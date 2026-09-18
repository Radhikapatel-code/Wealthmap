"""
Pydantic schemas for external integrations and account synchronization.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConnectAccountRequest(BaseModel):
    provider: str = Field(..., description="zerodha | binance | coindcx | alpaca | groww")
    member_id: str = Field(..., description="father | mother | son | HUF member ID")
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    client_id: Optional[str] = None
    base_url: Optional[str] = None


class SyncTriggerRequest(BaseModel):
    connector_id: Optional[str] = None
    member_id: Optional[str] = None


class AccountSummaryResponse(BaseModel):
    account_id: str
    provider: str
    family_member_id: str
    account_type: str
    currency: str
    masked_identifier: str
    status: str
    last_synced_at: Optional[str] = None
    error_message: Optional[str] = None


class SyncResultResponse(BaseModel):
    account_id: str
    provider: str
    status: str
    holdings_count: int
    transactions_count: int
    synced_at: str
    error_message: Optional[str] = None


class StatementUploadRequest(BaseModel):
    provider: str = Field(default="groww", description="groww | cams | zerodha | generic")
    member_id: str = Field(default="mother")
    csv_content: str
