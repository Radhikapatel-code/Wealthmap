"""
Lot Tracker — FIFO lot management for Indian tax computation.
Tracks purchase lots and correctly consumes them on sale.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import uuid

from core.models import AssetLot, AssetClass, Platform, RealizedTransaction, TaxBreakdown, TaxClassification, TaxConstants


class LotTracker:
    """
    Maintains ordered (FIFO) lots per symbol per member.
    On sale, consumes oldest lots first and emits RealizedTransaction records.
    """

    def __init__(self):
        # key: (member_id, symbol) → sorted list of AssetLot (oldest first)
        self._lots: dict[tuple[str, str], list[AssetLot]] = defaultdict(list)
        self._realized: list[RealizedTransaction] = []

    # ── Ingestion ────────────────────────────────────────────────────────────

    def add_lot(self, lot: AssetLot) -> None:
        key = (lot.member_id, lot.symbol)
        self._lots[key].append(lot)
        # Keep sorted by acquisition date (oldest first = FIFO)
        self._lots[key].sort(key=lambda x: x.acquisition_date)

    def add_lots(self, lots: list[AssetLot]) -> None:
        for lot in lots:
            self.add_lot(lot)

    # ── Query ────────────────────────────────────────────────────────────────

    def get_lots(self, member_id: str, symbol: str) -> list[AssetLot]:
        return list(self._lots.get((member_id, symbol), []))

    def all_lots(self, member_id: Optional[str] = None) -> list[AssetLot]:
        result = []
        for (mid, _), lots in self._lots.items():
            if member_id is None or mid == member_id:
                result.extend(lots)
        return result

    def all_symbols(self, member_id: Optional[str] = None) -> list[str]:
        return list({
            symbol for (mid, symbol) in self._lots
            if member_id is None or mid == member_id
        })

    def get_realized(self, member_id: Optional[str] = None) -> list[RealizedTransaction]:
        if member_id is None:
            return list(self._realized)
        return [r for r in self._realized if r.member_id == member_id]

    # ── Sale Simulation ──────────────────────────────────────────────────────

    def simulate_sale(
        self,
        member_id: str,
        symbol: str,
        quantity: Decimal,
        sale_price: Decimal,
        sale_date: Optional[date] = None,
        ytd_realized_ltcg: Decimal = Decimal("0"),
    ) -> dict:
        """
        Simulate selling `quantity` units at `sale_price`.
        Returns detailed lot-by-lot breakdown without mutating state.
        """
        if sale_date is None:
            sale_date = date.today()

        available = self.get_lots(member_id, symbol)
        if not available:
            raise ValueError(f"No lots found for {member_id}/{symbol}")

        total_available = sum(l.quantity for l in available)
        if quantity > total_available:
            raise ValueError(
                f"Cannot sell {quantity} units — only {total_available} available for {symbol}"
            )

        lot_breakdown = []
        remaining_qty = quantity
        total_gain = Decimal("0")
        ltcg_this_tx = Decimal("0")
        stcg_this_tx = Decimal("0")
        crypto_gain = Decimal("0")
        total_tax = Decimal("0")

        ltcg_exemption_used = ytd_realized_ltcg

        for lot in available:
            if remaining_qty <= 0:
                break

            sell_qty = min(remaining_qty, lot.quantity)
            holding_days_at_sale = (sale_date - lot.acquisition_date).days
            gain = (sale_price - lot.effective_cost_basis) * sell_qty
            gain = gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Determine classification
            is_lt = self._is_long_term_at_date(lot, sale_date)

            if lot.asset_class == AssetClass.CRYPTO:
                classification = TaxClassification.CRYPTO
                tax_rate = TaxConstants.CRYPTO_RATE
                taxable = max(gain, Decimal("0"))
                tax = (taxable * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                crypto_gain += gain
            elif is_lt:
                classification = TaxClassification.LTCG
                tax_rate = TaxConstants.LTCG_RATE
                # Apply remaining exemption
                remaining_exemption = max(
                    TaxConstants.LTCG_EXEMPTION - ltcg_exemption_used, Decimal("0")
                )
                gain_above_exemption = max(gain - remaining_exemption, Decimal("0"))
                ltcg_exemption_used += min(gain, remaining_exemption)
                taxable = gain_above_exemption
                tax = (taxable * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ltcg_this_tx += gain
            else:
                classification = TaxClassification.STCG
                tax_rate = TaxConstants.STCG_RATE
                taxable = max(gain, Decimal("0"))
                tax = (taxable * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                stcg_this_tx += gain

            cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_tax_this_lot = tax + cess
            total_tax += total_tax_this_lot
            total_gain += gain

            lot_breakdown.append({
                "lot_id": lot.lot_id,
                "symbol": symbol,
                "quantity": float(sell_qty),
                "acquisition_date": lot.acquisition_date.isoformat(),
                "cost_basis_per_unit": float(lot.effective_cost_basis),
                "sale_price_per_unit": float(sale_price),
                "holding_days": holding_days_at_sale,
                "classification": classification.value,
                "gain_inr": float(gain),
                "tax_rate": float(tax_rate),
                "taxable_gain_inr": float(taxable),
                "tax_inr": float(tax),
                "cess_inr": float(cess),
                "total_tax_inr": float(total_tax_this_lot),
            })

            remaining_qty -= sell_qty

        proceeds = (quantity * sale_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_proceeds = proceeds - total_tax

        # Advisory: should user wait for LTCG?
        advisory = self._build_advisory(
            available, quantity, sale_date, ytd_realized_ltcg
        )

        return {
            "sale_summary": {
                "symbol": symbol,
                "member_id": member_id,
                "quantity": float(quantity),
                "sale_price_per_unit_inr": float(sale_price),
                "total_proceeds_inr": float(proceeds),
                "net_proceeds_after_tax_inr": float(net_proceeds),
            },
            "lot_breakdown": lot_breakdown,
            "tax_summary": {
                "total_gain_inr": float(total_gain),
                "ltcg_this_transaction_inr": float(ltcg_this_tx),
                "stcg_this_transaction_inr": float(stcg_this_tx),
                "crypto_gain_this_transaction_inr": float(crypto_gain),
                "ltcg_ytd_before_this_inr": float(ytd_realized_ltcg),
                "ltcg_exemption_remaining_inr": float(
                    max(TaxConstants.LTCG_EXEMPTION - ytd_realized_ltcg - ltcg_this_tx, Decimal("0"))
                ),
                "total_tax_inr": float(total_tax),
                "effective_tax_rate_pct": float(
                    (total_tax / proceeds * 100).quantize(Decimal("0.01")) if proceeds else Decimal("0")
                ),
            },
            "advisory": advisory,
        }

    def execute_sale(
        self,
        member_id: str,
        symbol: str,
        quantity: Decimal,
        sale_price: Decimal,
        sale_date: Optional[date] = None,
    ) -> list[RealizedTransaction]:
        """
        Actually consume lots (FIFO) and record realized transactions.
        Mutates internal state.
        """
        if sale_date is None:
            sale_date = date.today()

        key = (member_id, symbol)
        lots = self._lots.get(key, [])

        if not lots:
            raise ValueError(f"No lots for {member_id}/{symbol}")

        remaining = quantity
        realized = []
        updated_lots = []

        for lot in lots:
            if remaining <= 0:
                updated_lots.append(lot)
                continue

            sell_qty = min(remaining, lot.quantity)
            remaining -= sell_qty

            is_lt = self._is_long_term_at_date(lot, sale_date)
            gain = (sale_price - lot.effective_cost_basis) * sell_qty

            if lot.asset_class == AssetClass.CRYPTO:
                classification = TaxClassification.CRYPTO
                rate = TaxConstants.CRYPTO_RATE
            elif is_lt:
                classification = TaxClassification.LTCG
                rate = TaxConstants.LTCG_RATE
            else:
                classification = TaxClassification.STCG
                rate = TaxConstants.STCG_RATE

            taxable = max(gain, Decimal("0"))
            tax_amount = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cess = (tax_amount * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            tax_bd = TaxBreakdown(
                classification=classification,
                gross_gain=gain,
                taxable_gain=taxable,
                tax_rate=rate,
                tax_amount=tax_amount,
                cess_amount=cess,
                total_tax=tax_amount + cess,
            )

            realized.append(RealizedTransaction(
                transaction_id=str(uuid.uuid4()),
                lot_id=lot.lot_id,
                symbol=symbol,
                asset_class=lot.asset_class,
                member_id=member_id,
                quantity=sell_qty,
                sale_date=sale_date,
                sale_price_per_unit=sale_price,
                cost_basis_per_unit=lot.effective_cost_basis,
                acquisition_date=lot.acquisition_date,
                tax_breakdown=tax_bd,
            ))

            # If partial lot remains, keep the remainder
            if lot.quantity > sell_qty:
                remaining_lot = AssetLot(
                    lot_id=lot.lot_id + "_R",
                    symbol=lot.symbol,
                    asset_class=lot.asset_class,
                    platform=lot.platform,
                    member_id=lot.member_id,
                    quantity=lot.quantity - sell_qty,
                    acquisition_date=lot.acquisition_date,
                    cost_basis_per_unit=lot.cost_basis_per_unit,
                    current_price=lot.current_price,
                    grandfathered_cost=lot.grandfathered_cost,
                    isin=lot.isin,
                    name=lot.name,
                )
                updated_lots.append(remaining_lot)

        self._lots[key] = updated_lots
        self._realized.extend(realized)
        return realized

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_long_term_at_date(lot: AssetLot, check_date: date) -> bool:
        days_held = (check_date - lot.acquisition_date).days
        thresholds = {
            AssetClass.EQUITY: TaxConstants.EQUITY_LONG_TERM_DAYS,
            AssetClass.MUTUAL_FUND: TaxConstants.MF_EQUITY_LONG_TERM_DAYS,
            AssetClass.GOLD: TaxConstants.GOLD_LONG_TERM_DAYS,
            AssetClass.US_EQUITY: TaxConstants.EQUITY_LONG_TERM_DAYS,
        }
        threshold = thresholds.get(lot.asset_class)
        if threshold is None:
            return False
        return days_held >= threshold

    def _build_advisory(
        self,
        lots: list[AssetLot],
        quantity: Decimal,
        sale_date: date,
        ytd_ltcg: Decimal,
    ) -> dict:
        """Check if waiting for LTCG classification saves significant tax."""
        stcg_lots = [
            l for l in lots
            if not self._is_long_term_at_date(l, sale_date)
            and l.asset_class not in (AssetClass.CRYPTO,)
            and l.days_to_long_term > 0
        ]

        if not stcg_lots:
            return {
                "wait_recommendation": False,
                "reason": "All applicable lots are already long-term. No benefit to waiting.",
                "potential_saving_inr": 0.0,
            }

        earliest = min(stcg_lots, key=lambda x: x.days_to_long_term)
        gain = earliest.unrealized_gain
        stcg_tax = max(gain, Decimal("0")) * TaxConstants.STCG_RATE
        remaining_exemption = max(TaxConstants.LTCG_EXEMPTION - ytd_ltcg, Decimal("0"))
        ltcg_taxable = max(gain - remaining_exemption, Decimal("0"))
        ltcg_tax = ltcg_taxable * TaxConstants.LTCG_RATE
        saving = (stcg_tax - ltcg_tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if saving > Decimal("1000"):
            unlock_date = earliest.acquisition_date
            from datetime import timedelta
            unlock_date = earliest.acquisition_date + timedelta(days=TaxConstants.EQUITY_LONG_TERM_DAYS)
            return {
                "wait_recommendation": True,
                "reason": f"Waiting until {unlock_date.isoformat()} saves approximately ₹{float(saving):,.0f} in tax on lot {earliest.lot_id}.",
                "unlock_date": unlock_date.isoformat(),
                "days_to_wait": earliest.days_to_long_term,
                "potential_saving_inr": float(saving),
            }

        return {
            "wait_recommendation": False,
            "reason": "Tax saving from waiting is minimal (<₹1,000). Proceed if needed.",
            "potential_saving_inr": float(saving),
        }
