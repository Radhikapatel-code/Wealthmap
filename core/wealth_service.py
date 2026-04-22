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
from core.tax.lot_tracker import FIFOLotTracker
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
        self.lot_tracker = FIFOLotTracker()
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

    def simulate_sale(self, member_id: str, symbol: str, quantity: str | float | int, method: str = "FIFO") -> dict:
        if method.upper() != "FIFO":
            raise ValueError("Only FIFO sale simulation is implemented in this MVP.")
        lots = self.repository.get_assets_by_symbol(member_id, symbol)
        sale_slices = self.lot_tracker.build_sale_slices(lots, quantity)
        state = self.repository.get_realized_state(member_id)
        remaining_exemption = max(
            self.equity_tax.LTCG_EXEMPTION_INR - state.ltcg_realized_inr,
            0,
        )
        lot_breakdown = []
        ltcg_gain = 0
        stcg_gain = 0
        crypto_gain = 0
        total_proceeds = 0
        for sale_slice in sale_slices:
            gain = sale_slice.gain_inr
            total_proceeds += sale_slice.proceeds_inr
            classification = "LTCG" if sale_slice.lot.is_long_term else "STCG"
            rate = 0.125 if classification == "LTCG" else 0.20
            if sale_slice.lot.asset_class == AssetClass.CRYPTO:
                classification = "CRYPTO"
                rate = 0.30
            if classification == "LTCG":
                ltcg_gain += gain
            elif classification == "STCG":
                stcg_gain += gain
            elif classification == "CRYPTO":
                crypto_gain += gain
            tax_inr = 0
            if classification == "LTCG":
                taxable = max(min(gain, max(ltcg_gain - remaining_exemption, 0)), 0)
                tax_inr = taxable * rate
            elif classification == "STCG":
                tax_inr = max(gain, 0) * rate
            elif classification == "CRYPTO":
                tax_inr = max(gain, 0) * rate
            lot_breakdown.append(
                {
                    "lot_id": sale_slice.lot.asset_id,
                    "quantity": float(sale_slice.quantity),
                    "acquisition_date": sale_slice.lot.acquisition_date.isoformat(),
                    "cost_basis_per_unit": float(sale_slice.lot.cost_basis_per_unit),
                    "holding_days": sale_slice.lot.holding_days,
                    "classification": classification,
                    "gain_inr": float(gain),
                    "tax_rate": rate,
                    "tax_inr": float(money(tax_inr)),
                }
            )
        effective_ltcg_taxable = max(decimalize(ltcg_gain) - decimalize(remaining_exemption), 0)
        total_tax = (
            effective_ltcg_taxable * decimalize("0.125")
            + max(decimalize(stcg_gain), 0) * decimalize("0.20")
            + max(decimalize(crypto_gain), 0) * decimalize("0.30")
        )

        recommendation = "All matched lots are already long-term. Proceed if liquidity is needed."
        wait_recommendation = False
        alternative = "No near-term LTCG unlock difference detected."
        same_symbol = self.repository.get_assets_by_symbol(member_id, symbol)
        pending_unlocks = [
            self.equity_tax.optimal_sell_date(lot)
            for lot in same_symbol
            if lot.asset_class in {AssetClass.EQUITY, AssetClass.MF, AssetClass.US_EQUITY}
        ]
        pending_unlocks = [item for item in pending_unlocks if item.unlock_date and item.tax_delta_inr > 0]
        if pending_unlocks:
            best = sorted(pending_unlocks, key=lambda item: item.tax_delta_inr, reverse=True)[0]
            wait_recommendation = True
            recommendation = f"Waiting for the next LTCG unlock on {best.unlock_date.isoformat()} can improve post-tax proceeds."
            alternative = best.recommendation

        return {
            "sale_summary": {
                "symbol": symbol,
                "quantity": float(decimalize(quantity)),
                "current_price_inr": float(sale_slices[0].lot.current_price),
                "total_proceeds_inr": float(money(total_proceeds)),
            },
            "lot_breakdown": lot_breakdown,
            "tax_summary": {
                "total_gain_inr": float(money(decimalize(ltcg_gain) + decimalize(stcg_gain) + decimalize(crypto_gain))),
                "ltcg_this_transaction": float(money(ltcg_gain)),
                "ltcg_ytd_before_this": float(money(state.ltcg_realized_inr)),
                "ltcg_exemption_remaining": float(money(remaining_exemption)),
                "effective_ltcg_taxable": float(money(effective_ltcg_taxable)),
                "stcg_taxable": float(money(max(decimalize(stcg_gain), 0))),
                "total_tax_inr": float(money(total_tax)),
            },
            "advisory": {
                "wait_recommendation": wait_recommendation,
                "reason": recommendation,
                "alternative": alternative,
            },
        }

    def ltcg_calendar(self, window_days: int = 90) -> dict:
        assets = [
            asset
            for asset in self.repository.list_assets()
            if asset.asset_class in {AssetClass.EQUITY, AssetClass.MF, AssetClass.US_EQUITY}
        ]
        return {
            "events": self.tax_calendar.ltcg_unlock_events(assets, window_days=window_days),
            "window_days": window_days,
        }

    def tlh_opportunities(self) -> dict:
        opportunities = self.tlh_scanner.scan(self.repository.list_assets())
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
