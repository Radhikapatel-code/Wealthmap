"""
Angel One SmartAPI Connector.
Implements BaseConnector for Indian Equity and F&O accounts with TOTP authentication.
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


class AngelOneConnector(BaseConnector):
    """
    Connects to Angel One SmartAPI using API Key + TOTP authentication.
    SmartAPI is completely free with session validity till midnight.
    """

    BASE_URL = "https://apiconnect.angelone.in"

    def __init__(
        self,
        api_key: str,
        client_code: str,
        password: str,
        totp_secret: Optional[str] = None,
        member_id: str = "father",
        jwt_token: Optional[str] = None,
    ) -> None:
        super().__init__(provider_id="angel_one", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.client_code = client_code.strip() if client_code else ""
        self.password = password.strip() if password else ""
        self.totp_secret = totp_secret.strip() if totp_secret else ""
        self.jwt_token = jwt_token.strip() if jwt_token else ""
        self._session = requests.Session()
        
        if self.api_key and self.client_code and self.password:
            self._status = SyncStatus.CONNECTED
        elif self.jwt_token:
            self._status = SyncStatus.CONNECTED

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self.api_key,
        }
        if self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        return headers

    def authenticate(self) -> bool:
        """Authenticate with Angel One using credentials or validate existing JWT token."""
        if self.jwt_token:
            # Validate existing token
            try:
                response = self._session.get(
                    f"{self.BASE_URL}/rest/secure/angelbroking/user/v1/getProfile",
                    headers=self._headers(),
                    timeout=10
                )
                
                if response.status_code == 200:
                    self._status = SyncStatus.CONNECTED
                    self._last_error = None
                    return True
                elif response.status_code == 401:
                    self._status = SyncStatus.AUTH_EXPIRED
                    self._last_error = "Angel One JWT token expired. Re-authenticate."
                    return False
                else:
                    self._status = SyncStatus.PROVIDER_UNAVAILABLE
                    self._last_error = f"Angel One auth failed: {response.status_code}"
                    return False
            except Exception as e:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"Angel One connection error: {str(e)}"
                return False
        
        # Need to authenticate with credentials
        if not self.api_key or not self.client_code or not self.password:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing Angel One API Key, Client Code, or Password."
            return False
        
        try:
            # Login with credentials
            payload = {
                "clientcode": self.client_code,
                "password": self.password,
                "totp": self._generate_totp() if self.totp_secret else "",
                "state": "live"
            }
            
            response = self._session.post(
                f"{self.BASE_URL}/rest/auth/angelbroking/user/v1/loginByPassword",
                headers=self._headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.jwt_token = data.get("data", {}).get("jwtToken", "")
                if self.jwt_token:
                    self._status = SyncStatus.CONNECTED
                    self._last_error = None
                    return True
                else:
                    self._status = SyncStatus.SYNC_FAILED
                    self._last_error = "Angel One login successful but no JWT token received."
                    return False
            else:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = f"Angel One authentication failed: {response.status_code}"
                return False
                
        except Exception as e:
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = f"Angel One authentication error: {str(e)}"
            return False

    def _generate_totp(self) -> str:
        """Generate TOTP code if TOTP secret is provided."""
        if not self.totp_secret:
            return ""
        
        try:
            import pyotp
            totp = pyotp.TOTP(self.totp_secret)
            return totp.now()
        except ImportError:
            logger.warning("pyotp library not installed. TOTP generation not available.")
            return ""
        except Exception as e:
            logger.warning("TOTP generation failed: %s", e)
            return ""

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        
        if not self.jwt_token and not (self.api_key and self.client_code and self.password):
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="No credentials or JWT token provided.",
            )

        try:
            if not self.jwt_token:
                self.authenticate()
            
            response = self._session.get(
                f"{self.BASE_URL}/rest/secure/angelbroking/user/v1/getProfile",
                headers=self._headers(),
                timeout=10
            )
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if response.status_code == 200:
                profile = response.json()
                client_id = profile.get("data", {}).get("clientcode", "Angel One User")
                return ConnectionHealth(
                    is_healthy=True,
                    status=SyncStatus.CONNECTED,
                    message=f"Connected to Angel One as {client_id}",
                    latency_ms=round(latency, 2),
                )
            else:
                status = SyncStatus.AUTH_EXPIRED if response.status_code == 401 else SyncStatus.PROVIDER_UNAVAILABLE
                return ConnectionHealth(
                    is_healthy=False,
                    status=status,
                    message=f"Angel One health check failed: {response.status_code}",
                )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_code = f"ANG-{self.client_code[:2]}****{self.client_code[-2:]}" if len(self.client_code) >= 4 else "ANG-ACCOUNT"
        return [
            CanonicalAccount(
                provider="angel_one",
                provider_account_id=self.client_code,
                family_member_id=self.member_id,
                account_type="EQUITY_TRADING_AND_DEMAT",
                currency="INR",
                masked_identifier=masked_code,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.jwt_token:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("Angel One JWT token not configured.")

        try:
            self._status = SyncStatus.SYNCING
            
            # Fetch holdings
            response = self._session.get(
                f"{self.BASE_URL}/rest/secure/angelbroking/portfolio/v1/getHolding",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                error_msg = f"Angel One holdings fetch failed: {response.status_code}"
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = error_msg
                raise RuntimeError(error_msg)
            
            data = response.json()
            holdings_data = data.get("data", [])
            
            canonical_holdings: List[CanonicalHolding] = []
            
            for item in holdings_data:
                trading_symbol = item.get("tradingsymbol", "")
                quantity = Decimal(str(item.get("quantity", 0)))
                if quantity <= 0:
                    continue
                
                isin = item.get("isin")
                exchange = item.get("exchange", "NSE")
                avg_price = Decimal(str(item.get("averageprice", 0)))
                last_price = Decimal(str(item.get("ltp", avg_price)))
                
                # Angel One doesn't provide acquisition date in holdings, use trade book
                acq_date = date.today()
                try:
                    trade_response = self._session.get(
                        f"{self.BASE_URL}/rest/secure/angelbroking/order/v1/getTradeBook",
                        headers=self._headers(),
                        timeout=10
                    )
                    if trade_response.status_code == 200:
                        trade_data = trade_response.json()
                        for trade in trade_data.get("data", []):
                            if trade.get("tradingsymbol") == trading_symbol:
                                trade_time = trade.get("orderdatetime")
                                if trade_time:
                                    try:
                                        acq_date = datetime.strptime(trade_time[:10], "%Y-%m-%d").date()
                                        break
                                    except Exception:
                                        pass
                except Exception as de:
                    logger.debug("Angel One trade book fetch note: %s", de)
                
                symbol_normalized = f"{trading_symbol}.NS" if exchange == "NSE" and not trading_symbol.endswith(".NS") else trading_symbol
                
                asset = CanonicalAsset(
                    symbol=symbol_normalized,
                    name=item.get("name", trading_symbol),
                    asset_type=AssetType.INDIAN_EQUITY,
                    currency="INR",
                    isin=isin,
                    exchange=exchange,
                    provider_asset_id=trading_symbol,
                    metadata={"symboltoken": item.get("symboltoken")},
                )
                
                canonical_holdings.append(
                    CanonicalHolding(
                        holding_id=f"ANG-{account_id}-{trading_symbol}",
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
                self._last_error = "Angel One JWT token expired. Re-authenticate."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"Angel One holdings sync error: {err_msg}"
            logger.error("Angel One holdings sync failed: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if not self.jwt_token:
            return []
        
        try:
            # Fetch trade book
            response = self._session.get(
                f"{self.BASE_URL}/rest/secure/angelbroking/order/v1/getTradeBook",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.debug("Angel One trade book fetch failed: %s", response.status_code)
                return []
            
            data = response.json()
            trades_data = data.get("data", [])
            
            transactions: List[CanonicalTransaction] = []
            
            for trade in trades_data:
                trade_time_str = trade.get("orderdatetime")
                if not trade_time_str:
                    continue
                    
                try:
                    trade_time = datetime.strptime(trade_time_str[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                    
                if since and trade_time < since:
                    continue
                
                trading_symbol = trade.get("tradingsymbol", "")
                side = trade.get("transactiontype", "BUY").upper()
                quantity = Decimal(str(trade.get("tradedquantity", 0)))
                price = Decimal(str(trade.get("tradedprice", 0)))
                
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
                        transaction_id=str(trade.get("exchangeordernumber", f"ANG-TX-{trade_time.timestamp()}")),
                        account_id=account_id,
                        asset=asset,
                        transaction_type=TransactionType.BUY if side == "BUY" else TransactionType.SELL,
                        quantity=quantity,
                        price=price,
                        timestamp=trade_time,
                        currency="INR",
                        provider_transaction_id=str(trade.get("exchangeordernumber", "")),
                        notes=f"Order ID: {trade.get('ordernumber')}",
                    )
                )
            
            return transactions
            
        except Exception as e:
            logger.error("Angel One transactions fetch failed: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if not self.jwt_token:
            return []
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/rest/secure/angelbroking/user/v1/getRMS",
                headers=self._headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                logger.debug("Angel One balance fetch failed: %s", response.status_code)
                return []
            
            data = response.json()
            balance_data = data.get("data", {})
            
            avail_balance = Decimal(str(balance_data.get("netavailablemargin", {}).get("cash", 0)))
            used_balance = Decimal(str(balance_data.get("utilizedmargin", {}).get("cash", 0)))
            
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
            logger.debug("Angel One cash balance fetch note: %s", e)
            return []

    def disconnect(self) -> bool:
        self.jwt_token = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True