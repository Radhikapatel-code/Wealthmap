"""
Binance Crypto Exchange Connector.
Implements BaseConnector for global crypto holdings and trade histories.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from core.aggregator.fx import get_fx_service
from core.connectors.base import BaseConnector
from core.connectors.models import (
    AssetType,
    CanonicalAccount,
    CanonicalAsset,
    CanonicalCashBalance,
    CanonicalHolding,
    CanonicalTransaction,
    ConnectionHealth,
    SyncStatus,
    TransactionType,
)

logger = logging.getLogger(__name__)


class BinanceConnector(BaseConnector):
    """
    Connects to Binance REST API using Read-Only API Key + Secret.
    Uses HMAC-SHA256 authenticated requests to fetch balances and trade history.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        member_id: str = "father",
        usd_inr_rate: Optional[Decimal] = None,
    ) -> None:
        super().__init__(provider_id="binance", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.api_secret = api_secret.strip() if api_secret else ""
        self._usd_inr_rate = usd_inr_rate
        self._client = None
        if self.api_key and self.api_secret:
            self._init_client()

    @property
    def usd_inr_rate(self) -> Decimal:
        if self._usd_inr_rate is not None:
            return self._usd_inr_rate
        return get_fx_service().get_usd_inr_rate()

    def _init_client(self) -> None:
        try:
            from binance.client import Client

            self._client = Client(self.api_key, self.api_secret)
            self._status = SyncStatus.CONNECTED
        except ImportError:
            logger.warning("python-binance library not installed.")
            self._client = None
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = "python-binance library not installed."
        except Exception as e:
            logger.error("Binance client initialization failed: %s", e)
            self._client = None
            self._status = SyncStatus.SYNC_FAILED
            self._last_error = str(e)

    def authenticate(self) -> bool:
        if not self.api_key or not self.api_secret:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing Binance API Key or Secret."
            return False

        if self._client is None:
            self._init_client()
            if self._client is None:
                return False

        try:
            # Test account status endpoint
            status_res = self._client.get_account_status()
            self._status = SyncStatus.CONNECTED
            self._last_error = None
            return True
        except Exception as e:
            err_msg = str(e)
            if "2015" in err_msg or "Invalid API-key" in err_msg or "Signature" in err_msg:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Invalid API Key, IP restriction, or signature mismatch."
            elif "429" in err_msg:
                self._status = SyncStatus.RATE_LIMITED
                self._last_error = "Binance rate limit exceeded."
            else:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"Binance connection failed: {err_msg}"
            return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        if not self.api_key or not self.api_secret:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="Credentials not provided.",
            )

        if self._client is None:
            return ConnectionHealth(
                is_healthy=False,
                status=self._status,
                message=self._last_error or "Binance client uninitialized.",
            )

        try:
            self._client.ping()
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            return ConnectionHealth(
                is_healthy=True,
                status=SyncStatus.CONNECTED,
                message="Binance API reachable and authenticated.",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_key = f"BNB-{self.api_key[:4]}****{self.api_key[-4:]}" if len(self.api_key) >= 8 else "BNB-WALLET"
        return [
            CanonicalAccount(
                provider="binance",
                provider_account_id=self.api_key[:12] if self.api_key else "default",
                family_member_id=self.member_id,
                account_type="CRYPTO_SPOT_WALLET",
                currency="USDT",
                masked_identifier=masked_key,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.api_key or not self.api_secret:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("Binance credentials not configured.")

        if self._client is None:
            self._init_client()
            if self._client is None:
                raise RuntimeError(self._last_error or "Binance client not available.")

        try:
            self._status = SyncStatus.SYNCING
            account = self._client.get_account()
            balances = [b for b in account["balances"] if float(b["free"]) + float(b["locked"]) > 0.000001]

            holdings: List[CanonicalHolding] = []
            fx_rate = self.usd_inr_rate

            for b in balances:
                asset_code = b["asset"]
                # Exclude fiat/stablecoins from asset holdings (they go to cash balances)
                if asset_code in ("USDT", "BUSD", "USDC", "USD", "EUR", "DAI"):
                    continue

                free_qty = Decimal(b["free"])
                locked_qty = Decimal(b["locked"])
                total_qty = free_qty + locked_qty
                if total_qty <= 0:
                    continue

                # Get live price in USDT -> convert to INR
                price_usdt = Decimal("0")
                try:
                    ticker = self._client.get_symbol_ticker(symbol=f"{asset_code}USDT")
                    price_usdt = Decimal(ticker["price"])
                except Exception:
                    # Attempt BTC pair fallback
                    try:
                        ticker = self._client.get_symbol_ticker(symbol=f"{asset_code}BTC")
                        btc_ticker = self._client.get_symbol_ticker(symbol="BTCUSDT")
                        price_usdt = Decimal(ticker["price"]) * Decimal(btc_ticker["price"])
                    except Exception:
                        price_usdt = Decimal("0")

                price_inr = (price_usdt * fx_rate).quantize(Decimal("0.01"))
                market_val_inr = (total_qty * price_inr).quantize(Decimal("0.01"))

                # Resolve cost basis from trade history
                cost_basis_per_unit = Decimal("0")
                acq_date = date.today()
                try:
                    trades = self._client.get_my_trades(symbol=f"{asset_code}USDT")
                    buy_trades = [t for t in trades if t.get("isBuyer", True)]
                    if buy_trades:
                        total_buy_qty = sum(Decimal(str(t["qty"])) for t in buy_trades)
                        total_buy_cost_usd = sum(Decimal(str(t["qty"])) * Decimal(str(t["price"])) for t in buy_trades)
                        if total_buy_qty > 0:
                            cost_basis_per_unit = ((total_buy_cost_usd / total_buy_qty) * fx_rate).quantize(Decimal("0.01"))
                        earliest_ts = min(t["time"] for t in buy_trades)
                        acq_date = date.fromtimestamp(earliest_ts / 1000)
                except Exception as te:
                    logger.debug("Binance trade history fetch note for %s: %s", asset_code, te)

                # Fallback: if no buy trades found, default cost basis to current price
                if cost_basis_per_unit == 0:
                    cost_basis_per_unit = price_inr

                asset = CanonicalAsset(
                    symbol=asset_code,
                    name=asset_code,
                    asset_type=AssetType.CRYPTO,
                    currency="INR",
                    exchange="BINANCE",
                    provider_asset_id=asset_code,
                )

                holdings.append(
                    CanonicalHolding(
                        holding_id=f"BNB-{account_id}-{asset_code}",
                        account_id=account_id,
                        asset=asset,
                        quantity=total_qty,
                        average_cost=cost_basis_per_unit,
                        cost_basis=total_qty * cost_basis_per_unit,
                        current_price=price_inr,
                        market_value=market_val_inr,
                        currency="INR",
                        acquisition_date=acq_date,
                    )
                )

            self._status = SyncStatus.SYNC_SUCCESS
            self._last_synced_at = datetime.utcnow()
            self._last_error = None
            return holdings

        except Exception as e:
            err_msg = str(e)
            if "2015" in err_msg or "Invalid API-key" in err_msg:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Binance API key expired or revoked."
            elif "429" in err_msg:
                self._status = SyncStatus.RATE_LIMITED
                self._last_error = "Binance rate limit hit."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"Binance holdings sync failed: {err_msg}"
            logger.error("Binance holdings sync error: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if self._client is None:
            return []

        try:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            transactions: List[CanonicalTransaction] = []
            fx_rate = self.usd_inr_rate

            for sym in symbols:
                try:
                    trades = self._client.get_my_trades(symbol=sym)
                    asset_symbol = sym.replace("USDT", "")
                    for t in trades:
                        tx_time = datetime.fromtimestamp(t["time"] / 1000)
                        if since and tx_time < since:
                            continue

                        qty = Decimal(str(t["qty"]))
                        price_usd = Decimal(str(t["price"]))
                        price_inr = (price_usd * fx_rate).quantize(Decimal("0.01"))
                        is_buy = t.get("isBuyer", True)

                        asset = CanonicalAsset(
                            symbol=asset_symbol,
                            name=asset_symbol,
                            asset_type=AssetType.CRYPTO,
                            currency="INR",
                            exchange="BINANCE",
                        )

                        transactions.append(
                            CanonicalTransaction(
                                transaction_id=f"BNB-TX-{t['id']}",
                                account_id=account_id,
                                asset=asset,
                                transaction_type=TransactionType.BUY if is_buy else TransactionType.SELL,
                                quantity=qty,
                                price=price_inr,
                                timestamp=tx_time,
                                currency="INR",
                                fees=Decimal(str(t.get("commission", 0))) * fx_rate,
                                provider_transaction_id=str(t["id"]),
                            )
                        )
                except Exception as sym_err:
                    logger.debug("Failed trades for %s: %s", sym, sym_err)

            return transactions
        except Exception as e:
            logger.error("Binance transactions fetch failed: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if self._client is None:
            return []
        try:
            account = self._client.get_account()
            fx_rate = self.usd_inr_rate
            cash_list: List[CanonicalCashBalance] = []

            for b in account.get("balances", []):
                asset = b["asset"]
                if asset in ("USDT", "USDC", "BUSD", "USD"):
                    avail = Decimal(str(b["free"]))
                    locked = Decimal(str(b["locked"]))
                    if avail + locked > Decimal("0.01"):
                        inr_val = (avail + locked) * fx_rate
                        cash_list.append(
                            CanonicalCashBalance(
                                account_id=account_id,
                                currency=asset,
                                available_balance=avail,
                                locked_balance=locked,
                                inr_equivalent=inr_val.quantize(Decimal("0.01")),
                            )
                        )
            return cash_list
        except Exception as e:
            logger.debug("Binance cash balance fetch note: %s", e)
            return []

    def disconnect(self) -> bool:
        self._client = None
        self.api_key = ""
        self.api_secret = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True
