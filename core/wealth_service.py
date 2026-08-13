from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from config.settings import get_settings
from core.aggregator.manual_import import load_manual_assets_from_payload
from core.family.family_unit import FamilyUnit
from core.family.member import FamilyMember
from core.models import AssetClass, AssetLot
from core.repository import PortfolioRepository
from core.tax.crypto_tax import CryptoTaxEngine
from core.tax.equity_tax import EquityTaxEngine
from core.tax.fd_tax import FixedDepositTaxEngine
from core.tax.lot_tracker import LotTracker
from core.tax.mf_tax import MutualFundTaxEngine
from core.tax.tax_calendar import TaxCalendar
from core.tax.tlh_scanner import TaxLossHarvestScanner
from core.utils import decimalize, money


class WealthService:
    def __init__(self, repository: PortfolioRepository) -> None:
        self.repository = repository
        self.equity_tax = EquityTaxEngine()
        self.crypto_tax = CryptoTaxEngine()
        self.mf_tax = MutualFundTaxEngine()
        self.fd_tax = FixedDepositTaxEngine()
        self.lot_tracker = LotTracker()
        self.tax_calendar = TaxCalendar()
        self.tlh_scanner = TaxLossHarvestScanner()

    def family_unit(self) -> FamilyUnit:
        members = [
            FamilyMember(
                profile=profile,
                assets=self.repository.list_assets(profile.member_id),
                realized_state=self.repository.get_realized_state(profile.member_id),
            )
            for profile in self.repository.list_members()
        ]
        return FamilyUnit(name=self.repository.family_name, members=members)

    def family_snapshot(self) -> dict:
        family = self.family_unit()
        return {
            "family_name": family.name,
            "total_net_worth_inr": float(family.total_net_worth_inr),
            "total_unrealized_gain_inr": float(family.total_unrealized_gain_inr),
            "asset_class_breakdown": {
                key: float(value) for key, value in family.asset_class_breakdown().items()
            },
            "members": [self.member_snapshot(member.member_id) for member in family.members],
            "concentration_risks": family.concentration_risks(),
        }

    def member_snapshot(self, member_id: str) -> dict:
        member = self.family_unit().member_map()[member_id]
        return {
            "member_id": member.member_id,
            "name": member.name,
            "entity_type": member.profile.entity_type.value,
            "net_worth_inr": float(member.net_worth_inr),
            "cost_basis_inr": float(member.cost_basis_inr),
            "unrealized_gain_inr": float(member.unrealized_gain_inr),
            "asset_class_breakdown": {
                key: float(value) for key, value in member.asset_class_breakdown().items()
            },
            "assets": [self._serialize_asset(asset) for asset in member.assets],
            "realized_state": member.realized_state.to_dict(),
            "concentration_risks": member.concentration_risks(),
        }

    def net_worth_breakdown(self) -> dict:
        family = self.family_unit()
        return {
            "family_name": family.name,
            "total_net_worth_inr": float(family.total_net_worth_inr),
            "member_breakdown": [
                {
                    "member_id": member.member_id,
                    "name": member.name,
                    "net_worth_inr": float(member.net_worth_inr),
                }
                for member in family.members
            ],
            "asset_class_breakdown": {
                key: float(value) for key, value in family.asset_class_breakdown().items()
            },
        }

    def add_manual_asset(self, payload: dict) -> dict:
        assets = load_manual_assets_from_payload(payload)
        if not assets:
            raise ValueError("Manual asset payload did not contain any assets.")
        created = self.repository.add_manual_asset(assets[0])
        return self._serialize_asset(created)

    def tax_liability(self) -> dict:
        members = []
        family_total = 0
        projected_fy_tax = 0
        family = self.family_unit()
        for member in family.members:
            breakdown = self._member_tax_breakdown(member.member_id)
            family_total += breakdown["current_outstanding_tax_inr"]
            projected_fy_tax += breakdown["projected_tax_if_all_sold_today_inr"]
            members.append(breakdown)
        return {
            "family_name": family.name,
            "members": members,
            "current_outstanding_tax_inr": float(money(family_total)),
            "projected_tax_if_all_sold_today_inr": float(money(projected_fy_tax)),
        }

    def simulate_sale_rust(self, member_id: str, symbol: str, quantity: str | float | int, sale_price: str | float | int) -> dict:
        from datetime import date
        from core.tax.rust_engine_bridge import RustEngineBridge
        lots = self.repository.get_assets_by_symbol(member_id, symbol)
        raw_txs = []
        for lot in lots:
            raw_txs.append({
                "transaction_id": f"TX-BUY-{lot.asset_id}",
                "member_id": member_id,
                "symbol": symbol,
                "side": "BUY",
                "date": lot.acquisition_date.isoformat(),
                "quantity": str(lot.quantity),
                "price": str(lot.cost_basis_per_unit),
                "asset_class": lot.asset_class.value if hasattr(lot.asset_class, "value") else str(lot.asset_class),
                "lot_id": lot.asset_id,
            })
        raw_txs.append({
            "transaction_id": "TX-SELL-SIM",
            "member_id": member_id,
            "symbol": symbol,
            "side": "SELL",
            "date": date.today().isoformat(),
            "quantity": str(quantity),
            "price": str(sale_price),
            "asset_class": lots[0].asset_class.value if lots and hasattr(lots[0].asset_class, "value") else "EQUITY",
            "lot_id": None,
        })
        return RustEngineBridge.compute_tax_lots(raw_txs)

    def simulate_sale(
        self,
        member_id: str,
        symbol: str,
        quantity: str | float | int,
        sale_price: str | float | int | None = None,
        method: str = "FIFO",
    ) -> dict:
        if method.upper() != "FIFO":
            raise ValueError("Only FIFO sale simulation is implemented in this MVP.")

        lots = self.repository.get_assets_by_symbol(member_id, symbol)
        if not lots:
            raise ValueError(f"No lots found for {member_id}/{symbol}")

        qty_decimal = decimalize(quantity)
        price_decimal = decimalize(sale_price) if sale_price is not None else lots[0].current_price

        state = self.repository.get_realized_state(member_id)

        tracker = LotTracker()
        tracker.add_lots(lots)

        return tracker.simulate_sale(
            member_id=member_id,
            symbol=symbol,
            quantity=qty_decimal,
            sale_price=price_decimal,
            ytd_realized_ltcg=state.ltcg_realized_inr,
        )

    def ltcg_calendar(self, window_days: int = 90) -> dict:
        assets = [
            asset
            for asset in self.repository.list_assets()
            if asset.asset_class in {AssetClass.EQUITY, AssetClass.MF, AssetClass.MUTUAL_FUND, AssetClass.US_EQUITY}
        ]
        ytd_ltcg = sum(
            self.repository.get_realized_state(m.member_id).ltcg_realized_inr
            for m in self.repository.list_members()
        )
        return {
            "events": self.tax_calendar.ltcg_unlock_events(assets, look_ahead_days=window_days, ytd_realized_ltcg=ytd_ltcg),
            "window_days": window_days,
        }

    def tlh_opportunities(self) -> dict:
        ytd_ltcg = sum(
            self.repository.get_realized_state(m.member_id).ltcg_realized_inr
            for m in self.repository.list_members()
        )
        ytd_stcg = sum(
            self.repository.get_realized_state(m.member_id).stcg_realized_inr
            for m in self.repository.list_members()
        )
        opportunities = self.tlh_scanner.scan(
            self.repository.list_assets(),
            ytd_realized_ltcg=ytd_ltcg,
            ytd_realized_stcg=ytd_stcg,
        )
        return {
            "opportunities": opportunities,
            "count": len(opportunities),
        }

    def crypto_tds_summary(self) -> dict:
        records = []
        for member in self.repository.list_members():
            lots = [asset for asset in self.repository.list_assets(member.member_id) if asset.asset_class == AssetClass.CRYPTO]
            tax = self.crypto_tax.compute_tax_if_sold(lots)
            state = self.repository.get_realized_state(member.member_id)
            records.append(
                {
                    "member_id": member.member_id,
                    "name": member.name,
                    "crypto_unrealized_gain_inr": float(tax.crypto_gain_inr),
                    "projected_crypto_tax_inr": float(tax.crypto_tax_inr),
                    "projected_tds_if_sold_today_inr": float(tax.tds_inr),
                    "ytd_crypto_tds_recorded_inr": float(state.crypto_tds_inr),
                }
            )
        return {"records": records}

    def advance_tax(self) -> dict:
        projected_tax = decimalize(self.tax_liability()["projected_tax_if_all_sold_today_inr"])
        return {
            "schedule": self.tax_calendar.advance_tax_schedule(projected_tax),
            "projected_total_tax_inr": float(projected_tax),
        }

    def _member_tax_breakdown(self, member_id: str) -> dict:
        member = self.family_unit().member_map()[member_id]
        state = member.realized_state
        equity_lots = [asset for asset in member.assets if asset.asset_class in {AssetClass.EQUITY, AssetClass.US_EQUITY}]
        mf_lots = [asset for asset in member.assets if asset.asset_class == AssetClass.MF]
        crypto_lots = [asset for asset in member.assets if asset.asset_class == AssetClass.CRYPTO]
        fd_lots = [asset for asset in member.assets if asset.asset_class == AssetClass.FD]

        equity_breakdown = self.equity_tax.compute_tax_if_sold(
            equity_lots,
            ytd_realized_ltcg=state.ltcg_realized_inr,
            ytd_realized_stcg=state.stcg_realized_inr,
        )
        mf_breakdown = self.mf_tax.compute_tax_if_sold(
            mf_lots,
            ytd_realized_ltcg=state.ltcg_realized_inr,
            slab_rate=member.profile.tax_slab_rate,
        )
        crypto_breakdown = self.crypto_tax.compute_tax_if_sold(crypto_lots)
        fd_breakdown = self.fd_tax.compute_tax(fd_lots, slab_rate=member.profile.tax_slab_rate)

        total_projected = money(
            equity_breakdown.total_tax_inr
            + mf_breakdown.total_tax_inr
            + crypto_breakdown.total_tax_inr
            + fd_breakdown.total_tax_inr
        )
        outstanding = max(total_projected - state.tax_paid_inr, 0)
        return {
            "member_id": member.member_id,
            "name": member.name,
            "entity_type": member.profile.entity_type.value,
            "projected_tax_if_all_sold_today_inr": float(total_projected),
            "tax_paid_ytd_inr": float(state.tax_paid_inr),
            "current_outstanding_tax_inr": float(money(outstanding)),
            "breakdown": {
                "equity": equity_breakdown.to_dict(),
                "mutual_funds": mf_breakdown.to_dict(),
                "crypto": crypto_breakdown.to_dict(),
                "fixed_deposits": fd_breakdown.to_dict(),
            },
        }

    def _serialize_asset(self, asset: AssetLot) -> dict:
        return {
            "asset_id": asset.asset_id,
            "symbol": asset.symbol,
            "asset_class": asset.asset_class.value,
            "platform": asset.platform,
            "member_id": asset.member_id,
            "quantity": float(asset.quantity),
            "acquisition_date": asset.acquisition_date.isoformat(),
            "cost_basis_per_unit": float(asset.cost_basis_per_unit),
            "current_price": float(asset.current_price),
            "market_value_inr": float(asset.market_value),
            "unrealized_gain_inr": float(asset.unrealized_gain),
            "holding_days": asset.holding_days,
            "is_long_term": asset.is_long_term,
            "metadata": asset.metadata,
        }


@lru_cache(maxsize=1)
def get_wealth_service() -> WealthService:
    settings = get_settings()
    sample_path = Path(settings.sample_portfolio_path)
    repository = PortfolioRepository.from_sample_file(sample_path)
    return WealthService(repository=repository)
