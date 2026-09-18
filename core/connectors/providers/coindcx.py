"""
CoinDCX Indian Crypto Exchange Connector.
Implements BaseConnector for CoinDCX accounts with HMAC-SHA256 signed REST calls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
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


class CoinDCXConnector(BaseConnector):
    """
    Connects to CoinDCX API using API Key + Secret.
    Executes HMAC-SHA256 authenticated REST calls for balances and trades.
    """

    BASE_URL = "https://api.coindcx.com"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        member_id: str = "father",
    ) -> None:
        super().__init__(provider_id="coindcx", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.api_secret = api_secret.strip() if api_secret else ""
        self._session = requests.Session()
        if self.api_key and self.api_secret:
            self._status = SyncStatus.CONNECTED

    def _generate_signature(self, json_body: str) -> str:
        return hmac.new(
            self.api_secret.encode("utf-8"),
            json_body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _post(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Any:
        payload = data or {}
        payload["timestamp"] = int(round(time.time() * 1000))
        json_body = json.dumps(payload, separators=(",", ":"))
        signature = self._generate_signature(json_body)

        headers = {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

        url = f"{self.BASE_URL}{endpoint}"
        resp = self._session.post(url, data=json_body, headers=headers, timeout=10)

        if resp.status_code == 401 or resp.status_code == 403:
            self._status = SyncStatus.AUTH_EXPIRED
            self._last_error = f"CoinDCX authentication failed ({resp.status_code}). Check API credentials."
            raise PermissionError(self._last_error)
        elif resp.status_code == 429:
            self._status = SyncStatus.RATE_LIMITED
            self._last_error = "CoinDCX rate limit reached."
            raise RuntimeError(self._last_error)

        resp.raise_for_status()
        return resp.json()

    def _get_public(self, endpoint: str) -> Any:
        url = f"{self.BASE_URL}{endpoint}"
        resp = self._session.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def authenticate(self) -> bool:
        if not self.api_key or not self.api_secret:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing CoinDCX API Key or Secret."
            return False

        try:
            # CoinDCX user info / balances check
            self._post("/exchange/v1/users/info")
            self._status = SyncStatus.CONNECTED
            self._last_error = None
            return True
        except PermissionError:
            return False
        except Exception as e:
            # If /users/info is restricted, test /exchange/v1/users/balances
            try:
                self._post("/exchange/v1/users/balances")
                self._status = SyncStatus.CONNECTED
                self._last_error = None
                return True
            except Exception as e2:
                err_str = str(e2)
                if "401" in err_str or "403" in err_str:
                    self._status = SyncStatus.AUTH_EXPIRED
                    self._last_error = "CoinDCX credentials expired or invalid."
                else:
                    self._status = SyncStatus.PROVIDER_UNAVAILABLE
                    self._last_error = f"CoinDCX connection failed: {err_str}"
                return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        if not self.api_key or not self.api_secret:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="CoinDCX credentials not provided.",
            )

        try:
            # Test public ping/ticker first
            self._get_public("/exchange/ticker")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            return ConnectionHealth(
                is_healthy=True,
                status=SyncStatus.CONNECTED,
                message="CoinDCX API reachable.",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_key = f"CDX-{self.api_key[:4]}****{self.api_key[-4:]}" if len(self.api_key) >= 8 else "CDX-WALLET"
        return [
            CanonicalAccount(
                provider="coindcx",
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
            raise RuntimeError("CoinDCX credentials not configured.")

        try:
            self._status = SyncStatus.SYNCING
            raw_balances = self._post("/exchange/v1/users/balances")

            # Fetch public tickers for INR prices
            tickers_list = []
            try:
                tickers_list = self._get_public("/exchange/ticker")
            except Exception as te:
                logger.debug("CoinDCX ticker fetch note: %s", te)

            ticker_map = {}
            for t in tickers_list:
                market = t.get("market", "")
                last_p = t.get("last_price")
                if market and last_p:
                    ticker_map[market.upper()] = Decimal(str(last_p))

            holdings: List[CanonicalHolding] = []
            for item in raw_balances:
                asset_code = item.get("currency", "").upper()
                if not asset_code or asset_code in ("INR", "USDT"):
                    continue

                balance = Decimal(str(item.get("balance", 0)))
                locked = Decimal(str(item.get("locked_balance", 0)))
                total_qty = balance + locked
                if total_qty <= Decimal("0.000001"):
                    continue

                # CoinDCX INR pair price
                inr_pair = f"{asset_code}INR"
                current_price = ticker_map.get(inr_pair, Decimal("0"))
                if current_price == 0:
                    # fallback to USDT pair
                    usdt_pair = f"{asset_code}USDT"
                    if usdt_pair in ticker_map and "USDTINR" in ticker_map:
                        current_price = ticker_map[usdt_pair] * ticker_map["USDTINR"]

                # Cost basis fallback to current price if no historical trades present
                cost_basis = current_price

                asset = CanonicalAsset(
                    symbol=asset_code,
                    name=asset_code,
                    asset_type=AssetType.CRYPTO,
                    currency="INR",
                    exchange="COINDCX",
                    provider_asset_id=asset_code,
                )

                holdings.append(
                    CanonicalHolding(
                        holding_id=f"CDX-{account_id}-{asset_code}",
                        account_id=account_id,
                        asset=asset,
                        quantity=total_qty,
                        average_cost=cost_basis,
                        cost_basis=(total_qty * cost_basis).quantize(Decimal("0.01")),
                        current_price=current_price,
                        market_value=(total_qty * current_price).quantize(Decimal("0.01")),
                        currency="INR",
                        acquisition_date=date.today(),
                    )
                )

            self._status = SyncStatus.SYNC_SUCCESS
            self._last_synced_at = datetime.utcnow()
            self._last_error = None
            return holdings

        except Exception as e:
            err_msg = str(e)
            if "authentication" in err_msg.lower() or "401" in err_msg:
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "CoinDCX API credentials expired or revoked."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"CoinDCX holdings sync failed: {err_msg}"
            logger.error("CoinDCX holdings sync error: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if not self.api_key or not self.api_secret:
            return []

        try:
            payload = {"limit": 100}
            raw_trades = self._post("/exchange/v1/orders/trade_history", payload)
            transactions: List[CanonicalTransaction] = []

            for t in raw_trades:
                ts_ms = t.get("timestamp") or t.get("created_at")
                tx_time = datetime.fromtimestamp(ts_ms / 1000) if ts_ms else datetime.utcnow()
                if since and tx_time < since:
                    continue

                symbol = t.get("symbol", "").upper().replace("INR", "").replace("USDT", "")
                side = t.get("side", "buy").upper()
                qty = Decimal(str(t.get("quantity", 0)))
                price = Decimal(str(t.get("price", 0)))
                fee = Decimal(str(t.get("fee_amount", 0)))

                asset = CanonicalAsset(
                    symbol=symbol,
                    name=symbol,
                    asset_type=AssetType.CRYPTO,
                    currency="INR",
                    exchange="COINDCX",
                )

                transactions.append(
                    CanonicalTransaction(
                        transaction_id=f"CDX-TX-{t.get('id', tx_time.timestamp())}",
                        account_id=account_id,
                        asset=asset,
                        transaction_type=TransactionType.BUY if side == "BUY" else TransactionType.SELL,
                        quantity=qty,
                        price=price,
                        timestamp=tx_time,
                        currency="INR",
                        fees=fee,
                        provider_transaction_id=str(t.get("id", "")),
                    )
                )

            return transactions
        except Exception as e:
            logger.debug("CoinDCX trade history fetch note: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if not self.api_key or not self.api_secret:
            return []

        try:
            raw_balances = self._post("/exchange/v1/users/balances")
            cash_list: List[CanonicalCashBalance] = []

            for item in raw_balances:
                curr = item.get("currency", "").upper()
                if curr in ("INR", "USDT"):
                    avail = Decimal(str(item.get("balance", 0)))
                    locked = Decimal(str(item.get("locked_balance", 0)))
                    if avail + locked > 0:
                        cash_list.append(
                            CanonicalCashBalance(
                                account_id=account_id,
                                currency=curr,
                                available_balance=avail,
                                locked_balance=locked,
                                inr_equivalent=(avail + locked) if curr == "INR" else None,
                            )
                        )
            return cash_list
        except Exception as e:
            logger.debug("CoinDCX cash balances error: %s", e)
            return []

    def disconnect(self) -> bool:
        self.api_key = ""
        self.api_secret = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True
