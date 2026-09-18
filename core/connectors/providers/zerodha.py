"""
Zerodha Kite Connect Connector.
Implements BaseConnector for Indian Equity and F&O accounts.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

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


class ZerodhaConnector(BaseConnector):
    """
    Connects to Zerodha Kite Connect API using API Key + Access Token.
    Note: Kite Connect access tokens expire daily at 6:00 AM IST.
    """

    def __init__(
        self,
        api_key: str,
        access_token: str,
        member_id: str = "father",
        client_id: Optional[str] = None,
    ) -> None:
        super().__init__(provider_id="zerodha", member_id=member_id)
        self.api_key = api_key.strip() if api_key else ""
        self.access_token = access_token.strip() if access_token else ""
        self.client_id = client_id or "KITE_ACCOUNT"
        self._kite = None
        if self.api_key and self.access_token:
            self._init_kite_client()

    def _init_kite_client(self) -> None:
        try:
            from kiteconnect import KiteConnect

            self._kite = KiteConnect(api_key=self.api_key)
            self._kite.set_access_token(self.access_token)
            self._status = SyncStatus.CONNECTED
        except ImportError:
            logger.warning("kiteconnect package not installed.")
            self._kite = None
            self._status = SyncStatus.PROVIDER_UNAVAILABLE
            self._last_error = "kiteconnect library is not installed."
        except Exception as e:
            logger.error("Failed to initialize Kite client: %s", e)
            self._kite = None
            self._status = SyncStatus.SYNC_FAILED
            self._last_error = str(e)

    def authenticate(self) -> bool:
        if not self.api_key or not self.access_token:
            self._status = SyncStatus.NOT_CONNECTED
            self._last_error = "Missing Zerodha API Key or Access Token."
            return False

        if self._kite is None:
            self._init_kite_client()
            if self._kite is None:
                return False

        try:
            profile = self._kite.profile()
            self.client_id = profile.get("user_id", self.client_id)
            self._status = SyncStatus.CONNECTED
            self._last_error = None
            return True
        except Exception as e:
            err_msg = str(e)
            if "TokenException" in type(e).__name__ or "token" in err_msg.lower():
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Kite access token has expired. Please regenerate daily token."
            else:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"Zerodha authentication failed: {err_msg}"
            return False

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        if not self.api_key or not self.access_token:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.NOT_CONNECTED,
                message="Credentials not provided.",
            )

        if self._kite is None:
            return ConnectionHealth(
                is_healthy=False,
                status=self._status,
                message=self._last_error or "Kite client not initialized.",
            )

        try:
            profile = self._kite.profile()
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            user_name = profile.get("user_name", "Zerodha User")
            return ConnectionHealth(
                is_healthy=True,
                status=SyncStatus.CONNECTED,
                message=f"Connected as {user_name} ({profile.get('user_id')})",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            err_msg = str(e)
            status = SyncStatus.AUTH_EXPIRED if "token" in err_msg.lower() else SyncStatus.PROVIDER_UNAVAILABLE
            return ConnectionHealth(
                is_healthy=False,
                status=status,
                message=err_msg,
            )

    def get_accounts(self) -> List[CanonicalAccount]:
        masked_id = f"KITE-{self.client_id[:2]}****{self.client_id[-2:]}" if len(self.client_id) >= 4 else "KITE-ACCOUNT"
        return [
            CanonicalAccount(
                provider="zerodha",
                provider_account_id=self.client_id,
                family_member_id=self.member_id,
                account_type="EQUITY_TRADING_AND_DEMAT",
                currency="INR",
                masked_identifier=masked_id,
                status=self._status,
                last_synced_at=self._last_synced_at,
                error_message=self._last_error,
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        if not self.api_key or not self.access_token:
            self._status = SyncStatus.NOT_CONNECTED
            raise RuntimeError("Zerodha credentials not configured.")

        if self._kite is None:
            self._init_kite_client()
            if self._kite is None:
                raise RuntimeError(self._last_error or "Kite client not initialized.")

        try:
            self._status = SyncStatus.SYNCING
            raw_holdings = self._kite.holdings()

            # Attempt to resolve purchase trade dates from recent tradebook
            trade_dates = {}
            try:
                trades = self._kite.trades()
                for t in trades:
                    tsym = t.get("tradingsymbol")
                    ttime = t.get("fill_timestamp") or t.get("order_timestamp") or t.get("exchange_timestamp")
                    if tsym and ttime:
                        d = ttime.date() if hasattr(ttime, "date") else date.fromisoformat(str(ttime)[:10])
                        if tsym not in trade_dates or d < trade_dates[tsym]:
                            trade_dates[tsym] = d
            except Exception as te:
                logger.debug("Kite trades fetch note: %s", te)

            canonical_holdings: List[CanonicalHolding] = []
            for h in raw_holdings:
                qty = Decimal(str(h.get("quantity", 0)))
                if qty <= 0:
                    continue

                tsym = h.get("tradingsymbol", "")
                isin = h.get("isin")
                exchange = h.get("exchange", "NSE")
                avg_price = Decimal(str(h.get("average_price", 0)))
                last_price = Decimal(str(h.get("last_price", avg_price)))
                market_val = Decimal(str(h.get("pnl", 0))) + (qty * avg_price) if "pnl" in h else (qty * last_price)

                # Determine acquisition date
                acq_date = trade_dates.get(tsym)
                if not acq_date and h.get("purchased_date"):
                    try:
                        acq_date = date.fromisoformat(str(h["purchased_date"])[:10])
                    except Exception:
                        pass
                if not acq_date and h.get("created_at"):
                    try:
                        acq_date = date.fromisoformat(str(h["created_at"])[:10])
                    except Exception:
                        pass
                if not acq_date:
                    acq_date = date.today()

                symbol_normalized = f"{tsym}.NS" if exchange == "NSE" and not tsym.endswith(".NS") else tsym
                asset = CanonicalAsset(
                    symbol=symbol_normalized,
                    name=h.get("instrument_name", tsym),
                    asset_type=AssetType.INDIAN_EQUITY,
                    currency="INR",
                    isin=isin,
                    exchange=exchange,
                    provider_asset_id=tsym,
                    metadata={"instrument_token": h.get("instrument_token")},
                )

                canonical_holdings.append(
                    CanonicalHolding(
                        holding_id=f"ZRD-{account_id}-{tsym}",
                        account_id=account_id,
                        asset=asset,
                        quantity=qty,
                        average_cost=avg_price,
                        cost_basis=qty * avg_price,
                        current_price=last_price,
                        market_value=qty * last_price,
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
            if "TokenException" in type(e).__name__ or "token" in err_msg.lower():
                self._status = SyncStatus.AUTH_EXPIRED
                self._last_error = "Zerodha access token expired. Re-authenticate to continue."
            elif "NetworkException" in type(e).__name__:
                self._status = SyncStatus.PROVIDER_UNAVAILABLE
                self._last_error = f"Zerodha network error: {err_msg}"
            else:
                self._status = SyncStatus.SYNC_FAILED
                self._last_error = f"Zerodha sync error: {err_msg}"
            logger.error("Zerodha holdings sync failed: %s", err_msg)
            raise

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        if self._kite is None:
            return []

        try:
            trades = self._kite.trades()
            transactions: List[CanonicalTransaction] = []
            for t in trades:
                ttime = t.get("fill_timestamp") or t.get("order_timestamp")
                tx_dt = ttime if isinstance(ttime, datetime) else datetime.fromisoformat(str(ttime))
                if since and tx_dt < since:
                    continue

                tsym = t.get("tradingsymbol", "")
                side = t.get("transaction_type", "BUY").upper()
                qty = Decimal(str(t.get("quantity", 0)))
                price = Decimal(str(t.get("average_price", 0)))

                asset = CanonicalAsset(
                    symbol=f"{tsym}.NS" if not tsym.endswith(".NS") else tsym,
                    name=tsym,
                    asset_type=AssetType.INDIAN_EQUITY,
                    currency="INR",
                    exchange=t.get("exchange", "NSE"),
                )

                transactions.append(
                    CanonicalTransaction(
                        transaction_id=str(t.get("trade_id", f"ZRD-TX-{tsym}-{tx_dt.timestamp()}")),
                        account_id=account_id,
                        asset=asset,
                        transaction_type=TransactionType.BUY if side == "BUY" else TransactionType.SELL,
                        quantity=qty,
                        price=price,
                        timestamp=tx_dt,
                        currency="INR",
                        provider_transaction_id=str(t.get("trade_id", "")),
                        notes=f"Order ID: {t.get('order_id')}",
                    )
                )
            return transactions
        except Exception as e:
            logger.error("Zerodha transactions fetch failed: %s", e)
            return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        if self._kite is None:
            return []
        try:
            margins = self._kite.margins("equity")
            avail = Decimal(str(margins.get("available", {}).get("cash", 0)))
            used = Decimal(str(margins.get("utilised", {}).get("debits", 0)))
            return [
                CanonicalCashBalance(
                    account_id=account_id,
                    currency="INR",
                    available_balance=avail,
                    locked_balance=used,
                    inr_equivalent=avail + used,
                )
            ]
        except Exception as e:
            logger.debug("Zerodha cash balance fetch note: %s", e)
            return []

    def disconnect(self) -> bool:
        self._kite = None
        self.access_token = ""
        self._status = SyncStatus.NOT_CONNECTED
        self._last_error = "Disconnected by user."
        return True
