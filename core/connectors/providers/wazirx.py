"""
WazirX Crypto Exchange Connector.
Implements BaseConnector for Indian crypto exchange with HMAC-SHA256 authentication.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

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


class WazirXConnector(BaseConnector):
    """
    Connects to WazirX REST API using HMAC-SHA256 authentication.
    WazirX is an Indian crypto exchange with INR trading pairs.
    """

    BASE_URL = "https://api.wazirx.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        member_id: str = "father",
        usd_inr_rate: Optional[Decimal] = None,
    ) -> None:
        super().__init__(provider_id="wazirx", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.api_secret = api_secret.strip() if api_secret else ""
        self._usd_inr_rate = usd_inr_rate
        self._session = requests.Session()
        
        if self.api_key and self.api_secret:
            self._status = SyncStatus.CONNECTED

    @property
    def usd_inr_rate(self) -> Decimal:
        if self._usd_inr_rate is not None:
            return self._usd_inr_rate
        return get_fx_service().get_usd_inr_rate()

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC-SHA256 signature for WazirX API."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self) -> Dict[str, str]:
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    def authenticate(self) -> bool:
        """Validate API credentials."""
        if not self.api_key or not self.api_secret:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing WazirX API Key or Secret."
            return False

        try:
            # Test account endpoint
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = self._generate_signature(query_string)
            
            response = self._session.get(
                f"{self.BASE_URL}/sapi/v1/account?",
                params={
                    "timestamp": timestamp,
                    "signature": signature,
                },
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                self._status = SyncStatus.CONNECTED
                self._last_error = None
                return True
            elif response.status_code == 401:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Invalid WazirX API Key or Secret."
                return False
            else:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"WazirX authentication failed: {response.status_code}"
                return False
                
        except Exception as e:
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = f"WazirX connection error: {str(e)}"
            return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        
        if not self.api_key or not self.api_secret:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="WazirX credentials not provided.",
            )

        try:
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = self._generate_signature(query_string)
            
            response = self._session.get(
                f"{self.BASE_URL}/sapi/v1/account?",
                params={
                    "timestamp": timestamp,
                    "signature": signature,
                },
                headers=self._headers(),
                timeout=10
            )
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response.status_code == 200:
                account_data = response.json()
                return ConnectionHealth(
                    is_healthy=True,
                    status=SyncStatus.CONNECTED,
                    message="WazirX API reachable and authenticated.",
                    latency_ms=round(latency, 2),
                )
            else:
                status = SyncStatus.AUTH_EXPIRED if response.status_code == 401 else SyncStatus.PROVIDER_UNAVAILABLE
                return ConnectionHealth(
                    is_healthy=False,
                    status=status,
                    message=f"WazirX health check failed: {response.status_code}",
                )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_key = f"WRX-{self.api_key[:4]}****{self.api_key[-4:]}" if len(self.api_key) >= 8 else "WRX-WALLET"
        return [
            CanonicalAccount(
                provider="wazirx",
                provider_account_id=self.api_key[:12] if self.api_key else "default",
                family_member_id=self.member_id,
                account_type="CRYPTO_INR_WALLET",
                currency="INR",
                masked_identifier=masked_key,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.api_key or not self.api_secret:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("WazirX credentials not configured.")

        try:
            self._status = SyncStatus.SYNCING
            
            # Fetch account snapshot
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = self._generate_signature(query_string)
            
            response = self._session.get(
                f"{self.BASE_URL}/sapi/v1/account?",
                params={
                    "timestamp": timestamp,
                    "signature": signature,
                },
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                error_msg = f"WazirX account fetch failed: {response.status_code}"
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = error_msg
                raise RuntimeError(error_msg)
            
            account_data = response.json()
            balances = account_data.get("balances", [])
            
            holdings: List[CanonicalHolding] = []
            fx_rate = self.usd_inr_rate
            
            for balance in balances:
                asset_code = balance.get("asset", "")
                # Exclude stablecoins from holdings (they go to cash)
                if asset_code in ("USDT", "BUSD", "USDC", "USD", "INR"):
                    continue
                
                free_qty = Decimal(str(balance.get("free", 0)))
                locked_qty = Decimal(str(balance.get("locked", 0)))
                total_qty = free_qty + locked_qty
                
                if total_qty <= Decimal("0.000001"):
                    continue
                
                # Get live price
                current_price = Decimal("0")
                try:
                    # Try INR pair first
                    ticker_response = self._session.get(
                        f"{self.BASE_URL}/sapi/v1/ticker/price",
                        params={"symbol": f"{asset_code}INR"},
                        timeout=5
                    )
                    if ticker_response.status_code == 200:
                        ticker_data = ticker_response.json()
                        current_price = Decimal(str(ticker_data.get("price", 0)))
                    else:
                        # Fallback to USDT pair
                        usdt_ticker = self._session.get(
                            f"{self.BASE_URL}/sapi/v1/ticker/price",
                            params={"symbol": f"{asset_code}USDT"},
                            timeout=5
                        )
                        if usdt_ticker.status_code == 200:
                            usdt_data = usdt_ticker.json()
                            usdt_price = Decimal(str(usdt_data.get("price", 0)))
                            current_price = (usdt_price * fx_rate).quantize(Decimal("0.01"))
                except Exception as pe:
                    logger.debug("WazirX price fetch note for %s: %s", asset_code, pe)
                
                # Resolve cost basis from trade history
                cost_basis_per_unit = Decimal("0")
                acq_date = date.today()
                try:
                    trade_timestamp = int(time.time() * 1000)
                    trade_query = f"symbol={asset_code}INR&timestamp={trade_timestamp}"
                    trade_signature = self._generate_signature(trade_query)
                    
                    trades_response = self._session.get(
                        f"{self.BASE_URL}/sapi/v1/myTrades?",
                        params={
                            "symbol": f"{asset_code}INR",
                            "timestamp": trade_timestamp,
                            "signature": trade_signature,
                        },
                        headers=self._headers(),
                        timeout=10
                    )
                    
                    if trades_response.status_code == 200:
                        trades = trades_response.json()
                        buy_trades = [t for t in trades if t.get("isBuyer", True)]
                        if buy_trades:
                            total_buy_qty = sum(Decimal(str(t["qty"])) for t in buy_trades)
                            total_buy_cost = sum(
                                Decimal(str(t["qty"])) * Decimal(str(t["price"]))
                                for t in buy_trades
                            )
                            if total_buy_qty > 0:
                                cost_basis_per_unit = (total_buy_cost / total_buy_qty).quantize(Decimal("0.01"))
                            earliest_timestamp = min(t["time"] for t in buy_trades)
                            acq_date = date.fromtimestamp(earliest_timestamp / 1000)
                except Exception as te:
                    logger.debug("WazirX trade history fetch note for %s: %s", asset_code, te)
                
                # Fallback to current price if no cost basis
                if cost_basis_per_unit == 0:
                    cost_basis_per_unit = current_price
                
                asset = CanonicalAsset(
                    symbol=asset_code,
                    name=asset_code,
                    asset_type=AssetType.CRYPTO,
                    currency="INR",
                    exchange="WAZIRX",
                    provider_asset_id=asset_code,
                )
                
                holdings.append(
                    CanonicalHolding(
                        holding_id=f"WRX-{account_id}-{asset_code}",
                        account_id=account_id,
                        asset=asset,
                        quantity=total_qty,
                        average_cost=cost_basis_per_unit,
                        cost_basis=total_qty * cost_basis_per_unit,
                        current_price=current_price,
                        market_value=total_qty * current_price,
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
            if "401" in err_msg or "Invalid" in err_msg:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "WazirX API credentials expired or invalid."
            elif "429" in err_msg:
                self._status = SyncStatus.RATE_LIMITED
                self._last_error = "WazirX rate limit hit."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"WazirX holdings sync failed: {err_msg}"
            logger.error("WazirX holdings sync error: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if not self.api_key or not self.api_secret:
            return []
        
        try:
            # Fetch trade history for major INR pairs
            symbols = ["BTCINR", "ETHINR", "SOLINR", "XRPINR"]
            transactions: List[CanonicalTransaction] = []
            fx_rate = self.usd_inr_rate
            
            for symbol in symbols:
                try:
                    timestamp = int(time.time() * 1000)
                    query_string = f"symbol={symbol}&timestamp={timestamp}"
                    signature = self._generate_signature(query_string)
                    
                    response = self._session.get(
                        f"{self.BASE_URL}/sapi/v1/myTrades?",
                        params={
                            "symbol": symbol,
                            "timestamp": timestamp,
                            "signature": signature,
                        },
                        headers=self._headers(),
                        timeout=10
                    )
                    
                    if response.status_code != 200:
                        continue
                        
                    trades = response.json()
                    asset_symbol = symbol.replace("INR", "")
                    
                    for trade in trades:
                        tx_time = datetime.fromtimestamp(trade["time"] / 1000)
                        if since and tx_time < since:
                            continue
                        
                        qty = Decimal(str(trade["qty"]))
                        price_inr = Decimal(str(trade["price"]))
                        is_buy = trade.get("isBuyer", True)
                        
                        asset = CanonicalAsset(
                            symbol=asset_symbol,
                            name=asset_symbol,
                            asset_type=AssetType.CRYPTO,
                            currency="INR",
                            exchange="WAZIRX",
                        )
                        
                        transactions.append(
                            CanonicalTransaction(
                                transaction_id=f"WRX-TX-{trade['id']}",
                                account_id=account_id,
                                asset=asset,
                                transaction_type=TransactionType.BUY if is_buy else TransactionType.SELL,
                                quantity=qty,
                                price=price_inr,
                                timestamp=tx_time,
                                currency="INR",
                                fees=Decimal(str(trade.get("commission", 0))),
                                provider_transaction_id=str(trade["id"]),
                            )
                        )
                except Exception as sym_err:
                    logger.debug("Failed trades for %s: %s", symbol, sym_err)
            
            return transactions
            
        except Exception as e:
            logger.error("WazirX transactions fetch failed: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if not self.api_key or not self.api_secret:
            return []
        
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = self._generate_signature(query_string)
            
            response = self._session.get(
                f"{self.BASE_URL}/sapi/v1/account?",
                params={
                    "timestamp": timestamp,
                    "signature": signature,
                },
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.debug("WazirX account fetch failed: %s", response.status_code)
                return []
            
            account_data = response.json()
            balances = account_data.get("balances", [])
            cash_list: List[CanonicalCashBalance] = []
            fx_rate = self.usd_inr_rate
            
            for balance in balances:
                asset = balance.get("asset", "")
                if asset in ("INR", "USDT", "USDC", "BUSD"):
                    avail = Decimal(str(balance.get("free", 0)))
                    locked = Decimal(str(balance.get("locked", 0)))
                    if avail + locked > Decimal("0.01"):
                        inr_val = (avail + locked) if asset == "INR" else (avail + locked) * fx_rate
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
            logger.debug("WazirX cash balance fetch note: %s", e)
            return []

    def disconnect(self) -> bool:
        self.api_key = ""
        self.api_secret = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True