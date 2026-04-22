"""
Manual asset import for FDs, gold, real estate, and US equity.
Also Yahoo Finance price feed for Indian equities.
"""
from __future__ import annotations
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, AssetClass, Platform

logger = logging.getLogger(__name__)


class ManualAssetImporter:
    """
    Handles manually specified assets: FDs, physical gold, real estate, US equity.
    These don't have API connections — user provides structured JSON.
    """

    def import_fd(self, data: dict, member_id: str) -> AssetLot:
        return AssetLot(
            lot_id=data.get("lot_id", f"FD-{str(uuid.uuid4())[:8]}"),
            symbol=f"FD-{data.get('bank', 'BANK')}",
            asset_class=AssetClass.FIXED_DEPOSIT,
            platform=Platform.MANUAL,
            member_id=member_id,
            quantity=Decimal("1"),
            acquisition_date=date.fromisoformat(data["start_date"]),
            cost_basis_per_unit=Decimal(str(data["principal_inr"])),
            current_price=Decimal(str(data.get("maturity_value_inr", data["principal_inr"]))),
            name=f"{data.get('bank', 'FD')} FD @ {data.get('interest_rate_pct', '?')}%",
            isin=None,
        )

    def import_gold(self, data: dict, member_id: str) -> AssetLot:
        grams = Decimal(str(data["quantity_grams"]))
        current_price_per_gram = Decimal(str(data.get("current_price_per_gram_inr", 6200)))
        cost_per_gram = Decimal(str(data["cost_per_gram_inr"]))

        return AssetLot(
            lot_id=data.get("lot_id", f"GOLD-{str(uuid.uuid4())[:8]}"),
            symbol="GOLD_PHYSICAL",
            asset_class=AssetClass.GOLD,
            platform=Platform.MANUAL,
            member_id=member_id,
            quantity=grams,
            acquisition_date=date.fromisoformat(data["purchase_date"]),
            cost_basis_per_unit=cost_per_gram,
            current_price=current_price_per_gram,
            name=f"Physical Gold ({float(grams):.0f}g)",
        )

    def import_us_equity(self, data: dict, member_id: str) -> AssetLot:
        usd_inr = Decimal(str(data.get("usd_inr_rate", 83.5)))
        return AssetLot(
            lot_id=data.get("lot_id", f"US-{str(uuid.uuid4())[:8]}"),
            symbol=f"{data['symbol']}.US",
            asset_class=AssetClass.US_EQUITY,
            platform=Platform.MANUAL,
            member_id=member_id,
            quantity=Decimal(str(data["quantity"])),
            acquisition_date=date.fromisoformat(data["acquisition_date"]),
            cost_basis_per_unit=Decimal(str(data["cost_basis_usd"])) * usd_inr,
            current_price=Decimal(str(data["current_price_usd"])) * usd_inr,
            name=data.get("name", data["symbol"]),
        )

    def import_from_json(self, assets: list[dict], member_id: str) -> list[AssetLot]:
        lots = []
        for asset in assets:
            asset_type = asset.get("type", "").upper()
            try:
                if asset_type == "FD":
                    lots.append(self.import_fd(asset, member_id))
                elif asset_type == "GOLD":
                    lots.append(self.import_gold(asset, member_id))
                elif asset_type == "US_EQUITY":
                    lots.append(self.import_us_equity(asset, member_id))
            except Exception as e:
                logger.error(f"Failed to import asset {asset}: {e}")
        return lots

    def sample_manual_assets(self, member_id: str) -> list[AssetLot]:
        today = date.today()
        return [
            AssetLot(
                lot_id="FD-HDFC-001",
                symbol="FD-HDFC",
                asset_class=AssetClass.FIXED_DEPOSIT,
                platform=Platform.MANUAL,
                member_id=member_id,
                quantity=Decimal("1"),
                acquisition_date=today - timedelta(days=200),
                cost_basis_per_unit=Decimal("3000000"),
                current_price=Decimal("3180000"),    # ₹30L principal + accrued interest
                name="HDFC Bank FD @ 7.1%",
            ),
            AssetLot(
                lot_id="GOLD-001",
                symbol="GOLD_PHYSICAL",
                asset_class=AssetClass.GOLD,
                platform=Platform.MANUAL,
                member_id=member_id,
                quantity=Decimal("100"),             # 100 grams
                acquisition_date=today - timedelta(days=900),
                cost_basis_per_unit=Decimal("4800"), # ₹4,800/g cost
                current_price=Decimal("6200"),        # ₹6,200/g current
                name="Physical Gold (100g)",
            ),
        ]


class YahooFinanceFeed:
    """
    Live price feed via yfinance for Indian equities.
    Adds .NS suffix for NSE, .BO for BSE.
    """

    def get_price(self, symbol: str) -> Optional[Decimal]:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                return Decimal(str(price)).quantize(Decimal("0.01"))
        except Exception as e:
            logger.error(f"yfinance price fetch error for {symbol}: {e}")
        return None

    def update_lot_prices(self, lots: list[AssetLot]) -> list[AssetLot]:
        """Batch update current prices for equity lots."""
        equity_symbols = list({
            lot.symbol for lot in lots
            if lot.asset_class in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND)
        })

        prices: dict[str, Decimal] = {}
        for sym in equity_symbols:
            price = self.get_price(sym)
            if price:
                prices[sym] = price

        updated = []
        for lot in lots:
            if lot.symbol in prices:
                from dataclasses import replace
                lot = AssetLot(
                    lot_id=lot.lot_id,
                    symbol=lot.symbol,
                    asset_class=lot.asset_class,
                    platform=lot.platform,
                    member_id=lot.member_id,
                    quantity=lot.quantity,
                    acquisition_date=lot.acquisition_date,
                    cost_basis_per_unit=lot.cost_basis_per_unit,
                    current_price=prices[lot.symbol],
                    grandfathered_cost=lot.grandfathered_cost,
                    isin=lot.isin,
                    name=lot.name,
                )
            updated.append(lot)
        return updated
