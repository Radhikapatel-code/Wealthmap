"""
Family member and family unit models for WealthMap.
Wealth is tracked at the family level — each member has their own tax slate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, AssetClass, TaxConstants, PortfolioSnapshot, current_fy_start


@dataclass
class FamilyMember:
    member_id: str
    name: str
    relationship: str       # SELF | SPOUSE | CHILD | PARENT | HUF
    pan: Optional[str] = None
    tax_slab_rate: Decimal = Decimal("0.30")    # 30% for HNI
    is_huf: bool = False
    portfolio: Optional[PortfolioSnapshot] = None

    # YTD realized gains (loaded from DB / history)
    ytd_realized_ltcg: Decimal = Decimal("0")
    ytd_realized_stcg: Decimal = Decimal("0")
    ytd_realized_crypto: Decimal = Decimal("0")
    ytd_tax_paid: Decimal = Decimal("0")

    @property
    def ltcg_exemption_remaining(self) -> Decimal:
        return max(TaxConstants.LTCG_EXEMPTION - self.ytd_realized_ltcg, Decimal("0"))

    @property
    def net_worth(self) -> Decimal:
        if self.portfolio is None:
            return Decimal("0")
        return self.portfolio.total_value

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "name": self.name,
            "relationship": self.relationship,
            "is_huf": self.is_huf,
            "net_worth_inr": float(self.net_worth),
            "tax_slab_rate": float(self.tax_slab_rate),
            "ltcg_exemption_remaining_inr": float(self.ltcg_exemption_remaining),
            "ytd_realized_ltcg_inr": float(self.ytd_realized_ltcg),
            "ytd_realized_stcg_inr": float(self.ytd_realized_stcg),
            "ytd_realized_crypto_inr": float(self.ytd_realized_crypto),
            "ytd_tax_paid_inr": float(self.ytd_tax_paid),
        }


@dataclass
class GiftTransaction:
    """Intra-family transfers above ₹50,000 are taxable as 'Income from Other Sources'."""
    from_member: str
    to_member: str
    amount_inr: Decimal
    transfer_date: str
    asset_description: str
    tax_applicable: bool = False
    notes: str = ""

    GIFT_EXEMPTION = Decimal("50000")  # Per FY per donor

    def __post_init__(self):
        self.tax_applicable = self.amount_inr > self.GIFT_EXEMPTION


@dataclass
class FamilyUnit:
    family_name: str
    members: list[FamilyMember] = field(default_factory=list)
    gift_transactions: list[GiftTransaction] = field(default_factory=list)

    def add_member(self, member: FamilyMember) -> None:
        self.members.append(member)

    def get_member(self, member_id: str) -> Optional[FamilyMember]:
        return next((m for m in self.members if m.member_id == member_id), None)

    @property
    def total_net_worth(self) -> Decimal:
        return sum(m.net_worth for m in self.members)

    @property
    def all_lots(self) -> list[AssetLot]:
        lots = []
        for m in self.members:
            if m.portfolio:
                lots.extend(m.portfolio.lots)
        return lots

    def asset_class_breakdown(self) -> dict[str, dict]:
        """Consolidated asset class breakdown across all members."""
        breakdown: dict[str, dict] = {}
        total = self.total_net_worth

        for lot in self.all_lots:
            cls = lot.asset_class.value
            if cls not in breakdown:
                breakdown[cls] = {"value_inr": Decimal("0"), "members": set()}
            breakdown[cls]["value_inr"] += lot.current_value
            breakdown[cls]["members"].add(lot.member_id)

        result = {}
        for cls, data in breakdown.items():
            val = data["value_inr"]
            result[cls] = {
                "value_inr": float(val),
                "pct_of_portfolio": float((val / total * 100).quantize(Decimal("0.01"))) if total else 0.0,
                "member_count": len(data["members"]),
            }
        return result

    def concentration_risks(self, threshold_pct: float = 15.0) -> list[dict]:
        """Flag any single stock/asset > threshold_pct of total portfolio."""
        symbol_values: dict[str, Decimal] = {}
        total = self.total_net_worth

        for lot in self.all_lots:
            symbol_values[lot.symbol] = symbol_values.get(lot.symbol, Decimal("0")) + lot.current_value

        risks = []
        for symbol, value in symbol_values.items():
            pct = float((value / total * 100).quantize(Decimal("0.01"))) if total else 0.0
            if pct >= threshold_pct:
                risks.append({
                    "symbol": symbol,
                    "value_inr": float(value),
                    "portfolio_pct": pct,
                    "risk_level": "HIGH" if pct >= 25.0 else "MEDIUM",
                    "recommendation": f"Position at {pct:.1f}% of total portfolio. Consider rebalancing.",
                })
        risks.sort(key=lambda r: r["portfolio_pct"], reverse=True)
        return risks

    def ytd_tax_summary(self) -> dict:
        """Family-level YTD tax summary. LTCG exemption is per-individual."""
        members_data = []
        total_tax = Decimal("0")
        total_ltcg = Decimal("0")
        total_stcg = Decimal("0")

        for m in self.members:
            member_tax = (
                max(m.ytd_realized_ltcg - TaxConstants.LTCG_EXEMPTION, Decimal("0")) * TaxConstants.LTCG_RATE
                + max(m.ytd_realized_stcg, Decimal("0")) * TaxConstants.STCG_RATE
                + max(m.ytd_realized_crypto, Decimal("0")) * TaxConstants.CRYPTO_RATE
            )
            total_tax += member_tax
            total_ltcg += m.ytd_realized_ltcg
            total_stcg += m.ytd_realized_stcg
            members_data.append({
                "member_id": m.member_id,
                "name": m.name,
                "ytd_realized_ltcg_inr": float(m.ytd_realized_ltcg),
                "ytd_realized_stcg_inr": float(m.ytd_realized_stcg),
                "estimated_tax_inr": float(member_tax),
                "ltcg_exemption_remaining_inr": float(m.ltcg_exemption_remaining),
            })

        return {
            "family_total_ltcg_inr": float(total_ltcg),
            "family_total_stcg_inr": float(total_stcg),
            "estimated_total_tax_inr": float(total_tax),
            "note": "LTCG exemption (₹1.25L) is per individual — not shared across family.",
            "members": members_data,
        }

    def gift_tax_alerts(self) -> list[dict]:
        """Flag taxable intra-family gifts."""
        return [
            {
                "from": g.from_member,
                "to": g.to_member,
                "amount_inr": float(g.amount_inr),
                "date": g.transfer_date,
                "tax_applicable": g.tax_applicable,
                "note": (
                    f"Gift of ₹{float(g.amount_inr):,.0f} exceeds ₹50,000 — taxable as 'Income from Other Sources' in recipient's hands."
                    if g.tax_applicable else "Within ₹50,000 exemption limit."
                ),
            }
            for g in self.gift_transactions
        ]

    def to_summary_dict(self) -> dict:
        return {
            "family_name": self.family_name,
            "member_count": len(self.members),
            "total_net_worth_inr": float(self.total_net_worth),
            "asset_class_breakdown": self.asset_class_breakdown(),
            "concentration_risks": self.concentration_risks(),
            "ytd_tax_summary": self.ytd_tax_summary(),
            "members": [m.to_dict() for m in self.members],
        }
