"""
Standard Base Connector Interface for WealthMap.
All external financial integrations implement this contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from core.connectors.models import (
    CanonicalAccount,
    CanonicalCashBalance,
    CanonicalHolding,
    CanonicalTransaction,
    ConnectionHealth,
    SyncStatus,
)


class BaseConnector(ABC):
    """
    Base contract for all external portfolio data providers.
    Adapters must normalize provider-specific responses into WealthMap Canonical Models.
    Provider-specific raw response structures must NEVER leak outside the adapter.
    """

    def __init__(self, provider_id: str, member_id: str, read_only: bool = True) -> None:
        self.provider_id = provider_id
        self.member_id = member_id
        self.read_only = read_only
        self._status: SyncStatus = SyncStatus.NOT_CONNECTED
        self._last_error: Optional[str] = None
        self._last_synced_at: Optional[datetime] = None

    @property
    def status(self) -> SyncStatus:
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def last_synced_at(self) -> Optional[datetime]:
        return self._last_synced_at

    @abstractmethod
    def authenticate(self) -> bool:
        """
        Validate credentials against the provider API.
        Sets self._status to CONNECTED on success, or AUTH_EXPIRED / PROVIDER_UNAVAILABLE on failure.
        """
        pass

    @abstractmethod
    def health_check(self) -> ConnectionHealth:
        """
        Ping the provider API to verify connectivity, latency, and token validity.
        """
        pass

    @abstractmethod
    def get_accounts(self) -> List[CanonicalAccount]:
        """
        Discover accounts/demats/wallets linked to the provided credentials.
        """
        pass

    @abstractmethod
    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        """
        Fetch all current positions/holdings for an account, normalized to CanonicalHolding.
        """
        pass

    @abstractmethod
    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        """
        Fetch transaction / order history, incrementally if 'since' timestamp is provided.
        """
        pass

    @abstractmethod
    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        """
        Fetch available and locked cash / fiat / margin balances.
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Invalidate session tokens or remove client state cleanly.
        """
        pass
