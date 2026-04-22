from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


MONEY_PLACES = Decimal("0.01")


def money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def decimalize(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def days_between(start: date, end: date) -> int:
    return max((end - start).days, 0)


def fy_start(as_of: date, fy_start_month: int = 4) -> date:
    if as_of.month < fy_start_month:
        return date(as_of.year - 1, fy_start_month, 1)
    return date(as_of.year, fy_start_month, 1)


def fy_end(as_of: date, fy_start_month: int = 4) -> date:
    start = fy_start(as_of, fy_start_month)
    return date(start.year + 1, fy_start_month, 1) - timedelta(days=1)


def financial_year_label(as_of: date, fy_start_month: int = 4) -> str:
    start = fy_start(as_of, fy_start_month)
    return f"FY{start.year + 1}-{str(start.year + 2)[-2:]}"


def next_days(target: date, as_of: date | None = None) -> int:
    reference = as_of or date.today()
    return max((target - reference).days, 0)


def long_term_threshold_days(asset_class: Any, metadata: dict[str, Any] | None = None) -> int | None:
    meta = metadata or {}
    asset_name = getattr(asset_class, "value", str(asset_class))
    if asset_name in {"EQUITY", "US_EQUITY"}:
        return 365
    if asset_name == "MF":
        return 365 if str(meta.get("fund_type", "equity")).lower() == "equity" else None
    if asset_name == "GOLD":
        return 365 * 3
    return None
