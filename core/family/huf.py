"""
HUF (Hindu Undivided Family) tax computation.
HUF is a separate tax entity with its own PAN, slab, and LTCG exemption.
"""
from decimal import Decimal
from core.models import TaxConstants


# HUF tax slabs FY 2025-26 (old regime — HUF cannot use new regime with surcharge logic)
HUF_TAX_SLABS = [
    (Decimal("250000"), Decimal("0.00")),    # Up to ₹2.5L: Nil
    (Decimal("500000"), Decimal("0.05")),    # ₹2.5L – ₹5L: 5%
    (Decimal("1000000"), Decimal("0.20")),   # ₹5L – ₹10L: 20%
    (Decimal("9999999999"), Decimal("0.30")),# Above ₹10L: 30%
]


class HUFTaxEngine:
    """
    HUF-specific tax computation.
    HUF gets same basic exemption as individual (₹2.5L in old regime).
    HUF gets its own LTCG exemption of ₹1.25L per FY.
    """

    def compute_slab_tax(self, total_income: Decimal) -> dict:
        """Compute slab-rate tax for HUF under old regime."""
        tax = Decimal("0")
        prev_slab = Decimal("0")

        for slab_limit, rate in HUF_TAX_SLABS:
            taxable_in_slab = min(total_income, slab_limit) - prev_slab
            if taxable_in_slab <= 0:
                break
            tax += taxable_in_slab * rate
            prev_slab = slab_limit

        # Surcharge for income > ₹50L
        if total_income > Decimal("5000000"):
            surcharge_rate = Decimal("0.10") if total_income <= Decimal("10000000") else Decimal("0.15")
            tax += tax * surcharge_rate

        cess = tax * TaxConstants.HEALTH_EDUCATION_CESS
        total_tax = tax + cess

        return {
            "total_income_inr": float(total_income),
            "basic_exemption_inr": 250000.0,
            "tax_before_cess_inr": float(tax.quantize(Decimal("0.01"))),
            "cess_inr": float(cess.quantize(Decimal("0.01"))),
            "total_tax_inr": float(total_tax.quantize(Decimal("0.01"))),
            "effective_rate_pct": float(((total_tax / total_income) * 100).quantize(Decimal("0.01"))) if total_income else 0.0,
            "note": "HUF taxed as separate entity. Same LTCG exemption (₹1.25L) applies independently.",
        }

    def partition_considerations(self) -> dict:
        """Key considerations for HUF partition (informational)."""
        return {
            "ltcg_exemption": "₹1.25L LTCG exemption is available to HUF independently per FY.",
            "basic_exemption": "₹2.5L basic exemption (old regime) — same as individual.",
            "gift_from_huf": "Gifts from HUF to members are NOT taxable if from corpus.",
            "partition_tax": "Full partition of HUF assets may trigger capital gains — consult CA.",
            "coparceners": "Coparceners' share in HUF is not taxable in individual hands until distributed.",
        }
