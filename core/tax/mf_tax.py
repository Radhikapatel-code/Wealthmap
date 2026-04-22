"""
Mutual Fund Tax Engine.
Equity MFs: same as equity (STCG 20%, LTCG 12.5% above ₹1.25L).
Debt MFs (purchased post April 1 2023): taxed at slab rate, no LTCG benefit.
"""
from decimal import Decimal, ROUND_HALF_UP
from core.models import AssetLot, AssetClass, TaxConstants


class MFTaxEngine:
    # Post-Apr 2023 debt MF rules: always slab rate
    DEBT_MF_CUTOFF_DATE_STR = "2023-04-01"

    def classify_mf(self, lot: AssetLot, equity_pct: float = 65.0) -> str:
        """
        Classify MF as EQUITY or DEBT type.
        Equity MFs: 65%+ in equities. Treated like equity for tax.
        Debt MFs (post Apr 2023): slab rate.
        """
        return "EQUITY" if equity_pct >= 65.0 else "DEBT"

    def compute_tax(
        self,
        lot: AssetLot,
        mf_type: str = "EQUITY",
        tax_slab_rate: Decimal = Decimal("0.30"),
        ytd_realized_ltcg: Decimal = Decimal("0"),
    ) -> dict:
        gain = lot.unrealized_gain
        if mf_type == "DEBT":
            # Post Apr-2023: always slab rate (assume 30% for HNI)
            taxable = max(gain, Decimal("0"))
            tax = (taxable * tax_slab_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return {
                "mf_type": "DEBT",
                "gain_inr": float(gain),
                "treatment": "SLAB_RATE",
                "tax_rate": float(tax_slab_rate),
                "tax_inr": float(tax),
                "cess_inr": float(cess),
                "total_tax_inr": float(tax + cess),
                "note": "Debt MFs purchased after Apr 1 2023 taxed at slab rate — no LTCG benefit.",
            }
        else:
            # Equity MF: same as equity
            if lot.is_long_term:
                remaining_exemption = max(TaxConstants.LTCG_EXEMPTION - ytd_realized_ltcg, Decimal("0"))
                taxable = max(gain - remaining_exemption, Decimal("0"))
                rate = TaxConstants.LTCG_RATE
                classification = "LTCG"
            else:
                taxable = max(gain, Decimal("0"))
                rate = TaxConstants.STCG_RATE
                classification = "STCG"

            tax = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return {
                "mf_type": "EQUITY",
                "classification": classification,
                "gain_inr": float(gain),
                "taxable_gain_inr": float(taxable),
                "tax_rate": float(rate),
                "tax_inr": float(tax),
                "cess_inr": float(cess),
                "total_tax_inr": float(tax + cess),
            }
