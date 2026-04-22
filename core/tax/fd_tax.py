"""
Fixed Deposit Tax Engine.
FD interest is taxed at slab rate.
TDS deducted at 10% above ₹40,000 interest per bank per FY.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from core.models import TaxConstants


class FDTaxEngine:

    def compute_interest(
        self,
        principal: Decimal,
        annual_rate_pct: Decimal,
        start_date: date,
        maturity_date: date,
        compounding: str = "QUARTERLY",
    ) -> dict:
        """Compute FD interest with compound interest formula."""
        days = (maturity_date - start_date).days
        years = Decimal(str(days)) / Decimal("365")
        rate = annual_rate_pct / Decimal("100")

        if compounding == "QUARTERLY":
            n = Decimal("4")
            maturity_value = principal * ((1 + rate / n) ** (n * years))
        elif compounding == "MONTHLY":
            n = Decimal("12")
            maturity_value = principal * ((1 + rate / n) ** (n * years))
        else:
            maturity_value = principal * (1 + rate * years)

        interest = maturity_value - principal
        interest = interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "principal_inr": float(principal),
            "annual_rate_pct": float(annual_rate_pct),
            "tenure_days": days,
            "tenure_years": float(years.quantize(Decimal("0.01"))),
            "maturity_value_inr": float(maturity_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "total_interest_inr": float(interest),
            "compounding": compounding,
        }

    def compute_tax_and_tds(
        self,
        total_interest_inr: Decimal,
        tax_slab_rate: Decimal = Decimal("0.30"),
        tds_already_deducted: Decimal = Decimal("0"),
    ) -> dict:
        """
        Compute slab-rate tax on FD interest and TDS reconciliation.
        TDS is deducted at 10% if interest > ₹40,000 per bank per FY.
        """
        tds_applicable = total_interest_inr > TaxConstants.FD_TDS_THRESHOLD
        tds_amount = (
            (total_interest_inr * TaxConstants.FD_TDS_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if tds_applicable else Decimal("0")
        )

        # Actual tax liability at slab rate
        tax = (total_interest_inr * tax_slab_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cess = (tax * TaxConstants.HEALTH_EDUCATION_CESS).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_tax = tax + cess

        # TDS is advance tax — credit it
        balance_tax = max(total_tax - tds_already_deducted, Decimal("0"))

        return {
            "total_interest_inr": float(total_interest_inr),
            "tax_slab_rate": float(tax_slab_rate),
            "tds_threshold_inr": float(TaxConstants.FD_TDS_THRESHOLD),
            "tds_applicable": tds_applicable,
            "tds_at_source_inr": float(tds_amount),
            "tds_already_deducted_inr": float(tds_already_deducted),
            "actual_tax_liability_inr": float(total_tax),
            "balance_tax_payable_inr": float(balance_tax),
            "note": (
                "TDS of 10% deducted by bank if interest > ₹40,000. "
                "File 15G/15H to avoid TDS if income is below taxable limit."
            ),
        }
