"""
Portfolio Normalizer — unified entry point for all data sources.
Aggregates, deduplicates, and returns a clean PortfolioSnapshot.
"""
from __future__ import annotations
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, PortfolioSnapshot
from core.aggregator.zerodha import ZerodhaAggregator
from core.aggregator.binance import BinanceAggregator, CoinDCXAggregator
from core.aggregator.manual_import import ManualAssetImporter, YahooFinanceFeed
from config.settings import Settings

logger = logging.getLogger(__name__)


class PortfolioNormalizer:
    """
    Orchestrates all data sources and returns a unified PortfolioSnapshot
    for a given family member.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._zerodha: Optional[ZerodhaAggregator] = None
        self._binance: Optional[BinanceAggregator] = None
        self._coindcx: Optional[CoinDCXAggregator] = None
        self._manual = ManualAssetImporter()
        self._price_feed = YahooFinanceFeed()
        self._init_aggregators()

    def _init_aggregators(self):
        s = self.settings
        if s.kite_api_key and s.kite_access_token:
            self._zerodha = ZerodhaAggregator(s.kite_api_key, s.kite_access_token)
        else:
            logger.info("Zerodha credentials not configured — using mock data.")
            self._zerodha = ZerodhaAggregator("", "")

        if s.binance_api_key and s.binance_api_secret:
            self._binance = BinanceAggregator(s.binance_api_key, s.binance_api_secret)
        else:
            logger.info("Binance credentials not configured — using mock data.")
            self._binance = BinanceAggregator("", "")

        if s.coindcx_api_key and s.coindcx_api_secret:
            self._coindcx = CoinDCXAggregator(s.coindcx_api_key, s.coindcx_api_secret)
        else:
            self._coindcx = CoinDCXAggregator("", "")

    def build_snapshot(
        self,
        member_id: str,
        manual_assets: Optional[list[dict]] = None,
        update_prices: bool = True,
    ) -> PortfolioSnapshot:
        """
        Full portfolio snapshot for a member:
        1. Zerodha equity
        2. Binance crypto
        3. CoinDCX crypto
        4. Manual assets (FD, gold, US equity)
        5. Live price refresh (optional)
        """
        lots: list[AssetLot] = []

        # Equity from Zerodha
        try:
            equity_lots = self._zerodha.get_holdings(member_id)
            lots.extend(equity_lots)
            logger.info(f"[{member_id}] Zerodha: {len(equity_lots)} lots")
        except Exception as e:
            logger.error(f"Zerodha aggregation failed: {e}")

        # Crypto from Binance
        try:
            crypto_lots = self._binance.get_holdings(member_id)
            lots.extend(crypto_lots)
            logger.info(f"[{member_id}] Binance: {len(crypto_lots)} lots")
        except Exception as e:
            logger.error(f"Binance aggregation failed: {e}")

        # Crypto from CoinDCX
        try:
            coindcx_lots = self._coindcx.get_holdings(member_id)
            lots.extend(coindcx_lots)
            logger.info(f"[{member_id}] CoinDCX: {len(coindcx_lots)} lots")
        except Exception as e:
            logger.error(f"CoinDCX aggregation failed: {e}")

        # Manual assets
        if manual_assets:
            manual_lots = self._manual.import_from_json(manual_assets, member_id)
            lots.extend(manual_lots)
        else:
            # Use sample manual assets for demo
            sample_manual = self._manual.sample_manual_assets(member_id)
            lots.extend(sample_manual)
            logger.info(f"[{member_id}] Manual (sample): {len(sample_manual)} lots")

        # Refresh live prices
        if update_prices:
            try:
                lots = self._price_feed.update_lot_prices(lots)
            except Exception as e:
                logger.warning(f"Price refresh failed (using cached): {e}")

        logger.info(f"[{member_id}] Total lots: {len(lots)}")

        return PortfolioSnapshot(
            member_id=member_id,
            as_of=datetime.now(),
            lots=lots,
        )

    def build_demo_snapshot(self, member_id: str) -> PortfolioSnapshot:
        """Full demo snapshot with no API calls needed."""
        zerodha_mock = ZerodhaAggregator("", "")
        binance_mock = BinanceAggregator("", "")
        coindcx_mock = CoinDCXAggregator("", "")
        manual_mock = ManualAssetImporter()

        lots = (
            zerodha_mock._mock_holdings(member_id)
            + binance_mock._mock_holdings(member_id)
            + coindcx_mock.get_holdings(member_id)
            + manual_mock.sample_manual_assets(member_id)
        )

        return PortfolioSnapshot(
            member_id=member_id,
            as_of=datetime.now(),
            lots=lots,
            ytd_realized_ltcg=Decimal("87000"),
            ytd_realized_stcg=Decimal("23000"),
            ytd_realized_crypto_gain=Decimal("120000"),
            ytd_tax_paid=Decimal("52000"),
        )
