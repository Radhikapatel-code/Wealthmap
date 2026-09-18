"""
Canonical data models for WealthMap multi-provider connector layer.
All monetary and quantity fields use Decimal for financial precision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class SyncStatus(str, Enum):
    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    SYNC_SUCCESS = "SYNC_SUCCESS"
    SYNC_FAILED = "SYNC_FAILED"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PARTIAL_SYNC = "PARTIAL_SYNC"
    NOT_CONNECTED = "NOT_CONNECTED"


class AssetType(str, Enum):
    INDIAN_EQUITY = "INDIAN_EQUITY"
    US_EQUITY = "US_EQUITY"
    MUTUAL_FUND = "MUTUAL_FUND"
    ETF = "ETF"
    CRYPTO = "CRYPTO"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    BOND = "BOND"
    GOLD = "GOLD"
    CASH = "CASH"
    REAL_ESTATE = "REAL_ESTATE"
    OTHER = "OTHER"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    OTHER = "OTHER"


@dataclass
class ConnectionHealth:
    is_healthy: bool
    status: SyncStatus
    message: str
    last_checked_at: datetime = field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None
    rate_limit_remaining: Optional[int] = None


@dataclass
class CanonicalAsset:
    symbol: str
    name: str
    asset_type: AssetType
    currency: str = "INR"
    isin: Optional[str] = None
    exchange: Optional[str] = None
    provider_asset_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        """Stable deduplication identifier across providers."""
        if self.isin:
            return f"ISIN:{self.isin}"
        if self.exchange:
            return f"{self.exchange}:{self.symbol}"
        return f"{self.asset_type.value}:{self.symbol}"


@dataclass
class CanonicalAccount:
    provider: str
    provider_account_id: str
    family_member_id: str
    account_type: str
    currency: str = "INR"
    masked_identifier: str = ""
    status: SyncStatus = SyncStatus.NOT_CONNECTED
    last_synced_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def account_id(self) -> str:
        return f"{self.provider}_{self.provider_account_id}"


@dataclass
class CanonicalHolding:
    holding_id: str
    account_id: str
    asset: CanonicalAsset
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    current_price: Decimal
    market_value: Decimal
    currency: str = "INR"
    as_of: datetime = field(default_factory=datetime.utcnow)
    acquisition_date: Optional[date] = None
    grandfathered_cost: Optional[Decimal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalTransaction:
    transaction_id: str
    account_id: str
    asset: CanonicalAsset
    transaction_type: TransactionType
    quantity: Decimal
    price: Decimal
    timestamp: datetime
    currency: str = "INR"
    fees: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    settlement_date: Optional[date] = None
    provider_transaction_id: Optional[str] = None
    notes: Optional[str] = None
    is_internal_transfer: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def gross_amount(self) -> Decimal:
        return self.quantity * self.price

    @property
    def net_amount(self) -> Decimal:
        if self.transaction_type in (TransactionType.BUY, TransactionType.DEPOSIT):
            return self.gross_amount + self.fees + self.taxes
        elif self.transaction_type in (TransactionType.SELL, TransactionType.WITHDRAWAL, TransactionType.DIVIDEND, TransactionType.INTEREST):
            return self.gross_amount - self.fees - self.taxes
        return self.gross_amount


@dataclass
class CanonicalCashBalance:
    account_id: str
    currency: str
    available_balance: Decimal
    locked_balance: Decimal = Decimal("0")
    inr_equivalent: Optional[Decimal] = None
    as_of: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_balance(self) -> Decimal:
        return self.available_balance + self.locked_balance


@dataclass
class SyncResult:
    account_id: str
    provider: str
    status: SyncStatus
    holdings_count: int
    transactions_count: int
    synced_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    cash_balances: List[CanonicalCashBalance] = field(default_factory=list)
