"""FX rate service for live USD/INR conversions with cached fallback."""
from __future__ import annotations
import time
import urllib.request
import json
import logging
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class FXRateService:
    def __init__(self, default_rate: float = 83.5, cache_ttl_seconds: int = 3600) -> None:
        self.default_rate = Decimal(str(default_rate))
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_rate: Optional[Decimal] = None
        self._last_fetch_time: float = 0.0

    def get_usd_inr_rate(self) -> Decimal:
        now = time.time()
        if self._cached_rate is not None and (now - self._last_fetch_time) < self.cache_ttl_seconds:
            return self._cached_rate

        rate = self._fetch_live_rate()
        if rate is not None:
            self._cached_rate = rate
            self._last_fetch_time = now
            return rate

        return self._cached_rate or self.default_rate

    def _fetch_live_rate(self) -> Optional[Decimal]:
        endpoints = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.frankfurter.app/latest?from=USD&to=INR",
        ]
        for url in endpoints:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "WealthMap/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    if "rates" in data and "INR" in data["rates"]:
                        return Decimal(str(data["rates"]["INR"])).quantize(Decimal("0.01"))
            except Exception as exc:
                logger.debug("Failed to fetch live FX from %s: %s", url, exc)
        return None


_default_fx_service: Optional[FXRateService] = None


def get_fx_service(default_rate: float = 83.5) -> FXRateService:
    global _default_fx_service
    if _default_fx_service is None:
        _default_fx_service = FXRateService(default_rate=default_rate)
    return _default_fx_service
