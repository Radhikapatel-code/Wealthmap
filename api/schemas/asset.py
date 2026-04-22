"""
Pydantic schemas for FastAPI request/response validation.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


# ── Asset Schemas ─────────────────────────────────────────────────────────────

class AssetClassEnum(str, Enum):
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    MUTUAL_FUND = "MUTUAL_FUND"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    GOLD = "GOLD"
    US_EQUITY = "US_EQUITY"
    REAL_ESTATE = "REAL_ESTATE"


class ManualAssetRequest(BaseModel):
    type: str = Field(..., description="FD | GOLD | US_EQUITY | REAL_ESTATE")
    member_id: str
    # FD fields
    bank: Optional[str] = None
    principal_inr: Optional[float] = None
    maturity_value_inr: Optional[float] = None
    start_date: Optional[str] = None
    maturity_date: Optional[str] = None
    interest_rate_pct: Optional[float] = None
    # Gold fields
    quantity_grams: Optional[float] = None
    cost_per_gram_inr: Optional[float] = None
    purchase_date: Optional[str] = None
    current_price_per_gram_inr: Optional[float] = None
    # US Equity fields
    symbol: Optional[str] = None
    quantity: Optional[float] = None
    cost_basis_usd: Optional[float] = None
    current_price_usd: Optional[float] = None
    acquisition_date: Optional[str] = None
    usd_inr_rate: Optional[float] = 83.5


class AssetLotResponse(BaseModel):
    lot_id: str
    symbol: str
    name: Optional[str]
    asset_class: str
    platform: str
    member_id: str
    quantity: float
    acquisition_date: str
    cost_basis_per_unit_inr: float
    current_price_inr: float
    current_value_inr: float
    total_cost_basis_inr: float
    unrealized_gain_inr: float
    unrealized_gain_pct: float
    holding_days: int
    is_long_term: bool
    days_to_long_term: int


class PortfolioSummaryResponse(BaseModel):
    member_id: str
    as_of: str
    total_value_inr: float
    total_cost_basis_inr: float
    total_unrealized_gain_inr: float
    asset_class_breakdown: dict
    lots: List[AssetLotResponse]


# ── Tax Schemas ────────────────────────────────────────────────────────────────

class SimulateSaleRequest(BaseModel):
    member_id: str
    symbol: str
    quantity: float = Field(..., gt=0)
    method: str = Field(default="FIFO", description="FIFO (only supported method)")


class SimulateSaleResponse(BaseModel):
    sale_summary: dict
    lot_breakdown: List[dict]
    tax_summary: dict
    advisory: dict


class TaxLiabilityResponse(BaseModel):
    member_id: Optional[str]
    ytd_realized_ltcg_inr: float
    ytd_realized_stcg_inr: float
    ytd_realized_crypto_gain_inr: float
    estimated_tax_inr: float
    ltcg_exemption_remaining_inr: float
    breakdown_by_member: Optional[List[dict]]


class TLHReportResponse(BaseModel):
    summary: dict
    opportunities: List[dict]
    crypto_loss_warnings: List[dict]
    important_notes: List[str]


# ── Family Schemas ─────────────────────────────────────────────────────────────

class AddMemberRequest(BaseModel):
    member_id: str
    name: str
    relationship: str = Field(..., description="SELF | SPOUSE | CHILD | PARENT | HUF")
    pan: Optional[str] = None
    tax_slab_rate: float = 0.30
    is_huf: bool = False


class FamilyMemberResponse(BaseModel):
    member_id: str
    name: str
    relationship: str
    net_worth_inr: float
    ltcg_exemption_remaining_inr: float
    ytd_realized_ltcg_inr: float
    ytd_realized_stcg_inr: float


class FamilySummaryResponse(BaseModel):
    family_name: str
    member_count: int
    total_net_worth_inr: float
    asset_class_breakdown: dict
    concentration_risks: List[dict]
    members: List[FamilyMemberResponse]


# ── AI Schemas ─────────────────────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    query: str = Field(..., min_length=10, max_length=1000)
    member_id: Optional[str] = None
    additional_context: Optional[dict] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: List[dict] = Field(default_factory=list)


class AIResponse(BaseModel):
    response: str
    context_used: Optional[str] = "full_portfolio"
    disclaimer: str = "Advisory only. Verify with a qualified CA before making financial decisions."
