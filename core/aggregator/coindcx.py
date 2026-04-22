from __future__ import annotations

from typing import Any

from config.settings import Settings


class CoinDCXAggregator:
    BASE_URL = "https://api.coindcx.com"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def configured(self) -> bool:
        return bool(self.settings.coindcx_api_key and self.settings.coindcx_api_secret)

    def fetch_holdings(self) -> list[dict[str, Any]]:
        if not self.configured():
            return []
        return [
            {
                "source": "coindcx",
                "status": "configured",
                "message": "Replace stub with signed REST calls when real exchange sync is enabled.",
            }
        ]
