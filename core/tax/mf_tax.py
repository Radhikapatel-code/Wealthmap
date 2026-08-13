"""
Mutual Fund Tax Engine.
Equity MFs: same as equity (STCG 20%, LTCG 12.5% above ₹1.25L).
Debt MFs (purchased post April 1 2023): taxed at slab rate, no LTCG benefit.
Debt MFs (purchased pre April 1 2023): eligible for LTCG (20%) if held for 3+ years.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from core.models import AssetLot, AssetClass, TaxConstants, TaxBreakdown, TaxClassification


class MFTaxEngine:
    # Post-Apr 2023 debt MF rules: always slab rate
    DEBT_MF_CUTOFF_DATE_STR = "2023-04-01"

    def classify_mf(self, lot: AssetLot, equity_pct: float = 65.0) -> str:
        """
        Classify MF as EQUITY or DEBT type.
        Equity MFs: 65%+ in equities. Treated like equity for tax.
        Debt MFs: < 65% in equities.
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
        cutoff_date = date.fromisoformat(self.DEBT_MF_CUTOFF_DATE_STR)

        if mf_type == "DEBT":
            # Check acquisition date against cutoff date (April 1, 2023)
            if lot.acquisition_date >= cutoff_date:
                # Post Apr 1 2023: always slab rate (no LTCG benefit)
                taxable = max(gain, Decimal("0"))
                rate = tax_slab_rate
                treatment = "SLAB_RATE"
                classification = "STCG"
                note = "Debt MFs purchased on or after Apr 1 2023 are taxed at slab rate — no LTCG benefit."
            else:
                # Pre Apr 1 2023: eligible for LTCG if held >= 3 years (1095 days)
                if lot.holding_days >= TaxConstants.MF_DEBT_LONG_TERM_DAYS:
                    remaining_exemption = max(TaxConstants.LTCG_EXEMPTION - ytd_realized_ltcg, Decimal("0"))
                    taxable = max(gain - remaining_exemption, Decimal("0"))
                    # Pre-2023 Debt MF LTCG rate (20%)
                    rate = Decimal("0.20")
                    treatment = "LTCG"
                    classification = "LTCG"
                    note = "Debt MFs purchased before Apr 1 2023 held for 3+ years qualify for LTCG (20%)."
                else:
                    taxable = max(gain, Decimal("0"))
                    rate = tax_slab_rate
                    treatment = "SLAB_RATE"
                    classification = "STCG"
                    note = "Debt MFs purchased before Apr 1 2023 held under 3 years are taxed at slab rate."

            tax = (taxable * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_tax = tax + cess
            return {
                "mf_type": "DEBT",
                "classification": classification,
                "gain_inr": float(gain),
                "taxable_gain_inr": float(taxable),
                "treatment": treatment,
                "tax_rate": float(rate),
                "tax_inr": float(tax),
                "cess_inr": float(cess),
                "total_tax_inr": float(total_tax),
                "note": note,
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
            total_tax = tax + cess
            return {
                "mf_type": "EQUITY",
                "classification": classification,
                "gain_inr": float(gain),
                "taxable_gain_inr": float(taxable),
                "tax_rate": float(rate),
                "tax_inr": float(tax),
                "cess_inr": float(cess),
                "total_tax_inr": float(total_tax),
            }

    def compute_tax_if_sold(
        self,
        lots: list[AssetLot],
        ytd_realized_ltcg: Decimal = Decimal("0"),
        slab_rate: Decimal = Decimal("0.30"),
    ) -> TaxBreakdown:
        """Batch tax computation across multiple MF lots."""
        total_tax = Decimal("0")
        total_gain = Decimal("0")
        total_taxable = Decimal("0")
        total_cess = Decimal("0")
        total_raw_tax = Decimal("0")

        for lot in lots:
            mf_type = self.classify_mf(
                lot,
                equity_pct=lot.metadata.get("equity_pct", 100.0) if lot.metadata else 100.0
            )
            res = self.compute_tax(
                lot,
                mf_type=mf_type,
                tax_slab_rate=slab_rate,
                ytd_realized_ltcg=ytd_realized_ltcg
            )
            total_gain += Decimal(str(res["gain_inr"]))
            total_taxable += Decimal(str(res.get("taxable_gain_inr", res["gain_inr"])))
            total_raw_tax += Decimal(str(res["tax_inr"]))
            total_cess += Decimal(str(res["cess_inr"]))
            total_tax += Decimal(str(res["total_tax_inr"]))

        return TaxBreakdown(
            classification=TaxClassification.LTCG if total_taxable > 0 else TaxClassification.EXEMPT,
            gross_gain=total_gain,
            taxable_gain=total_taxable,
            tax_rate=slab_rate,
            tax_amount=total_raw_tax,
            cess_amount=total_cess,
            total_tax=total_tax,
            notes="Mutual Fund portfolio aggregate tax estimate",
        )
