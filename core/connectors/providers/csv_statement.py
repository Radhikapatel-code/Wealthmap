"""
Statement / CSV Import Connector.
Standardized ingestion for providers without retail APIs (Groww, CAMS, KFintech CAS, Bank Statements).
Normalizes statement exports into WealthMap Canonical models with lot-level fidelity.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

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


class CSVStatementConnector(BaseConnector):
    """
    Ingests and normalizes CSV/Excel statement exports from brokers and mutual fund registrars.
    Preserves exact transaction dates, quantities, prices, ISINs, and folios.
    """

    def __init__(
        self,
        provider_name: str = "groww",
        member_id: str = "mother",
        account_name: str = "Imported Account",
    ) -> None:
        super().__init__(provider_id=provider_name.lower(), member_id=member_id)
        self.account_name = account_name
        self._holdings: List[CanonicalHolding] = []
        self._transactions: List[CanonicalTransaction] = []
        self._status = SyncStatus.CONNECTED

    def authenticate(self) -> bool:
        self._status = SyncStatus.CONNECTED
        return True

    def health_check(self) -> ConnectionHealth:
        return ConnectionHealth(
            is_healthy=True,
            status=SyncStatus.CONNECTED,
            message=f"Ready for statement ingestion ({self.provider_id.title()}).",
        )

    def get_accounts(self) -> List[CanonicalAccount]:
        return [
            CanonicalAccount(
                provider=self.provider_id,
                provider_account_id=f"stmt_{self.provider_id}_{self.member_id}",
                family_member_id=self.member_id,
                account_type=f"{self.provider_id.upper()}_STATEMENT_ACCOUNT",
                currency="INR",
                masked_identifier=f"{self.provider_id.upper()}-STMT",
                status=self._status,
                last_synced_at=self._last_synced_at,
            )
        ]

    def parse_holdings_csv(self, csv_content: str) -> List[CanonicalHolding]:
        """
        Parses generic or broker-specific holdings CSV:
        Headers supported:
        - Symbol / Stock / Instrument / Scheme Name
        - ISIN
        - Quantity / Qty / Units
        - Average Cost / Avg Price / Buy Price / Cost Basis
        - Current Price / LTP / NAV / Market Price
        - Asset Class / Type (Equity, Mutual Fund, Gold, etc.)
        - Acquisition Date / Buy Date / Purchase Date
        """
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        holdings: List[CanonicalHolding] = []
        account_id = f"stmt_{self.provider_id}_{self.member_id}"

        for row in reader:
            # Clean keys by stripping whitespace and lowercasing
            clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}

            # Symbol / Name
            sym = (
                clean_row.get("symbol")
                or clean_row.get("stock")
                or clean_row.get("instrument")
                or clean_row.get("tradingsymbol")
                or clean_row.get("scheme name")
                or clean_row.get("name")
                or "UNKNOWN"
            )

            # ISIN
            isin = clean_row.get("isin")

            # Quantity
            qty_str = (
                clean_row.get("quantity")
                or clean_row.get("qty")
                or clean_row.get("units")
                or clean_row.get("shares")
                or "0"
            ).replace(",", "")
            qty = Decimal(qty_str) if qty_str else Decimal("0")
            if qty <= 0:
                continue

            # Cost Price
            cost_str = (
                clean_row.get("average cost")
                or clean_row.get("avg cost")
                or clean_row.get("avg price")
                or clean_row.get("buy price")
                or clean_row.get("cost_basis_per_unit")
                or clean_row.get("purchase price")
                or "0"
            ).replace(",", "")
            cost_price = Decimal(cost_str) if cost_str else Decimal("0")

            # Current Price
            curr_str = (
                clean_row.get("current price")
                or clean_row.get("ltp")
                or clean_row.get("nav")
                or clean_row.get("market price")
                or clean_row.get("close price")
                or str(cost_price)
            ).replace(",", "")
            current_price = Decimal(curr_str) if curr_str else cost_price

            # Asset Type
            raw_type = clean_row.get("asset class") or clean_row.get("type") or clean_row.get("asset_class") or ""
            raw_type = raw_type.upper()
            if "MUTUAL" in raw_type or "MF" in raw_type or "FUND" in raw_type:
                atype = AssetType.MUTUAL_FUND
            elif "CRYPTO" in raw_type:
                atype = AssetType.CRYPTO
            elif "GOLD" in raw_type:
                atype = AssetType.GOLD
            elif "US" in raw_type or sym.endswith(".US"):
                atype = AssetType.US_EQUITY
            elif "FD" in raw_type or "DEPOSIT" in raw_type:
                atype = AssetType.FIXED_DEPOSIT
            elif "BOND" in raw_type:
                atype = AssetType.BOND
            else:
                atype = AssetType.INDIAN_EQUITY

            # Acquisition Date
            acq_str = (
                clean_row.get("acquisition date")
                or clean_row.get("buy date")
                or clean_row.get("purchase date")
                or clean_row.get("date")
            )
            acq_date = date.today()
            if acq_str:
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                    try:
                        acq_date = datetime.strptime(acq_str[:10], fmt).date()
                        break
                    except ValueError:
                        pass

            # Grandfathering FMV if available
            g_str = clean_row.get("grandfathered_cost") or clean_row.get("fmv_2018")
            grandfathered = Decimal(g_str.replace(",", "")) if g_str else None

            # Exchange
            exchange = clean_row.get("exchange", "NSE" if atype == AssetType.INDIAN_EQUITY else None)
            symbol_canonical = sym
            if atype == AssetType.INDIAN_EQUITY and exchange == "NSE" and not sym.endswith(".NS"):
                symbol_canonical = f"{sym}.NS"

            asset = CanonicalAsset(
                symbol=symbol_canonical,
                name=clean_row.get("name", sym),
                asset_type=atype,
                currency="INR",
                isin=isin,
                exchange=exchange,
                metadata={"folio": clean_row.get("folio")},
            )

            holdings.append(
                CanonicalHolding(
                    holding_id=f"CSV-{self.provider_id}-{sym}-{str(uuid.uuid4())[:6]}",
                    account_id=account_id,
                    asset=asset,
                    quantity=qty,
                    average_cost=cost_price,
                    cost_basis=qty * cost_price,
                    current_price=current_price,
                    market_value=qty * current_price,
                    currency="INR",
                    as_of=datetime.utcnow(),
                    acquisition_date=acq_date,
                    grandfathered_cost=grandfathered,
                )
            )

        self._holdings = holdings
        self._last_synced_at = datetime.utcnow()
        self._status = SyncStatus.SYNC_SUCCESS
        return holdings

    def get_holdings(self, account_id: str) -> List[CanonicalHolding]:
        return self._holdings

    def get_transactions(
        self, account_id: str, since: Optional[datetime] = None
    ) -> List[CanonicalTransaction]:
        return self._transactions

    def get_cash_balances(self, account_id: str) -> List[CanonicalCashBalance]:
        return []

    def disconnect(self) -> bool:
        self._holdings.clear()
        self._transactions.clear()
        self._status = SyncStatus.NOT_CONNECTED
        return True
