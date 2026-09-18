"""Thread-safe portfolio state manager for WealthMap."""
from __future__ import annotations
import threading
from decimal import Decimal
from typing import Optional, Dict

from config.settings import Settings, get_settings
from core.aggregator.normalizer import PortfolioNormalizer
from core.family.family_unit import FamilyUnit, FamilyMember
from core.tax.lot_tracker import LotTracker
from core.ai.cfo_engine import CFOEngine
from core.connectors.sync_engine import SyncEngine
from core.connectors.providers.zerodha import ZerodhaConnector
from core.connectors.providers.binance import BinanceConnector
from core.connectors.providers.coindcx import CoinDCXConnector
from core.connectors.providers.alpaca import AlpacaConnector
from core.connectors.providers.amfi import AMFIProvider
from core.connectors.providers.csv_statement import CSVStatementConnector
from core.connectors.providers.upstox import UpstoxConnector
from core.connectors.providers.angel_one import AngelOneConnector
from core.connectors.providers.wazirx import WazirXConnector


class PortfolioStateManager:
    """Thread-safe state manager for family portfolios, lot tracking, and live connectors."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.RLock()
        self._families: Dict[str, FamilyUnit] = {}
        self._lot_trackers: Dict[str, LotTracker] = {}
        self._sync_engines: Dict[str, SyncEngine] = {}
        self._normalizer = PortfolioNormalizer(self.settings)
        self._cfo_engine: Optional[CFOEngine] = None

    def _init_connectors_for_session(self, session_id: str) -> SyncEngine:
        """Instantiate configured connectors and register them with the session's SyncEngine."""
        engine = SyncEngine()
        s = self.settings

        # Zerodha (if credentials available)
        if s.kite_api_key and s.kite_access_token:
            engine.register_connector(
                "zerodha_father",
                ZerodhaConnector(s.kite_api_key, s.kite_access_token, member_id="father"),
            )

        # Binance (if credentials available)
        if s.binance_api_key and s.binance_api_secret:
            engine.register_connector(
                "binance_father",
                BinanceConnector(s.binance_api_key, s.binance_api_secret, member_id="father"),
            )

        # CoinDCX (if credentials available)
        if s.coindcx_api_key and s.coindcx_api_secret:
            engine.register_connector(
                "coindcx_son",
                CoinDCXConnector(s.coindcx_api_key, s.coindcx_api_secret, member_id="son"),
            )

        # Upstox (if credentials available)
        if s.upstox_api_key and s.upstox_api_secret and s.upstox_redirect_uri:
            engine.register_connector(
                "upstox_father",
                UpstoxConnector(
                    s.upstox_api_key,
                    s.upstox_api_secret,
                    s.upstox_redirect_uri,
                    member_id="father",
                    access_token=s.upstox_access_token,
                ),
            )

        # Angel One (if credentials available)
        if s.angel_one_api_key and s.angel_one_client_code and s.angel_one_password:
            engine.register_connector(
                "angel_one_mother",
                AngelOneConnector(
                    s.angel_one_api_key,
                    s.angel_one_client_code,
                    s.angel_one_password,
                    s.angel_one_totp_secret,
                    member_id="mother",
                ),
            )

        # WazirX (if credentials available)
        if s.wazirx_api_key and s.wazirx_api_secret:
            engine.register_connector(
                "wazirx_son",
                WazirXConnector(s.wazirx_api_key, s.wazirx_api_secret, member_id="son"),
            )

        # AMFI Mutual Fund Public Provider
        engine.register_connector("amfi_public", AMFIProvider(member_id="all"))

        # Pre-register statement connector for manual uploads
        engine.register_connector(
            "groww_statement_mother",
            CSVStatementConnector(provider_name="groww", member_id="mother", account_name="Groww Investments"),
        )

        self._sync_engines[session_id] = engine
        return engine

    def initialize_demo(self, session_id: str = "default") -> FamilyUnit:
        with self._lock:
            family = FamilyUnit(family_name="Sharma Family")
            tracker = LotTracker()
            sync_engine = self._init_connectors_for_session(session_id)

            member_configs = [
                ("father", "Rajesh Sharma", "SELF", Decimal("0.30")),
                ("mother", "Priya Sharma", "SPOUSE", Decimal("0.30")),
                ("son", "Arjun Sharma", "CHILD", Decimal("0.20")),
            ]

            for mid, name, rel, slab in member_configs:
                snapshot = self._normalizer.build_demo_snapshot(mid)
                member = FamilyMember(
                    member_id=mid,
                    name=name,
                    relationship=rel,
                    tax_slab_rate=slab,
                    portfolio=snapshot,
                    ytd_realized_ltcg=Decimal("87000") if mid == "father" else Decimal("15000"),
                    ytd_realized_stcg=Decimal("23000") if mid == "father" else Decimal("5000"),
                    ytd_realized_crypto=Decimal("120000") if mid == "father" else Decimal("0"),
                    ytd_tax_paid=Decimal("52000") if mid == "father" else Decimal("6000"),
                )
                family.add_member(member)
                for lot in snapshot.lots:
                    tracker.add_lot(lot)

            self._families[session_id] = family
            self._lot_trackers[session_id] = tracker
            if self._cfo_engine is None:
                self._cfo_engine = CFOEngine(api_key=self.settings.gemini_api_key)

            return family

    def get_family(self, session_id: str = "default") -> FamilyUnit:
        with self._lock:
            if session_id not in self._families:
                self.initialize_demo(session_id)
            return self._families[session_id]

    def get_lot_tracker(self, session_id: str = "default") -> LotTracker:
        with self._lock:
            if session_id not in self._lot_trackers:
                self.initialize_demo(session_id)
            return self._lot_trackers[session_id]

    def get_sync_engine(self, session_id: str = "default") -> SyncEngine:
        with self._lock:
            if session_id not in self._sync_engines:
                self._init_connectors_for_session(session_id)
            return self._sync_engines[session_id]

    def get_cfo_engine(self) -> CFOEngine:
        with self._lock:
            if self._cfo_engine is None:
                self._cfo_engine = CFOEngine(api_key=self.settings.gemini_api_key)
            return self._cfo_engine


_global_state_manager: Optional[PortfolioStateManager] = None


def get_state_manager() -> PortfolioStateManager:
    global _global_state_manager
    if _global_state_manager is None:
        _global_state_manager = PortfolioStateManager()
    return _global_state_manager

