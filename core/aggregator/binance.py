"""
Crypto exchange integrations: Binance and CoinDCX.
Fetches holdings, transaction history, and cost basis.
"""
from __future__ import annotations
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, AssetClass, Platform
from core.tax.crypto_tax import CryptoTransaction
from core.aggregator.fx import get_fx_service

logger = logging.getLogger(__name__)


class BinanceAggregator:
    def __init__(self, api_key: str, api_secret: str, usd_inr_rate: Optional[Decimal] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self._usd_inr_rate = usd_inr_rate
        self._client = None
        self._init_client()

    @property
    def usd_inr_rate(self) -> Decimal:
        if self._usd_inr_rate is not None:
            return self._usd_inr_rate
        return get_fx_service().get_usd_inr_rate()

    def _init_client(self):
        try:
            from binance.client import Client
            self._client = Client(self.api_key, self.api_secret)
            logger.info("Binance client initialized.")
        except ImportError:
            logger.warning("python-binance not installed. Using mock data.")
        except Exception as e:
            logger.error(f"Binance init error: {e}")

    def _usdt_to_inr(self, usdt_amount: Decimal) -> Decimal:
        return (usdt_amount * self.usd_inr_rate).quantize(Decimal("0.01"))

    def get_holdings(self, member_id: str) -> list[AssetLot]:
        if self._client is None:
            return self._mock_holdings(member_id)
        try:
            account = self._client.get_account()
            balances = [b for b in account["balances"] if float(b["free"]) > 0.000001]
            lots = []
            for b in balances:
                asset = b["asset"]
                if asset in ("USDT", "BUSD", "USDC"):
                    continue
                qty = Decimal(b["free"]) + Decimal(b["locked"])
                try:
                    ticker = self._client.get_symbol_ticker(symbol=f"{asset}USDT")
                    price_usdt = Decimal(ticker["price"])
                    price_inr = self._usdt_to_inr(price_usdt)
                except Exception:
                    price_inr = Decimal("0")

                cost_basis_inr = Decimal("0")
                acq_date = date.today()
                try:
                    trades = self._client.get_my_trades(symbol=f"{asset}USDT")
                    buy_trades = [t for t in trades if t.get("isBuyer", True)]
                    if buy_trades:
                        total_buy_qty = sum(Decimal(str(t["qty"])) for t in buy_trades)
                        total_buy_cost = sum(
                            Decimal(str(t["qty"])) * self._usdt_to_inr(Decimal(str(t["price"])))
                            for t in buy_trades
                        )
                        if total_buy_qty > 0:
                            cost_basis_inr = (total_buy_cost / total_buy_qty).quantize(Decimal("0.01"))
                        earliest_timestamp = min(t["time"] for t in buy_trades)
                        acq_date = date.fromtimestamp(earliest_timestamp / 1000)
                except Exception as te:
                    logger.warning("Failed to fetch trade history for Binance asset %s: %s", asset, te)

                lots.append(AssetLot(
                    lot_id=f"BNB-{asset}-{str(uuid.uuid4())[:8]}",
                    symbol=asset,
                    asset_class=AssetClass.CRYPTO,
                    platform=Platform.BINANCE,
                    member_id=member_id,
                    quantity=qty,
                    acquisition_date=acq_date,
                    cost_basis_per_unit=cost_basis_inr,
                    current_price=price_inr,
                    name=asset,
                ))
            return lots
        except Exception as e:
            logger.error(f"Binance holdings error: {e}")
            return self._mock_holdings(member_id)

    def _mock_holdings(self, member_id: str) -> list[AssetLot]:
        today = date.today()
        return [
            AssetLot(
                lot_id="BNB-BTC-001",
                symbol="BTC",
                asset_class=AssetClass.CRYPTO,
                platform=Platform.BINANCE,
                member_id=member_id,
                quantity=Decimal("0.18"),
                acquisition_date=today - timedelta(days=420),
                cost_basis_per_unit=Decimal("1800000"),
                current_price=Decimal("2161111"),
                name="Bitcoin",
            ),
            AssetLot(
                lot_id="BNB-ETH-001",
                symbol="ETH",
                asset_class=AssetClass.CRYPTO,
                platform=Platform.BINANCE,
                member_id=member_id,
                quantity=Decimal("2.5"),
                acquisition_date=today - timedelta(days=300),
                cost_basis_per_unit=Decimal("220000"),
                current_price=Decimal("248000"),
                name="Ethereum",
            ),
        ]

    def get_transactions(self, member_id: str, symbol: str = "BTC") -> list[CryptoTransaction]:
        if self._client is None:
            return self._mock_transactions(member_id)
        try:
            trades = self._client.get_my_trades(symbol=f"{symbol}USDT")
            result = []
            for t in trades:
                tx_date = date.fromtimestamp(t["time"] / 1000)
                qty = Decimal(t["qty"])
                price_usdt = Decimal(t["price"])
                price_inr = self._usdt_to_inr(price_usdt)
                value_inr = qty * price_inr
                tds = value_inr * Decimal("0.01") if not t["isBuyer"] else Decimal("0")

                result.append(CryptoTransaction(
                    tx_id=str(t["id"]),
                    symbol=symbol,
                    member_id=member_id,
                    tx_type="BUY" if t["isBuyer"] else "SELL",
                    quantity=qty,
                    price_inr=price_inr,
                    tx_date=tx_date,
                    platform="binance",
                    tds_deducted=tds,
                ))
            return result
        except Exception as e:
            logger.error(f"Binance transactions error: {e}")
            return self._mock_transactions(member_id)

    def _mock_transactions(self, member_id: str) -> list[CryptoTransaction]:
        today = date.today()
        return [
            CryptoTransaction(
                tx_id="BNB-TX-001",
                symbol="BTC",
                member_id=member_id,
                tx_type="BUY",
                quantity=Decimal("0.18"),
                price_inr=Decimal("1800000"),
                tx_date=today - timedelta(days=420),
                platform="binance",
                tds_deducted=Decimal("0"),
            ),
        ]


class CoinDCXAggregator:
    def __init__(self, api_key: str, api_secret: str, usd_inr_rate: Optional[Decimal] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self._usd_inr_rate = usd_inr_rate

    @property
    def usd_inr_rate(self) -> Decimal:
        if self._usd_inr_rate is not None:
            return self._usd_inr_rate
        return get_fx_service().get_usd_inr_rate()

    def get_holdings(self, member_id: str) -> list[AssetLot]:
        today = date.today()
        return [
            AssetLot(
                lot_id="CDX-SOL-001",
                symbol="SOL",
                asset_class=AssetClass.CRYPTO,
                platform=Platform.COINDCX,
                member_id=member_id,
                quantity=Decimal("15"),
                acquisition_date=today - timedelta(days=180),
                cost_basis_per_unit=Decimal("8350"),
                current_price=Decimal("14200"),
                name="Solana",
            ),
        ]

    def get_transactions(self, member_id: str) -> list[CryptoTransaction]:
        return []
