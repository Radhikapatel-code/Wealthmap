from __future__ import annotations

from typing import Any


class YahooFinancePriceFeed:
    def fetch_quote(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "status": "stubbed",
            "message": "Install yfinance-backed lookup for live market prices in production mode.",
        }
