"""
Alpaca US Equity Connector.
Implements BaseConnector for US equities held by Indian HNIs via RBI LRS.
"""
from __future__ import annotations

import logging
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


class AlpacaConnector(BaseConnector):
    """
    Connects to Alpaca Trading API for US equities and ETFs.
    Authenticates via APCA-API-KEY-ID and APCA-API-SECRET-KEY headers.
    """

    DEFAULT_BASE_URL = "https://api.alpaca.markets"

    def __init__(
        self,
        api_key_id: str,
        secret_key: str,
        member_id: str = "father",
        base_url: Optional[str] = None,
        usd_inr_rate: Optional[Decimal] = None,
    ) -> None:
        super().__init__(provider_id="alpaca", member_id=member_id)
        self.api_key_id = api_key_id.strip() if api_key_id else ""
        self.secret_key = secret_key.strip() if secret_key else ""
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self._usd_inr_rate = usd_inr_rate
        self._session = requests.Session()
        if self.api_key_id and self.secret_key:
            self._status = SyncStatus.CONNECTED

    @property
    def usd_inr_rate(self) -> Decimal:
        if self._usd_inr_rate is not None:
            return self._usd_inr_rate
        return get_fx_service().get_usd_inr_rate()

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Accept": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(url, headers=self._headers(), params=params, timeout=10)

        if resp.status_code == 401 or resp.status_code == 403:
            self._status = SyncStatus.AUTH_EXPIRED
            self._last_error = f"Alpaca authentication failed ({resp.status_code})."
            raise PermissionError(self._last_error)
        elif resp.status_code == 429:
            self._status = SyncStatus.RATE_LIMITED
            self._last_error = "Alpaca rate limit exceeded."
            raise RuntimeError(self._last_error)

        resp.raise_for_status()
        return resp.json()

    def authenticate(self) -> bool:
        if not self.api_key_id or not self.secret_key:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing Alpaca API Key ID or Secret Key."
            return False

        try:
            acc = self._get("/v2/account")
            self._status = SyncStatus.CONNECTED
            self._last_error = None
            return True
        except PermissionError:
            return False
        except Exception as e:
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = f"Alpaca connection failed: {e}"
            return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        if not self.api_key_id or not self.secret_key:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="Credentials not provided.",
            )

        try:
            acc = self._get("/v2/account")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            acc_num = acc.get("account_number", "Alpaca")
            status_str = acc.get("status", "ACTIVE")
            return ConnectionHealth(
                is_healthy=True,
                status=SyncStatus.CONNECTED,
                message=f"Connected to Alpaca account #{acc_num} (Status: {status_str})",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_id = f"ALPAC-{self.api_key_id[:4]}****{self.api_key_id[-4:]}" if len(self.api_key_id) >= 8 else "ALPAC-ACC"
        return [
            CanonicalAccount(
                provider="alpaca",
                provider_account_id=self.api_key_id[:12] if self.api_key_id else "default",
                family_member_id=self.member_id,
                account_type="US_EQUITY_BROKERAGE",
                currency="USD",
                masked_identifier=masked_id,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.api_key_id or not self.secret_key:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("Alpaca credentials not configured.")

        try:
            self._status = SyncStatus.SYNCING
            raw_positions = self._get("/v2/positions")
            fx_rate = self.usd_inr_rate

            holdings: List[CanonicalHolding] = []
            for p in raw_positions:
                sym = p.get("symbol", "").upper()
                qty = Decimal(str(p.get("qty", 0)))
                avg_entry_usd = Decimal(str(p.get("avg_entry_price", 0)))
                current_price_usd = Decimal(str(p.get("current_price", avg_entry_usd)))

                avg_entry_inr = (avg_entry_usd * fx_rate).quantize(Decimal("0.01"))
                current_price_inr = (current_price_usd * fx_rate).quantize(Decimal("0.01"))
                market_val_inr = (qty * current_price_inr).quantize(Decimal("0.01"))

                asset = CanonicalAsset(
                    symbol=f"{sym}.US",
                    name=sym,
                    asset_type=AssetType.US_EQUITY,
                    currency="USD",
                    exchange=p.get("exchange", "NASDAQ"),
                    provider_asset_id=sym,
                )

                holdings.append(
                    CanonicalHolding(
                        holding_id=f"ALPAC-{account_id}-{sym}",
                        account_id=account_id,
                        asset=asset,
                        quantity=qty,
                        average_cost=avg_entry_inr,
                        cost_basis=qty * avg_entry_inr,
                        current_price=current_price_inr,
                        market_value=market_val_inr,
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
                self._last_error = "Alpaca API credentials invalid or revoked."
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"Alpaca holdings sync failed: {err_msg}"
            logger.error("Alpaca sync failed: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if not self.api_key_id or not self.secret_key:
            return []

        try:
            params = {"activity_types": "FILL,DIV,TRANS", "direction": "desc"}
            if since:
                params["after"] = since.isoformat()

            activities = self._get("/v2/account/activities", params=params)
            fx_rate = self.usd_inr_rate
            transactions: List[CanonicalTransaction] = []

            for act in activities:
                act_type = act.get("activity_type", "")
                tx_dt_str = act.get("transaction_time") or act.get("date")
                tx_dt = datetime.fromisoformat(tx_dt_str.replace("Z", "+00:00")) if tx_dt_str else datetime.utcnow()

                sym = act.get("symbol", "")
                qty = Decimal(str(act.get("qty", 0)))
                price_usd = Decimal(str(act.get("price", 0)))
                price_inr = (price_usd * fx_rate).quantize(Decimal("0.01"))
                side = act.get("side", "").upper()

                ttype = TransactionType.OTHER
                if act_type == "FILL":
                    ttype = TransactionType.BUY if side == "BUY" else TransactionType.SELL
                elif act_type == "DIV":
                    ttype = TransactionType.DIVIDEND
                elif act_type == "TRANS":
                    ttype = TransactionType.TRANSFER

                asset = CanonicalAsset(
                    symbol=f"{sym}.US" if sym else "USD_CASH",
                    name=sym or "USD Cash",
                    asset_type=AssetType.US_EQUITY if sym else AssetType.CASH,
                    currency="USD",
                )

                transactions.append(
                    CanonicalTransaction(
                        transaction_id=str(act.get("id", tx_dt.timestamp())),
                        account_id=account_id,
                        asset=asset,
                        transaction_type=ttype,
                        quantity=qty,
                        price=price_inr,
                        timestamp=tx_dt,
                        currency="INR",
                        provider_transaction_id=str(act.get("id", "")),
                    )
                )

            return transactions
        except Exception as e:
            logger.debug("Alpaca activities fetch note: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if not self.api_key_id or not self.secret_key:
            return []

        try:
            acc = self._get("/v2/account")
            fx_rate = self.usd_inr_rate
            cash_usd = Decimal(str(acc.get("cash", 0)))
            cash_inr = (cash_usd * fx_rate).quantize(Decimal("0.01"))

            return [
                CanonicalCashBalance(
                    account_id=account_id,
                    currency="USD",
                    available_balance=cash_usd,
                    locked_balance=Decimal("0"),
                    inr_equivalent=cash_inr,
                )
            ]
        except Exception as e:
            logger.debug("Alpaca cash balance note: %s", e)
            return []

    def disconnect(self) -> bool:
        self.api_key_id = ""
        self.secret_key = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True
