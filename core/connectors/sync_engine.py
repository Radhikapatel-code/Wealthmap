"""
Central Synchronization Engine for WealthMap.
Orchestrates connectors, incremental synchronization, deduplication, transfer detection,
and updates the core tax engine and family portfolio snapshots.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from core.connectors.base import BaseConnector
from core.connectors.models import (
    AssetType,
    CanonicalAccount,
    CanonicalAsset,
    CanonicalCashBalance,
    CanonicalHolding,
    CanonicalTransaction,
    SyncResult,
    SyncStatus,
    TransactionType,
)
from core.models import AssetClass, AssetLot, Platform, PortfolioSnapshot
from core.tax.lot_tracker import LotTracker

logger = logging.getLogger(__name__)


def map_asset_type_to_class(asset_type: AssetType) -> AssetClass:
    mapping = {
        AssetType.INDIAN_EQUITY: AssetClass.EQUITY,
        AssetType.US_EQUITY: AssetClass.US_EQUITY,
        AssetType.MUTUAL_FUND: AssetClass.MUTUAL_FUND,
        AssetType.ETF: AssetClass.EQUITY,
        AssetType.CRYPTO: AssetClass.CRYPTO,
        AssetType.FIXED_DEPOSIT: AssetClass.FIXED_DEPOSIT,
        AssetType.GOLD: AssetClass.GOLD,
        AssetType.REAL_ESTATE: AssetClass.REAL_ESTATE,
    }
    return mapping.get(asset_type, AssetClass.EQUITY)


def map_provider_to_platform(provider_id: str) -> Platform:
    p_lower = provider_id.lower()
    for platform in Platform:
        if platform.value == p_lower:
            return platform
    return Platform.MANUAL


class SyncEngine:
    """
    Central synchronization and deduplication orchestrator.
    Manages registered connectors for each family member, synchronizes data incrementally,
    deduplicates holdings across accounts, tags intra-portfolio transfers, and populates
    the deterministic tax engine.
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, BaseConnector] = {}  # connector_id -> BaseConnector
        self._accounts: Dict[str, CanonicalAccount] = {}   # account_id -> CanonicalAccount
        self._sync_history: List[SyncResult] = []
        self._cash_balances: Dict[str, List[CanonicalCashBalance]] = {}

    def register_connector(self, connector_id: str, connector: BaseConnector) -> None:
        """Register an active external connector instance."""
        self._connectors[connector_id] = connector
        # Discover accounts from this connector
        try:
            accounts = connector.get_accounts()
            for acc in accounts:
                self._accounts[acc.account_id] = acc
        except Exception as e:
            logger.warning("Could not discover accounts during registration for %s: %s", connector_id, e)

    def unregister_connector(self, connector_id: str) -> bool:
        """Disconnect and remove a connector."""
        connector = self._connectors.pop(connector_id, None)
        if connector:
            connector.disconnect()
            # Remove linked accounts
            to_remove = [aid for aid, acc in self._accounts.items() if acc.provider == connector.provider_id]
            for aid in to_remove:
                self._accounts.pop(aid, None)
            return True
        return False

    def list_connectors(self) -> Dict[str, BaseConnector]:
        return dict(self._connectors)

    def list_accounts(self, member_id: Optional[str] = None) -> List[CanonicalAccount]:
        accounts = list(self._accounts.values())
        if member_id:
            return [a for a in accounts if a.family_member_id == member_id]
        return accounts

    def sync_connector(self, connector_id: str, force_full_sync: bool = False) -> SyncResult:
        """
        Synchronize a specific connector with enhanced incremental sync support.
        
        Args:
            connector_id: The connector ID to sync
            force_full_sync: If True, ignore last_synced_at and fetch all data
        
        Returns:
            SyncResult with sync status and counts
        """
        connector = self._connectors.get(connector_id)
        if not connector:
            return SyncResult(
                account_id=connector_id,
                provider="unknown",
                status=SyncStatus.NOT_CONNECTED,
                holdings_count=0,
                transactions_count=0,
                error_message="Connector not found.",
            )

        accounts = connector.get_accounts()
        total_holdings = 0
        total_transactions = 0
        err_msg = None
        status = SyncStatus.SYNC_SUCCESS

        for acc in accounts:
            try:
                # Determine sync timestamp
                since_timestamp = None if force_full_sync else acc.last_synced_at
                
                # Sync holdings (always full fetch for holdings to ensure consistency)
                holdings = connector.get_holdings(acc.account_id)
                total_holdings += len(holdings)
                
                # Sync transactions incrementally
                txs = connector.get_transactions(acc.account_id, since=since_timestamp)
                total_transactions += len(txs)
                
                # Sync cash balances
                cash = connector.get_cash_balances(acc.account_id)
                self._cash_balances[acc.account_id] = cash

                # Update account status
                acc.status = SyncStatus.CONNECTED
                acc.last_synced_at = datetime.utcnow()
                acc.error_message = None
                
                logger.info(
                    "Synced %s for %s: %d holdings, %d transactions (since: %s)",
                    connector.provider_id,
                    acc.account_id,
                    len(holdings),
                    len(txs),
                    since_timestamp.isoformat() if since_timestamp else "full sync"
                )
                
            except Exception as e:
                err_msg = str(e)
                status = connector.status
                acc.status = status
                acc.error_message = err_msg
                logger.error("Sync failed for account %s: %s", acc.account_id, err_msg)

        result = SyncResult(
            account_id=accounts[0].account_id if accounts else connector_id,
            provider=connector.provider_id,
            status=status,
            holdings_count=total_holdings,
            transactions_count=total_transactions,
            error_message=err_msg,
        )
        self._sync_history.append(result)
        return result

    def sync_all(self, force_full_sync: bool = False) -> List[SyncResult]:
        """
        Synchronize all registered connectors with optional full sync.
        
        Args:
            force_full_sync: If True, force full sync for all connectors
        
        Returns:
            List of SyncResult objects for each connector
        """
        results = []
        for cid in list(self._connectors.keys()):
            res = self.sync_connector(cid, force_full_sync=force_full_sync)
            results.append(res)
        return results

    def smart_sync_schedule(self) -> List[SyncResult]:
        """
        Implement smart sync scheduling based on provider-specific optimal intervals.
        Different providers have different data freshness requirements and rate limits.
        
        Returns:
            List of SyncResult objects for synced connectors
        """
        results = []
        now = datetime.utcnow()
        
        for cid, connector in self._connectors.items():
            acc = next((a for a in self.accounts if a.account_id.startswith(connector.provider_id)), None)
            if not acc:
                continue
                
            # Provider-specific sync intervals (in minutes)
            sync_intervals = {
                "zerodha": 15,      # Daily token expiry, sync every 15 min
                "binance": 5,         # Real-time crypto, sync every 5 min
                "coindcx": 5,        # Real-time crypto, sync every 5 min
                "wazirx": 5,         # Real-time crypto, sync every 5 min
                "upstox": 10,        # 24-hour token, sync every 10 min
                "angel_one": 15,     # Till midnight, sync every 15 min
                "alpaca": 10,        # US markets, sync every 10 min
                "amfi": 60,         # Daily NAV, sync every hour
            }
            
            interval = sync_intervals.get(connector.provider_id, 30)
            
            # Check if sync is needed
            if acc.last_synced_at:
                time_since_sync = (now - acc.last_synced_at).total_seconds() / 60
                if time_since_sync < interval:
                    logger.debug("Skipping %s sync, last sync was %.1f min ago (interval: %d min)", 
                                cid, time_since_sync, interval)
                    continue
            
            # Perform sync
            try:
                res = self.sync_connector(cid)
                results.append(res)
            except Exception as e:
                logger.error("Smart sync failed for %s: %s", cid, e)
                results.append(SyncResult(
                    account_id=cid,
                    provider=connector.provider_id,
                    status=SyncStatus.SYNC_FAILED,
                    holdings_count=0,
                    transactions_count=0,
                    error_message=str(e),
                ))
        
        return results

    def deduplicate_holdings(
        self, holdings: List[CanonicalHolding]
    ) -> List[CanonicalHolding]:
        """
        Deduplication rule:
        Holdings in different accounts belonging to different members are distinct.
        Holdings in the same account with the same ISIN/symbol are merged (weighted cost basis).
        """
        seen: Dict[Tuple[str, str], CanonicalHolding] = {}
        for h in holdings:
            key = (h.account_id, h.asset.unique_key)
            if key not in seen:
                seen[key] = h
            else:
                existing = seen[key]
                total_qty = existing.quantity + h.quantity
                if total_qty > 0:
                    weighted_avg_cost = (
                        (existing.quantity * existing.average_cost) + (h.quantity * h.average_cost)
                    ) / total_qty
                    existing.quantity = total_qty
                    existing.average_cost = weighted_avg_cost
                    existing.cost_basis = total_qty * weighted_avg_cost
                    existing.market_value = total_qty * existing.current_price

        return list(seen.values())

    def detect_transfers(
        self, transactions: List[CanonicalTransaction]
    ) -> List[CanonicalTransaction]:
        """
        Transfer Detection:
        If a WITHDRAWAL/TRANSFER from Account A matches a DEPOSIT/TRANSFER in Account B
        with the same asset, matching quantity (+/- fees), and within 48 hours,
        mark them as internal transfers (is_internal_transfer = True).
        This prevents the tax engine from treating account transfers as taxable sales.
        """
        withdrawals = [
            t for t in transactions
            if t.transaction_type in (TransactionType.WITHDRAWAL, TransactionType.TRANSFER)
        ]
        deposits = [
            t for t in transactions
            if t.transaction_type in (TransactionType.DEPOSIT, TransactionType.TRANSFER)
        ]

        matched_tx_ids = set()
        for w in withdrawals:
            for d in deposits:
                if w.account_id == d.account_id:
                    continue
                if w.asset.symbol == d.asset.symbol:
                    # Quantity matches within 1% (allow for network/gas/broker fee)
                    qty_diff = abs(w.quantity - d.quantity)
                    if qty_diff <= (w.quantity * Decimal("0.02")):
                        time_diff = abs((w.timestamp - d.timestamp).total_seconds())
                        if time_diff <= 172800:  # 48 hours
                            w.is_internal_transfer = True
                            d.is_internal_transfer = True
                            w.notes = f"Internal transfer to {d.account_id}"
                            d.notes = f"Internal transfer from {w.account_id}"
                            matched_tx_ids.add(w.transaction_id)
                            matched_tx_ids.add(d.transaction_id)

        return transactions

    def canonical_to_asset_lot(
        self, holding: CanonicalHolding, member_id: str
    ) -> AssetLot:
        """Converts a CanonicalHolding into WealthMap's core AssetLot for the tax engine."""
        asset = holding.asset
        platform = map_provider_to_platform(holding.account_id.split("_")[0])
        asset_class = map_asset_type_to_class(asset.asset_type)

        return AssetLot(
            lot_id=holding.holding_id or f"LOT-{str(uuid.uuid4())[:8]}",
            symbol=asset.symbol,
            asset_class=asset_class,
            platform=platform,
            member_id=member_id,
            quantity=holding.quantity,
            acquisition_date=holding.acquisition_date or date.today(),
            cost_basis_per_unit=holding.average_cost,
            current_price=holding.current_price,
            grandfathered_cost=holding.grandfathered_cost,
            isin=asset.isin,
            name=asset.name,
            exchange=asset.exchange,
            metadata=asset.metadata,
        )

    def build_member_snapshot(
        self, member_id: str, existing_snapshot: Optional[PortfolioSnapshot] = None
    ) -> PortfolioSnapshot:
        """
        Consolidates all connected holdings for a family member into a unified PortfolioSnapshot.
        Merges existing lots with fresh connector lots, deduplicating appropriately.
        """
        member_accounts = self.list_accounts(member_id=member_id)
        all_canonical_holdings: List[CanonicalHolding] = []

        for acc in member_accounts:
            conn = next((c for c in self._connectors.values() if c.provider_id == acc.provider), None)
            if conn and conn.status == SyncStatus.CONNECTED:
                try:
                    holdings = conn.get_holdings(acc.account_id)
                    all_canonical_holdings.extend(holdings)
                except Exception as e:
                    logger.debug("Failed to pull holdings from %s for member %s: %s", acc.account_id, member_id, e)

        # Deduplicate
        deduped = self.deduplicate_holdings(all_canonical_holdings)

        # Convert to AssetLots
        fresh_lots = [self.canonical_to_asset_lot(h, member_id) for h in deduped]

        # Merge with existing snapshot manual lots (avoiding duplicates)
        final_lots: List[AssetLot] = list(fresh_lots)
        if existing_snapshot:
            fresh_symbols = {l.symbol for l in fresh_lots}
            for lot in existing_snapshot.lots:
                if lot.symbol not in fresh_symbols:
                    final_lots.append(lot)

        return PortfolioSnapshot(
            member_id=member_id,
            as_of=datetime.now(),
            lots=final_lots,
            ytd_realized_ltcg=existing_snapshot.ytd_realized_ltcg if existing_snapshot else Decimal("0"),
            ytd_realized_stcg=existing_snapshot.ytd_realized_stcg if existing_snapshot else Decimal("0"),
            ytd_realized_crypto_gain=existing_snapshot.ytd_realized_crypto_gain if existing_snapshot else Decimal("0"),
            ytd_tax_paid=existing_snapshot.ytd_tax_paid if existing_snapshot else Decimal("0"),
        )

    def populate_lot_tracker(self, tracker: LotTracker, member_id: str) -> None:
        """Populate a LotTracker instance with fresh lots from synchronized accounts."""
        snapshot = self.build_member_snapshot(member_id)
        for lot in snapshot.lots:
            tracker.add_lot(lot)

    def get_sync_history(self, connector_id: Optional[str] = None, limit: int = 100) -> List[SyncResult]:
        """
        Retrieve sync history for debugging and monitoring.
        
        Args:
            connector_id: Filter by specific connector, or None for all
            limit: Maximum number of records to return
        
        Returns:
            List of SyncResult objects
        """
        if connector_id:
            return [r for r in self._sync_history if r.account_id == connector_id][-limit:]
        return self._sync_history[-limit:]

    def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Get overall sync statistics for monitoring.
        
        Returns:
            Dictionary with sync metrics
        """
        if not self._sync_history:
            return {
                "total_syncs": 0,
                "successful_syncs": 0,
                "failed_syncs": 0,
                "total_holdings_synced": 0,
                "total_transactions_synced": 0,
                "active_connectors": len(self._connectors),
                "providers": {},
            }
        
        successful = sum(1 for r in self._sync_history if r.status == SyncStatus.SYNC_SUCCESS)
        failed = sum(1 for r in self._sync_history if r.status in (SyncStatus.SYNC_FAILED, SyncStatus.AUTH_EXPIRED, SyncStatus.PROVIDER_UNAVAILABLE))
        
        provider_stats = {}
        for result in self._sync_history:
            if result.provider not in provider_stats:
                provider_stats[result.provider] = {
                    "total_syncs": 0,
                    "successful_syncs": 0,
                    "failed_syncs": 0,
                    "total_holdings": 0,
                    "total_transactions": 0,
                }
            provider_stats[result.provider]["total_syncs"] += 1
            if result.status == SyncStatus.SYNC_SUCCESS:
                provider_stats[result.provider]["successful_syncs"] += 1
                provider_stats[result.provider]["total_holdings"] += result.holdings_count
                provider_stats[result.provider]["total_transactions"] += result.transactions_count
            else:
                provider_stats[result.provider]["failed_syncs"] += 1
        
        return {
            "total_syncs": len(self._sync_history),
            "successful_syncs": successful,
            "failed_syncs": failed,
            "total_holdings_synced": sum(r.holdings_count for r in self._sync_history),
            "total_transactions_synced": sum(r.transactions_count for r in self._sync_history),
            "active_connectors": len(self._connectors),
            "providers": provider_stats,
        }
