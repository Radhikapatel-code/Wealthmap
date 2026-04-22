from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.models import AssetClass, AssetLot, MemberProfile, TaxState
from core.utils import money


@dataclass(slots=True)
class FamilyMember:
    profile: MemberProfile
    assets: list[AssetLot]
    realized_state: TaxState

    @property
    def member_id(self) -> str:
        return self.profile.member_id

    @property
    def name(self) -> str:
        return self.profile.name

    @property
    def net_worth_inr(self) -> Decimal:
        return money(sum(asset.market_value for asset in self.assets))

    @property
    def cost_basis_inr(self) -> Decimal:
        return money(sum(asset.cost_basis_total for asset in self.assets))

    @property
    def unrealized_gain_inr(self) -> Decimal:
        return money(sum(asset.unrealized_gain for asset in self.assets))

    def asset_class_breakdown(self) -> dict[str, Decimal]:
        breakdown: dict[str, Decimal] = {}
        for asset in self.assets:
            breakdown.setdefault(asset.asset_class.value, Decimal("0"))
            breakdown[asset.asset_class.value] += asset.market_value
        return {key: money(value) for key, value in breakdown.items()}

    def concentration_risks(self, threshold: Decimal = Decimal("0.25")) -> list[dict]:
        risks: list[dict] = []
        total = self.net_worth_inr
        if total <= 0:
            return risks
        for asset in self.assets:
            weight = asset.market_value / total
            if weight >= threshold:
                risks.append(
                    {
                        "member_id": self.member_id,
                        "symbol": asset.symbol,
                        "asset_class": asset.asset_class.value,
                        "weight": round(float(weight), 4),
                        "market_value_inr": float(asset.market_value),
                    }
                )
        return risks

    def assets_for_class(self, asset_class: AssetClass) -> list[AssetLot]:
        return [asset for asset in self.assets if asset.asset_class == asset_class]
