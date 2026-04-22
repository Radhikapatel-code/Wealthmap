from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from core.models import AssetClass, AssetLot, MemberEntityType, MemberProfile, TaxState
from core.utils import decimalize, parse_date


class PortfolioRepository:
    """In-memory portfolio state with sample-data loading support."""

    def __init__(
        self,
        family_name: str = "WealthMap Demo Family",
        members: list[MemberProfile] | None = None,
        assets: list[AssetLot] | None = None,
        realized_state: dict[str, TaxState] | None = None,
    ) -> None:
        self.family_name = family_name
        self._members = {member.member_id: member for member in members or []}
        self._assets = assets or []
        self._realized_state = realized_state or {}

    @classmethod
    def from_sample_file(cls, path: str | Path) -> "PortfolioRepository":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        members = [
            MemberProfile(
                member_id=item["member_id"],
                name=item["name"],
                entity_type=MemberEntityType(item.get("entity_type", "INDIVIDUAL")),
                tax_slab_rate=decimalize(item.get("tax_slab_rate", "0.30")),
                relation=item.get("relation"),
                metadata=item.get("metadata", {}),
            )
            for item in payload.get("members", [])
        ]
        assets = [
            AssetLot(
                asset_id=item["asset_id"],
                symbol=item["symbol"],
                asset_class=AssetClass(item["asset_class"]),
                platform=item["platform"],
                member_id=item["member_id"],
                quantity=decimalize(item["quantity"]),
                acquisition_date=parse_date(item["acquisition_date"]),
                cost_basis_per_unit=decimalize(item["cost_basis_per_unit"]),
                current_price=decimalize(item["current_price"]),
                metadata=item.get("metadata", {}),
            )
            for item in payload.get("assets", [])
        ]
        realized_state = {
            member_id: TaxState(
                ltcg_realized_inr=decimalize(item.get("ltcg_realized_inr")),
                stcg_realized_inr=decimalize(item.get("stcg_realized_inr")),
                crypto_realized_inr=decimalize(item.get("crypto_realized_inr")),
                tax_paid_inr=decimalize(item.get("tax_paid_inr")),
                crypto_tds_inr=decimalize(item.get("crypto_tds_inr")),
            )
            for member_id, item in payload.get("realized_state", {}).items()
        }
        return cls(
            family_name=payload.get("family_name", "WealthMap Demo Family"),
            members=members,
            assets=assets,
            realized_state=realized_state,
        )

    def list_members(self) -> list[MemberProfile]:
        return list(self._members.values())

    def get_member(self, member_id: str) -> MemberProfile:
        return self._members[member_id]

    def list_assets(self, member_id: str | None = None) -> list[AssetLot]:
        if member_id is None:
            return list(self._assets)
        return [asset for asset in self._assets if asset.member_id == member_id]

    def get_assets_by_symbol(self, member_id: str, symbol: str) -> list[AssetLot]:
        return [
            asset
            for asset in self._assets
            if asset.member_id == member_id and asset.symbol.upper() == symbol.upper()
        ]

    def get_realized_state(self, member_id: str) -> TaxState:
        return self._realized_state.get(member_id, TaxState())

    def add_manual_asset(self, asset: AssetLot) -> AssetLot:
        self._assets.append(asset)
        return asset

    def snapshot(self) -> dict:
        return {
            "family_name": self.family_name,
            "members": [
                {
                    **asdict(member),
                    "entity_type": member.entity_type.value,
                    "tax_slab_rate": str(member.tax_slab_rate),
                }
                for member in self.list_members()
            ],
            "assets": [
                {
                    **asdict(asset),
                    "asset_class": asset.asset_class.value,
                    "acquisition_date": asset.acquisition_date.isoformat(),
                    "quantity": str(asset.quantity),
                    "cost_basis_per_unit": str(asset.cost_basis_per_unit),
                    "current_price": str(asset.current_price),
                }
                for asset in self.list_assets()
            ],
            "realized_state": {
                member_id: state.to_dict()
                for member_id, state in self._realized_state.items()
            },
        }
