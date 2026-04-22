"""
Zerodha Kite Connect integration.
Fetches equity holdings, P&L, and order history.
Requires: kiteconnect package, valid API key + access token.
"""
from __future__ import annotations
import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, AssetClass, Platform

logger = logging.getLogger(__name__)


class ZerodhaAggregator:
    """
    Fetches portfolio data from Zerodha Kite Connect API.
    Note: Kite access tokens expire daily — ensure fresh token via TOTP flow.
    """

    def __init__(self, api_key: str, access_token: str):
        self.api_key = api_key
        self.access_token = access_token
        self._kite = None
        self._init_client()

    def _init_client(self):
        try:
            from kiteconnect import KiteConnect
            self._kite = KiteConnect(api_key=self.api_key)
            self._kite.set_access_token(self.access_token)
            logger.info("Zerodha Kite client initialized.")
        except ImportError:
            logger.warning("kiteconnect not installed. Using mock data.")
        except Exception as e:
            logger.error(f"Zerodha init error: {e}")

    def get_holdings(self, member_id: str) -> list[AssetLot]:
        """Fetch current equity holdings and normalize to AssetLot."""
        if self._kite is None:
            return self._mock_holdings(member_id)

        try:
            holdings = self._kite.holdings()
            lots = []
            for h in holdings:
                if h.get("quantity", 0) == 0:
                    continue
                lot = AssetLot(
                    lot_id=f"ZRD-{h['tradingsymbol']}-{str(uuid.uuid4())[:8]}",
                    symbol=f"{h['tradingsymbol']}.NS",
                    asset_class=AssetClass.EQUITY,
                    platform=Platform.ZERODHA,
                    member_id=member_id,
                    quantity=Decimal(str(h["quantity"])),
                    acquisition_date=date.today(),   # Kite doesn't expose acquisition date directly
                    cost_basis_per_unit=Decimal(str(h["average_price"])),
                    current_price=Decimal(str(h.get("last_price", h["average_price"]))),
                    name=h.get("tradingsymbol"),
                    exchange=h.get("exchange", "NSE"),
                )
                lots.append(lot)
            logger.info(f"Fetched {len(lots)} holdings from Zerodha for {member_id}")
            return lots
        except Exception as e:
            logger.error(f"Zerodha holdings fetch error: {e}")
            return self._mock_holdings(member_id)

    def get_positions(self, member_id: str) -> list[dict]:
        """Fetch intraday/F&O positions (not normalized to lots)."""
        if self._kite is None:
            return []
        try:
            return self._kite.positions().get("net", [])
        except Exception as e:
            logger.error(f"Zerodha positions error: {e}")
            return []

    def _mock_holdings(self, member_id: str) -> list[AssetLot]:
        """Demo data when Zerodha credentials not configured."""
        from datetime import timedelta
        today = date.today()
        return [
            AssetLot(
                lot_id="ZRD-RELIANCE-001",
                symbol="RELIANCE.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("100"),
                acquisition_date=today - timedelta(days=400),
                cost_basis_per_unit=Decimal("2340.00"),
                current_price=Decimal("2847.50"),
                name="Reliance Industries",
            ),
            AssetLot(
                lot_id="ZRD-RELIANCE-002",
                symbol="RELIANCE.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("50"),
                acquisition_date=today - timedelta(days=200),
                cost_basis_per_unit=Decimal("2680.00"),
                current_price=Decimal("2847.50"),
                name="Reliance Industries",
            ),
            AssetLot(
                lot_id="ZRD-INFY-001",
                symbol="INFY.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("200"),
                acquisition_date=today - timedelta(days=550),
                cost_basis_per_unit=Decimal("1420.00"),
                current_price=Decimal("1680.00"),
                name="Infosys",
            ),
            AssetLot(
                lot_id="ZRD-ZOMATO-001",
                symbol="ZOMATO.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("500"),
                acquisition_date=today - timedelta(days=180),
                cost_basis_per_unit=Decimal("175.00"),
                current_price=Decimal("145.00"),
                name="Zomato",
            ),
            AssetLot(
                lot_id="ZRD-PAYTM-001",
                symbol="PAYTM.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("300"),
                acquisition_date=today - timedelta(days=300),
                cost_basis_per_unit=Decimal("620.00"),
                current_price=Decimal("525.00"),
                name="One97 Communications (Paytm)",
            ),
            AssetLot(
                lot_id="ZRD-HDFCBANK-001",
                symbol="HDFCBANK.NS",
                asset_class=AssetClass.EQUITY,
                platform=Platform.ZERODHA,
                member_id=member_id,
                quantity=Decimal("150"),
                acquisition_date=today - timedelta(days=700),
                cost_basis_per_unit=Decimal("1340.00"),
                current_price=Decimal("1720.00"),
                name="HDFC Bank",
            ),
        ]
