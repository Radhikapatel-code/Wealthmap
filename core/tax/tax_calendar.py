"""
Tax Calendar — Indian advance tax dates and LTCG unlock timeline.
"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal

from core.models import AssetLot, AssetClass, TaxConstants, UnlockEvent, current_fy_start, current_fy_end


ADVANCE_TAX_SCHEDULE = [
    {"installment": 1, "month": 6,  "day": 15, "cumulative_pct": Decimal("0.15"), "label": "1st Installment"},
    {"installment": 2, "month": 9,  "day": 15, "cumulative_pct": Decimal("0.45"), "label": "2nd Installment"},
    {"installment": 3, "month": 12, "day": 15, "cumulative_pct": Decimal("0.75"), "label": "3rd Installment"},
    {"installment": 4, "month": 3,  "day": 15, "cumulative_pct": Decimal("1.00"), "label": "Final Installment"},
]


class TaxCalendar:

    def advance_tax_dates(
        self,
        estimated_annual_tax: Decimal,
        ytd_advance_tax_paid: Decimal = Decimal("0"),
    ) -> list[dict]:
        """
        Returns advance tax installment schedule for current FY.
        Advance tax is applicable if total tax liability > ₹10,000.
        """
        today = date.today()
        fy_start = current_fy_start()
        fy_year = fy_start.year

        if estimated_annual_tax <= Decimal("10000"):
            return [{
                "note": "Advance tax not applicable — estimated liability ≤ ₹10,000.",
                "estimated_tax_inr": float(estimated_annual_tax),
            }]

        result = []
        for item in ADVANCE_TAX_SCHEDULE:
            m, d = item["month"], item["day"]
            year = fy_year if m >= 4 else fy_year + 1
            due_date = date(year, m, d)

            cumulative_due = (estimated_annual_tax * item["cumulative_pct"]).quantize(Decimal("0.01"))
            installment = max(cumulative_due - ytd_advance_tax_paid, Decimal("0"))
            days_until = (due_date - today).days
            status = "OVERDUE" if days_until < 0 and installment > 0 else (
                "DUE_SOON" if 0 <= days_until <= 14 else "UPCOMING"
            )

            result.append({
                "installment": item["label"],
                "due_date": due_date.isoformat(),
                "cumulative_percentage": float(item["cumulative_pct"] * 100),
                "cumulative_amount_inr": float(cumulative_due),
                "installment_amount_inr": float(installment),
                "days_until_due": days_until,
                "status": status,
            })

        return result

    def ltcg_unlock_events(
        self,
        lots: list[AssetLot],
        look_ahead_days: int = 90,
        ytd_realized_ltcg: Decimal = Decimal("0"),
        **kwargs,
    ) -> list[dict]:
        """All LTCG unlock events within the look-ahead window."""
        if "window_days" in kwargs:
            look_ahead_days = kwargs["window_days"]

        from core.tax.equity_tax import EquityTaxEngine
        from decimal import ROUND_HALF_UP
        engine = EquityTaxEngine()
        unlock_events = engine.ltcg_unlock_calendar(
            lots, look_ahead_days=look_ahead_days, ytd_realized_ltcg=ytd_realized_ltcg
        )

        lot_map = {l.lot_id: l for l in lots}
        remaining_exemption = max(TaxConstants.LTCG_EXEMPTION - ytd_realized_ltcg, Decimal("0"))

        events = []
        for e in unlock_events:
            lot = lot_map.get(e.lot_id)
            name = lot.name if (lot and lot.name) else e.symbol
            acq_date = lot.acquisition_date.isoformat() if lot else ""

            gain = e.current_gain_inr
            stcg_tax = (gain * TaxConstants.STCG_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            taxable_ltcg = max(gain - remaining_exemption, Decimal("0"))
            ltcg_tax = (taxable_ltcg * TaxConstants.LTCG_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            saving = e.tax_saving_inr

            events.append({
                "lot_id": e.lot_id,
                "symbol": e.symbol,
                "name": name,
                "member_id": e.member_id,
                "acquisition_date": acq_date,
                "unlock_date": e.unlock_date.isoformat(),
                "days_remaining": e.days_remaining,
                "quantity": float(e.quantity),
                "unrealized_gain_inr": float(gain),
                "stcg_tax_if_sold_today_inr": float(stcg_tax),
                "ltcg_tax_after_unlock_inr": float(ltcg_tax),
                "potential_saving_inr": float(saving),
                "worth_waiting": saving > Decimal("1000"),
            })

        events.sort(key=lambda x: x["days_remaining"])
        return events

    # Alias for method compatibility
    advance_tax_schedule = advance_tax_dates

    def fd_tds_alerts(self, fd_assets: list[dict]) -> list[dict]:
        """
        Flag FDs where interest income is approaching the ₹40,000 TDS threshold.
        """
        alerts = []
        for fd in fd_assets:
            interest = Decimal(str(fd.get("accrued_interest_inr", 0)))
            threshold = TaxConstants.FD_TDS_THRESHOLD
            if interest >= threshold * Decimal("0.80"):  # Within 80% of threshold
                pct = float((interest / threshold * 100).quantize(Decimal("0.01")))
                alerts.append({
                    "fd_id": fd.get("lot_id"),
                    "bank": fd.get("name", "Unknown Bank"),
                    "accrued_interest_inr": float(interest),
                    "tds_threshold_inr": float(threshold),
                    "pct_of_threshold": pct,
                    "tds_applicable": interest >= threshold,
                    "estimated_tds_inr": float((interest * TaxConstants.FD_TDS_RATE).quantize(Decimal("0.01"))) if interest >= threshold else 0.0,
                    "alert_level": "CRITICAL" if interest >= threshold else "WARNING",
                })
        return alerts

    def key_dates_this_fy(self) -> list[dict]:
        """Returns all key tax dates for the current financial year."""
        today = date.today()
        fy_start = current_fy_start()
        fy_end = current_fy_end()
        fy_year = fy_start.year

        dates = [
            {
                "date": fy_start.isoformat(),
                "event": "Financial Year Start",
                "description": "LTCG exemption resets (₹1.25L per individual).",
                "category": "FY_BOUNDARY",
            },
            {
                "date": date(fy_year, 6, 15).isoformat(),
                "event": "Advance Tax — 1st Installment (15%)",
                "description": "Pay 15% of estimated annual tax.",
                "category": "ADVANCE_TAX",
            },
            {
                "date": date(fy_year, 9, 15).isoformat(),
                "event": "Advance Tax — 2nd Installment (45%)",
                "description": "Cumulative 45% of estimated annual tax.",
                "category": "ADVANCE_TAX",
            },
            {
                "date": date(fy_year, 12, 15).isoformat(),
                "event": "Advance Tax — 3rd Installment (75%)",
                "description": "Cumulative 75% of estimated annual tax.",
                "category": "ADVANCE_TAX",
            },
            {
                "date": date(fy_year + 1, 3, 15).isoformat(),
                "event": "Advance Tax — Final Installment (100%)",
                "description": "Final advance tax payment.",
                "category": "ADVANCE_TAX",
            },
            {
                "date": fy_end.isoformat(),
                "event": "Financial Year End",
                "description": "Last date to book STCG/LTCG in current FY.",
                "category": "FY_BOUNDARY",
            },
            {
                "date": date(fy_year + 1, 7, 31).isoformat(),
                "event": "ITR Filing Deadline (Individuals)",
                "description": "Last date to file ITR-2/ITR-3 for carry-forward of capital losses.",
                "category": "ITR",
            },
        ]

        # Mark past/upcoming
        for d in dates:
            event_date = date.fromisoformat(d["date"])
            d["days_until"] = (event_date - today).days
            d["status"] = "PAST" if event_date < today else (
                "TODAY" if event_date == today else "UPCOMING"
            )

        return sorted(dates, key=lambda x: x["date"])
