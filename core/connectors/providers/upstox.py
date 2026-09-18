"""
Upstox UpLink API v2 Connector.
Implements BaseConnector for Indian Equity and F&O accounts with OAuth 2.0 authentication.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

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


class UpstoxConnector(BaseConnector):
    """
    Connects to Upstox UpLink API v2 using OAuth 2.0 authentication.
    Upstox offers free API access with OAuth 2.0 flow and 24-hour token validity.
    """

    BASE_URL = "https://api.upstox.com/v2"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        redirect_uri: str,
        member_id: str = "father",
        access_token: Optional[str] = None,
    ) -> None:
        super().__init__(provider_id="upstox", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.api_secret = api_secret.strip() if api_secret else ""
        self.redirect_uri = redirect_uri.strip() if redirect_uri else ""
        self.access_token = access_token.strip() if access_token else ""
        self._session = requests.Session()
        
        if self.api_key and self.api_secret and self.redirect_uri:
            self._status = SyncStatus.CONNECTED
        elif self.access_token:
            self._status = SyncStatus.CONNECTED

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def authenticate(self) -> bool:
        """Validate access token or initiate OAuth flow."""
        if not self.access_token:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "No access token provided. Complete OAuth 2.0 flow first."
            return False

        try:
            # Test token validity by fetching profile
            response = self._session.get(
                f"{self.BASE_URL}/user/profile",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                self._status = SyncStatus.CONNECTED
                self._last_error = None
                return True
            elif response.status_code == 401:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Upstox access token expired. Re-authenticate via OAuth 2.0."
                return False
            else:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"Upstox authentication failed: {response.status_code}"
                return False
                
        except Exception as e:
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = f"Upstox connection error: {str(e)}"
            return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        
        if not self.access_token:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="No access token provided. Complete OAuth 2.0 flow first.",
            )

        try:
            response = self._session.get(
                f"{self.BASE_URL}/user/profile",
                headers=self._headers(),
                timeout=10
            )
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response.status_code == 200:
                profile = response.json()
                client_id = profile.get("data", {}).get("client_id", "Upstox User")
                return ConnectionHealth(
                    is_healthy=True,
                    status=SyncStatus.CONNECTED,
                    message=f"Connected to Upstox as {client_id}",
                    latency_ms=round(latency, 2),
                )
            else:
                status = SyncStatus.AUTH_EXPIRED if response.status_code == 401 else SyncStatus.PROVIDER_UNAVAILABLE
                return ConnectionHealth(
                    is_healthy=False,
                    status=status,
                    message=f"Upstox health check failed: {response.status_code}",
                )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_key = f"UPS-{self.api_key[:4]}****{self.api_key[-4:]}" if len(self.api_key) >= 8 else "UPS-ACCOUNT"
        return [
            CanonicalAccount(
                provider="upstox",
                provider_account_id=self.api_key[:12] if self.api_key else "default",
                family_member_id=self.member_id,
                account_type="EQUITY_TRADING_AND_DEMAT",
                currency="INR",
                masked_identifier=masked_key,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.access_token:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("Upstox access token not configured.")

        try:
            self._status = SyncStatus.SYNCING
            
            # Fetch holdings
            response = self._session.get(
                f"{self.BASE_URL}/portfolio/long-term-holdings",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                error_msg = f"Upstox holdings fetch failed: {response.status_code}"
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = error_msg
                raise RuntimeError(error_msg)
            
            data = response.json()
            holdings_data = data.get("data", [])
            
            canonical_holdings: List[CanonicalHolding] = []
            
            for item in holdings_data:
                trading_symbol = item.get("trading_symbol", "")
                quantity = Decimal(str(item.get("quantity", 0)))
                if quantity <= 0:
                    continue
                
                isin = item.get("isin")
                exchange = item.get("exchange", "NSE")
                avg_price = Decimal(str(item.get("average_price", 0)))
                last_price = Decimal(str(item.get("last_price", avg_price)))
                
                # Determine acquisition date from portfolio endpoint
                acq_date = date.today()
                try:
                    portfolio_response = self._session.get(
                        f"{self.BASE_URL}/portfolio/positions",
                        headers=self._headers(),
                        timeout=10
                    )
                    if portfolio_response.status_code == 200:
                        portfolio_data = portfolio_response.json()
                        # Try to find matching position with date
                        for pos in portfolio_data.get("data", []):
                            if pos.get("trading_symbol") == trading_symbol:
                                day_cf = pos.get("day_cf")
                                if day_cf:
                                    try:
                                        acq_date = datetime.strptime(day_cf[:10], "%Y-%m-%d").date()
                                    except Exception:
                                        pass
                                break
                except Exception as de:
                    logger.debug("Upstox portfolio fetch note: %s", de)
                
                symbol_normalized = f"{trading_symbol}.NS" if exchange == "NSE" and not trading_symbol.endswith(".NS") else trading_symbol
                
                asset = CanonicalAsset(
                    symbol=symbol_normalized,
                    name=item.get("instrument_name", trading_symbol),
                    asset_type=AssetType.INDIAN_EQUITY,
                    currency="INR",
                    isin=isin,
                    exchange=exchange,
                    provider_asset_id=trading_symbol,
                    metadata={"instrument_token": item.get("instrument_token")},
                )
                
                canonical_holdings.append(
                    CanonicalHolding(
                        holding_id=f"UPS-{account_id}-{trading_symbol}",
                        account_id=account_id,
                        asset=asset,
                        quantity=quantity,
                        average_cost=avg_price,
                        cost_basis=quantity * avg_price,
                        current_price=last_price,
                        market_value=quantity * last_price,
                        currency="INR",
                        as_of=datetime.utcnow(),
                        acquisition_date=acq_date,
                    )
                )
            
            self._status = SyncStatus.SYNC_SUCCESS
            self._last_synced_at = datetime.utcnow()
            self._last_error = None
            return canonical_holdings
            
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "token" in err_msg.lower():
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Upstox access token expired. Re-authenticate via OAuth 2.0."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"Upstox holdings sync error: {err_msg}"
            logger.error("Upstox holdings sync failed: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if not self.access_token:
            return []
        
        try:
            # Fetch trade book
            response = self._session.get(
                f"{self.BASE_URL}/order/trade-book",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.debug("Upstox trade book fetch failed: %s", response.status_code)
                return []
            
            data = response.json()
            trades_data = data.get("data", [])
            
            transactions: List[CanonicalTransaction] = []
            
            for trade in trades_data:
                trade_time_str = trade.get("exchange_trade_time") or trade.get("order_timestamp")
                if not trade_time_str:
                    continue
                    
                try:
                    trade_time = datetime.strptime(trade_time_str[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                    
                if since and trade_time < since:
                    continue
                
                trading_symbol = trade.get("trading_symbol", "")
                side = trade.get("transaction_type", "BUY").upper()
                quantity = Decimal(str(trade.get("quantity", 0)))
                price = Decimal(str(trade.get("price", 0)))
                
                exchange = trade.get("exchange", "NSE")
                symbol_normalized = f"{trading_symbol}.NS" if exchange == "NSE" and not trading_symbol.endswith(".NS") else trading_symbol
                
                asset = CanonicalAsset(
                    symbol=symbol_normalized,
                    name=trading_symbol,
                    asset_type=AssetType.INDIAN_EQUITY,
                    currency="INR",
                    exchange=exchange,
                )
                
                transactions.append(
                    CanonicalTransaction(
                        transaction_id=str(trade.get("trade_id", f"UPS-TX-{trade_time.timestamp()}")),
                        account_id=account_id,
                        asset=asset,
                        transaction_type=TransactionType.BUY if side == "BUY" else TransactionType.SELL,
                        quantity=quantity,
                        price=price,
                        timestamp=trade_time,
                        currency="INR",
                        provider_transaction_id=str(trade.get("trade_id", "")),
                        notes=f"Order ID: {trade.get('order_id')}",
                    )
                )
            
            return transactions
            
        except Exception as e:
            logger.error("Upstox transactions fetch failed: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if not self.access_token:
            return []
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/user/balance",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.debug("Upstox balance fetch failed: %s", response.status_code)
                return []
            
            data = response.json()
            balance_data = data.get("data", {})
            
            avail_balance = Decimal(str(balance_data.get("available_margin", {}).get("cash", 0)))
            used_balance = Decimal(str(balance_data.get("utilized_margin", {}).get("cash", 0)))
            
            return [
                CanonicalCashBalance(
                    account_id=account_id,
                    currency="INR",
                    available_balance=avail_balance,
                    locked_balance=used_balance,
                    inr_equivalent=avail_balance + used_balance,
                )
            ]
        except Exception as e:
            logger.debug("Upstox cash balance fetch note: %s", e)
            return []

    def disconnect(self) -> bool:
        self.access_token = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True