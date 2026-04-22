"""
Alert modules — LTCG watcher, TDS tracker, and digest dispatcher.
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from core.models import AssetLot, AssetClass, TaxConstants
from core.tax.tax_calendar import TaxCalendar

logger = logging.getLogger(__name__)


class LTCGWatcher:
    """
    Monitors positions approaching LTCG qualification.
    Triggers alerts 7 days before unlock.
    """
    DEFAULT_ALERT_DAYS = 7
    calendar = TaxCalendar()

    def get_imminent_unlocks(
        self,
        lots: list[AssetLot],
        alert_window_days: int = DEFAULT_ALERT_DAYS,
    ) -> list[dict]:
        """Returns lots unlocking within alert_window_days."""
        events = self.calendar.ltcg_unlock_events(lots, look_ahead_days=alert_window_days)
        urgent = [e for e in events if e["days_remaining"] <= alert_window_days and e["worth_waiting"]]
        return urgent

    def generate_alerts(self, lots: list[AssetLot]) -> list[dict]:
        imminent = self.get_imminent_unlocks(lots, alert_window_days=7)
        alerts = []
        for event in imminent:
            alerts.append({
                "alert_type": "LTCG_UNLOCK",
                "priority": "HIGH" if event["days_remaining"] <= 3 else "MEDIUM",
                "symbol": event["symbol"],
                "member_id": event["member_id"],
                "message": (
                    f"⚡ LTCG Alert: {event['symbol']} unlocks LTCG status in "
                    f"{event['days_remaining']} days ({event['unlock_date']}). "
                    f"Waiting saves ₹{event['potential_saving_inr']:,.0f} in tax."
                ),
                "action": f"Do NOT sell {event['symbol']} before {event['unlock_date']}.",
                "tax_saving_inr": event["potential_saving_inr"],
                "unlock_date": event["unlock_date"],
            })
        return alerts


class TDSTracker:
    """
    Tracks TDS deductions across FD and crypto.
    Flags when approaching TDS thresholds or when TDS is under-deducted.
    """

    def fd_tds_status(self, fd_lots: list[dict]) -> list[dict]:
        return self.calendar.fd_tds_alerts(fd_lots) if fd_lots else []

    calendar = TaxCalendar()

    def crypto_tds_reconciliation(
        self,
        tds_summary,
    ) -> dict:
        balance = tds_summary.tds_balance_inr
        return {
            "tds_liability_inr": float(tds_summary.tds_liability_inr),
            "tds_deducted_inr": float(tds_summary.tds_deducted_inr),
            "outstanding_inr": float(balance),
            "status": "RECONCILED" if abs(balance) < Decimal("100") else (
                "UNDER_DEDUCTED" if balance > 0 else "OVER_DEDUCTED"
            ),
            "flagged_transactions": tds_summary.flagged_transactions,
            "note": (
                "Outstanding TDS must be paid as advance tax to avoid 234B/234C interest."
                if balance > Decimal("100") else
                "TDS is reconciled. No additional payment required."
            ),
        }

    def advance_tax_alert(self, estimated_tax: Decimal, ytd_paid: Decimal) -> Optional[dict]:
        """Alert if advance tax is due soon."""
        today = date.today()
        due_dates = [
            date(today.year, 6, 15),
            date(today.year, 9, 15),
            date(today.year, 12, 15),
            date(today.year + 1, 3, 15),
        ]
        percentages = [Decimal("0.15"), Decimal("0.45"), Decimal("0.75"), Decimal("1.00")]

        if estimated_tax <= Decimal("10000"):
            return None

        for due_date, pct in zip(due_dates, percentages):
            days_until = (due_date - today).days
            if 0 <= days_until <= 14:
                cumulative_due = estimated_tax * pct
                installment = max(cumulative_due - ytd_paid, Decimal("0"))
                if installment > Decimal("1000"):
                    return {
                        "alert_type": "ADVANCE_TAX_DUE",
                        "priority": "CRITICAL" if days_until <= 3 else "HIGH",
                        "due_date": due_date.isoformat(),
                        "days_until_due": days_until,
                        "installment_amount_inr": float(installment),
                        "message": (
                            f"⚠️ Advance tax installment of ₹{float(installment):,.0f} "
                            f"due on {due_date.isoformat()} ({days_until} days remaining)."
                        ),
                    }
        return None
