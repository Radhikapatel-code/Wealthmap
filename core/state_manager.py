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


class PortfolioStateManager:
    """Thread-safe state manager for family portfolios and lot tracking."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.RLock()
        self._families: Dict[str, FamilyUnit] = {}
        self._lot_trackers: Dict[str, LotTracker] = {}
        self._normalizer = PortfolioNormalizer(self.settings)
        self._cfo_engine: Optional[CFOEngine] = None

    def initialize_demo(self, session_id: str = "default") -> FamilyUnit:
        with self._lock:
            family = FamilyUnit(family_name="Sharma Family")
            tracker = LotTracker()

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
