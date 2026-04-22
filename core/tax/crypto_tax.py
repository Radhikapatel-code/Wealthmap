"""
Crypto Tax Engine — Indian crypto tax rules.
Section 115BBH: 30% flat tax, no exemption, no loss offset against other income.
1% TDS per transaction under Section 194S.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from core.models import AssetLot, AssetClass, TaxConstants, current_fy_start


@dataclass
class CryptoTransaction:
    """Represents a crypto buy/sell/transfer transaction."""
    tx_id: str
    symbol: str
    member_id: str
    tx_type: str          # BUY | SELL | TRANSFER_IN | TRANSFER_OUT
    quantity: Decimal
    price_inr: Decimal
    tx_date: date
    platform: str
    tds_deducted: Decimal = Decimal("0")
    notes: str = ""

    @property
    def value_inr(self) -> Decimal:
        return (self.quantity * self.price_inr).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class CryptoTDSSummary:
    total_sell_value_inr: Decimal
    tds_liability_inr: Decimal       # 1% of sell value
    tds_deducted_inr: Decimal        # Already deducted at source
    tds_balance_inr: Decimal         # Outstanding (liability - deducted)
    transactions_count: int
    flagged_transactions: list[str] = field(default_factory=list)


class CryptoTaxEngine:

    ADVANCE_TAX_DATES = [
        (6, 15, Decimal("0.15")),    # June 15 — 15%
        (9, 15, Decimal("0.45")),    # Sep 15 — 45%
        (12, 15, Decimal("0.75")),   # Dec 15 — 75%
        (3, 15, Decimal("1.00")),    # Mar 15 — 100%
    ]

    def compute_tax_on_gain(self, gain_inr: Decimal) -> dict:
        """
        Computes crypto tax at 30% flat.
        No exemption. No deductions. No carry-forward of losses.
        """
        if gain_inr <= 0:
            return {
                "gross_gain_inr": float(gain_inr),
                "taxable_gain_inr": 0.0,
                "tax_rate": float(TaxConstants.CRYPTO_RATE),
                "tax_inr": 0.0,
                "cess_inr": 0.0,
                "total_tax_inr": 0.0,
                "note": "No tax on loss (Section 115BBH — losses cannot be offset or carried forward).",
            }

        tax = (gain_inr * TaxConstants.CRYPTO_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = tax + cess

        return {
            "gross_gain_inr": float(gain_inr),
            "taxable_gain_inr": float(gain_inr),
            "tax_rate": float(TaxConstants.CRYPTO_RATE),
            "tax_inr": float(tax),
            "cess_inr": float(cess),
            "total_tax_inr": float(total),
            "effective_rate_pct": float(((total / gain_inr) * 100).quantize(Decimal("0.01"))),
        }

    def compute_tds_summary(
        self,
        transactions: list[CryptoTransaction],
        member_id: Optional[str] = None,
    ) -> CryptoTDSSummary:
        """
        Computes TDS liability vs. amount already deducted for the current FY.
        1% TDS is deducted on the SELL value at source by the exchange.
        """
        fy_start = current_fy_start()
        today = date.today()

        total_sell_value = Decimal("0")
        tds_deducted = Decimal("0")
        flagged = []

        for tx in transactions:
            if member_id and tx.member_id != member_id:
                continue
            if not (fy_start <= tx.tx_date <= today):
                continue
            if tx.tx_type != "SELL":
                continue

            total_sell_value += tx.value_inr
            tds_deducted += tx.tds_deducted

            # Flag if TDS not deducted but should have been
            expected_tds = (tx.value_inr * TaxConstants.CRYPTO_TDS_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if tx.tds_deducted < expected_tds * Decimal("0.95"):  # 5% tolerance
                flagged.append(tx.tx_id)

        tds_liability = (total_sell_value * TaxConstants.CRYPTO_TDS_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tds_balance = tds_liability - tds_deducted

        return CryptoTDSSummary(
            total_sell_value_inr=total_sell_value,
            tds_liability_inr=tds_liability,
            tds_deducted_inr=tds_deducted,
            tds_balance_inr=tds_balance,
            transactions_count=len([t for t in transactions if t.tx_type == "SELL"]),
            flagged_transactions=flagged,
        )

    def unrealized_gain_summary(self, crypto_lots: list[AssetLot]) -> dict:
        """Aggregate unrealized crypto gains for advance tax planning."""
        total_value = Decimal("0")
        total_cost = Decimal("0")
        by_symbol: dict[str, dict] = {}

        for lot in crypto_lots:
            if lot.asset_class != AssetClass.CRYPTO:
                continue
            total_value += lot.current_value
            total_cost += lot.total_cost_basis

            sym = lot.symbol
            if sym not in by_symbol:
                by_symbol[sym] = {"value": Decimal("0"), "cost": Decimal("0"), "qty": Decimal("0")}
            by_symbol[sym]["value"] += lot.current_value
            by_symbol[sym]["cost"] += lot.total_cost_basis
            by_symbol[sym]["qty"] += lot.quantity

        total_gain = total_value - total_cost
        tax_info = self.compute_tax_on_gain(total_gain)

        return {
            "total_crypto_value_inr": float(total_value),
            "total_crypto_cost_inr": float(total_cost),
            "total_unrealized_gain_inr": float(total_gain),
            "tax_if_fully_liquidated": tax_info,
            "by_symbol": {
                sym: {
                    "quantity": float(v["qty"]),
                    "current_value_inr": float(v["value"]),
                    "cost_basis_inr": float(v["cost"]),
                    "unrealized_gain_inr": float(v["value"] - v["cost"]),
                }
                for sym, v in by_symbol.items()
            },
        }

    def advance_tax_schedule(
        self,
        ytd_realized_gain: Decimal,
        unrealized_gain: Decimal = Decimal("0"),
        ytd_tax_paid: Decimal = Decimal("0"),
    ) -> list[dict]:
        """
        Projects advance tax installments based on current FY crypto gains.
        Uses 30% + 4% cess.
        """
        today = date.today()
        fy_start = current_fy_start()
        fy_year = fy_start.year

        # Conservative estimate: only realized gains
        total_estimated_gain = ytd_realized_gain
        total_tax = self.compute_tax_on_gain(total_estimated_gain)["total_tax_inr"]
        total_tax_decimal = Decimal(str(total_tax))

        schedule = []
        for month, day, cumulative_pct in self.ADVANCE_TAX_DATES:
            due_date = date(fy_year if month >= 4 else fy_year + 1, month, day)
            if due_date < fy_start:
                continue
            cumulative_due = (total_tax_decimal * cumulative_pct).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            installment = max(cumulative_due - ytd_tax_paid, Decimal("0"))
            overdue = due_date < today and installment > 0

            schedule.append({
                "due_date": due_date.isoformat(),
                "cumulative_percentage": float(cumulative_pct * 100),
                "cumulative_amount_due_inr": float(cumulative_due),
                "installment_inr": float(installment),
                "overdue": overdue,
                "days_until_due": (due_date - today).days,
            })

        return schedule
