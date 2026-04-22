"""
Application settings — loaded from environment variables via Pydantic.
"""
from __future__ import annotations
from functools import lru_cache
from typing import Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings  # type: ignore


class Settings(BaseSettings):
    # ── Google Gemini ────────────────────────────────────────────────────────
    gemini_api_key: str = ""

    # ── Zerodha Kite ─────────────────────────────────────────────────────────
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    # ── Binance ───────────────────────────────────────────────────────────────
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # ── CoinDCX ───────────────────────────────────────────────────────────────
    coindcx_api_key: str = ""
    coindcx_api_secret: str = ""

    # ── App Config ────────────────────────────────────────────────────────────
    app_name: str = "WealthMap"
    debug: bool = False
    fy_start_month: int = 4
    default_member_id: str = "primary"
    usd_inr_rate: float = 83.5

    # ── Alerts ────────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./wealthmap.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
