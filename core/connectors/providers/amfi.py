"""
AMFI (Association of Mutual Funds in India) Provider.
Fetches daily official NAVs and mutual fund scheme master data.
Public, official open data — zero authentication credentials required.
"""
from __future__ import annotations

import logging
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
)

logger = logging.getLogger(__name__)


class AMFIProvider(BaseConnector):
    """
    Public AMFI mutual fund data provider.
    Accesses free, public NAV data from MFAPI / AMFI India.
    """

    BASE_URL = "https://api.mfapi.in/mf"

    def __init__(self, member_id: str = "all") -> None:
        super().__init__(provider_id="amfi", member_id=member_id)
        self._session = requests.Session()
        self._cache: Dict[str, Decimal] = {}
        self._status = SyncStatus.CONNECTED

    def authenticate(self) -> bool:
        self._status = SyncStatus.CONNECTED
        return True

    def health_check(self) -> ConnectionHealth:
        start_time = datetime.utcnow()
        try:
            # Query a benchmark index scheme (e.g. HDFC Index Fund - Nifty 50: 101181)
            resp = self._session.get(f"{self.BASE_URL}/101181/latest", timeout=5)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            return ConnectionHealth(
                is_healthy=resp.status_code == 200,
                status=SyncStatus.CONNECTED if resp.status_code == 200 else SyncStatus.PROVIDER_UNAVAILABLE,
                message="AMFI NAV API reachable.",
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            return ConnectionHealth(
                is_healthy=False,
                status=SyncStatus.PROVIDER_UNAVAILABLE,
                message=str(e),
            )

    def get_nav(self, scheme_code: str) -> Optional[Decimal]:
        """Fetch latest NAV for an AMFI scheme code."""
        if scheme_code in self._cache:
            return self._cache[scheme_code]

        try:
            resp = self._session.get(f"{self.BASE_URL}/{scheme_code}/latest", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                data_list = data.get("data", [])
                if data_list:
                    nav_val = Decimal(str(data_list[0].get("nav", 0)))
                    self._cache[scheme_code] = nav_val
                    return nav_val
        except Exception as e:
            logger.debug("Failed to fetch AMFI NAV for %s: %s", scheme_code, e)
        return None

    def get_accounts(self) -> List[CanonicalAccount]:
        return [
            CanonicalAccount(
                provider="amfi",
                provider_account_id="public_directory",
                family_member_id=self.member_id,
                account_type="MUTUAL_FUND_PRICE_FEED",
                currency="INR",
                masked_identifier="AMFI-PUBLIC-FEED",
                status=SyncStatus.CONNECTED,
                last_synced_at=datetime.utcnow(),
            )
        ]

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        # AMFI is a pricing/directory provider, not a user brokerage account
        return []

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        return []

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        return []

    def disconnect(self) -> bool:
        self._cache.clear()
        return True
