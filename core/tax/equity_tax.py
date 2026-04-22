"""
Equity Tax Engine — LTCG/STCG computation for Indian equities and equity MFs.
FY 2025-26 rates:
  STCG: 20% flat
  LTCG: 12.5% above ₹1,25,000 exemption per individual per FY
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from core.models import (
    AssetLot, AssetClass, TaxBreakdown, TaxClassification,
    TaxConstants, UnlockEvent, current_fy_start
)


class EquityTaxEngine:

    def compute_tax_if_sold_today(
        self,
        lots: list[AssetLot],
        ytd_realized_ltcg: Decimal = Decimal("0"),
        ytd_realized_stcg: Decimal = Decimal("0"),
    ) -> dict:
        """
        Given a set of lots (all same symbol/member), compute aggregate tax
        if all were sold at current price today.
        """
        total_ltcg = Decimal("0")
        total_stcg = Decimal("0")
        total_tax = Decimal("0")

        for lot in lots:
            gain = lot.unrealized_gain
            if gain <= 0:
                continue
            if lot.is_long_term:
                total_ltcg += gain
            else:
                total_stcg += gain

        # Apply LTCG exemption
        remaining_exemption = max(TaxConstants.LTCG_EXEMPTION - ytd_realized_ltcg, Decimal("0"))
        taxable_ltcg = max(total_ltcg - remaining_exemption, Decimal("0"))
        ltcg_tax = (taxable_ltcg * TaxConstants.LTCG_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # STCG (no exemption)
        stcg_tax = (max(total_stcg, Decimal("0")) * TaxConstants.STCG_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        raw_tax = ltcg_tax + stcg_tax
        cess = (raw_tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_tax = raw_tax + cess

        return {
            "total_ltcg_inr": float(total_ltcg),
            "total_stcg_inr": float(total_stcg),
            "ltcg_exemption_used_inr": float(min(total_ltcg, remaining_exemption)),
            "taxable_ltcg_inr": float(taxable_ltcg),
            "taxable_stcg_inr": float(max(total_stcg, Decimal("0"))),
            "ltcg_tax_inr": float(ltcg_tax),
            "stcg_tax_inr": float(stcg_tax),
            "cess_inr": float(cess),
            "total_tax_inr": float(total_tax),
        }

    def ltcg_unlock_calendar(
        self,
        lots: list[AssetLot],
        look_ahead_days: int = 90,
    ) -> list[UnlockEvent]:
        """
        Returns upcoming LTCG unlock events within look_ahead_days.
        Only includes STCG lots with positive unrealized gain.
        """
        today = date.today()
        cutoff = today + timedelta(days=look_ahead_days)
        events: list[UnlockEvent] = []

        for lot in lots:
            if lot.asset_class not in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND):
                continue
            if lot.is_long_term:
                continue  # Already long-term
            if lot.unrealized_gain <= 0:
                continue  # Loss lot — no tax urgency

            unlock_date = lot.acquisition_date + timedelta(days=TaxConstants.EQUITY_LONG_TERM_DAYS)
            if today <= unlock_date <= cutoff:
                gain = lot.unrealized_gain
                stcg_tax = (gain * TaxConstants.STCG_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ltcg_tax = (gain * TaxConstants.LTCG_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                saving = stcg_tax - ltcg_tax

                events.append(UnlockEvent(
                    lot_id=lot.lot_id,
                    symbol=lot.symbol,
                    member_id=lot.member_id,
                    unlock_date=unlock_date,
                    quantity=lot.quantity,
                    current_gain_inr=gain,
                    tax_saving_inr=saving,
                ))

        events.sort(key=lambda e: e.unlock_date)
        return events

    def ytd_realized_summary(
        self,
        realized_transactions: list,
        member_id: Optional[str] = None,
    ) -> dict:
        """Aggregate realized gains/losses for the current financial year."""
        fy_start = current_fy_start()
        today = date.today()

        ltcg = Decimal("0")
        stcg = Decimal("0")
        total_tax = Decimal("0")

        for tx in realized_transactions:
            if member_id and tx.member_id != member_id:
                continue
            if not (fy_start <= tx.sale_date <= today):
                continue
            if tx.asset_class not in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND):
                continue

            if tx.tax_breakdown.classification == TaxClassification.LTCG:
                ltcg += tx.tax_breakdown.gross_gain
            elif tx.tax_breakdown.classification == TaxClassification.STCG:
                stcg += tx.tax_breakdown.gross_gain
            total_tax += tx.tax_breakdown.total_tax

        return {
            "fy_start": fy_start.isoformat(),
            "ytd_realized_ltcg_inr": float(ltcg),
            "ytd_realized_stcg_inr": float(stcg),
            "ltcg_exemption_used_inr": float(min(ltcg, TaxConstants.LTCG_EXEMPTION)),
            "ltcg_exemption_remaining_inr": float(
                max(TaxConstants.LTCG_EXEMPTION - ltcg, Decimal("0"))
            ),
            "ytd_tax_paid_inr": float(total_tax),
        }

    def optimal_sell_recommendation(self, lot: AssetLot) -> dict:
        """
        For a single STCG lot, compute the tax delta between selling today
        vs. waiting for LTCG classification.
        """
        gain = lot.unrealized_gain
        if gain <= 0:
            return {
                "recommendation": "HOLD_OR_HARVEST",
                "reason": "Lot is currently at a loss. Consider for tax-loss harvesting.",
                "current_gain_inr": float(gain),
            }

        if lot.is_long_term:
            ltcg_tax = (max(gain - TaxConstants.LTCG_EXEMPTION, Decimal("0")) * TaxConstants.LTCG_RATE)
            return {
                "recommendation": "SELL_NOW",
                "reason": "Lot already qualifies for LTCG treatment.",
                "current_gain_inr": float(gain),
                "estimated_tax_inr": float(ltcg_tax),
            }

        stcg_tax = gain * TaxConstants.STCG_RATE
        ltcg_tax = max(gain - TaxConstants.LTCG_EXEMPTION, Decimal("0")) * TaxConstants.LTCG_RATE
        saving = stcg_tax - ltcg_tax

        return {
            "recommendation": "WAIT_FOR_LTCG" if saving > Decimal("2000") else "SELL_NOW_ACCEPTABLE",
            "days_to_ltcg": lot.days_to_long_term,
            "unlock_date": (lot.acquisition_date + timedelta(days=TaxConstants.EQUITY_LONG_TERM_DAYS)).isoformat(),
            "stcg_tax_if_sold_today_inr": float(stcg_tax),
            "ltcg_tax_if_waited_inr": float(ltcg_tax),
            "tax_saving_inr": float(saving),
            "current_gain_inr": float(gain),
        }
