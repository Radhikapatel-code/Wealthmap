"""
Core data models for WealthMap.
All monetary values use Decimal for financial precision — no floats.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    MUTUAL_FUND = "MUTUAL_FUND"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    GOLD = "GOLD"
    US_EQUITY = "US_EQUITY"
    REAL_ESTATE = "REAL_ESTATE"


class TaxClassification(str, Enum):
    STCG = "STCG"          # Short-Term Capital Gain
    LTCG = "LTCG"          # Long-Term Capital Gain
    CRYPTO = "CRYPTO"      # 30% flat, no offset
    INTEREST = "INTEREST"  # Slab rate (FD)
    EXEMPT = "EXEMPT"      # Within exemption limit


class Platform(str, Enum):
    ZERODHA = "zerodha"
    BINANCE = "binance"
    COINDCX = "coindcx"
    GROWW = "groww"
    KUVERA = "kuvera"
    VESTED = "vested"
    INDMONEY = "indmoney"
    MANUAL = "manual"


# ─────────────────────────────────────────────
# Indian Tax Constants FY 2025-26
# ─────────────────────────────────────────────

class TaxConstants:
    # Equity / MF
    STCG_RATE = Decimal("0.20")                  # 20% flat
    LTCG_RATE = Decimal("0.125")                 # 12.5%
    LTCG_EXEMPTION = Decimal("125000")           # ₹1,25,000 per individual per FY

    # Crypto
    CRYPTO_RATE = Decimal("0.30")                # 30% flat
    CRYPTO_TDS_RATE = Decimal("0.01")            # 1% TDS per transaction

    # FD
    FD_TDS_THRESHOLD = Decimal("40000")          # TDS triggered above ₹40,000 interest
    FD_TDS_RATE = Decimal("0.10")                # 10% TDS

    # US Equity (DTAA)
    US_EQUITY_RATE = Decimal("0.25")

    # Gold (physical)
    GOLD_LTCG_RATE = Decimal("0.125")            # 12.5% with indexation (post Budget 2024)
    GOLD_LONG_TERM_DAYS = 730                    # 2 years for gold

    # General
    EQUITY_LONG_TERM_DAYS = 365                  # 12 months for equity
    MF_EQUITY_LONG_TERM_DAYS = 365
    MF_DEBT_LONG_TERM_DAYS = 1095               # 3 years for debt MF (pre-Apr 2023 purchases)

    # Grandfathering
    GRANDFATHERING_CUTOFF = date(2018, 1, 31)

    # FY
    FY_START_MONTH = 4   # April
    FY_START_DAY = 1

    # Cess
    HEALTH_EDUCATION_CESS = Decimal("0.04")     # 4% cess on tax


def current_fy_start() -> date:
    today = date.today()
    year = today.year if today.month >= TaxConstants.FY_START_MONTH else today.year - 1
    return date(year, TaxConstants.FY_START_MONTH, TaxConstants.FY_START_DAY)


def current_fy_end() -> date:
    fy_start = current_fy_start()
    return date(fy_start.year + 1, 3, 31)


# ─────────────────────────────────────────────
# Tax Breakdown
# ─────────────────────────────────────────────

@dataclass
class TaxBreakdown:
    classification: TaxClassification
    gross_gain: Decimal
    taxable_gain: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    cess_amount: Decimal
    total_tax: Decimal
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "classification": self.classification.value,
            "gross_gain_inr": float(self.gross_gain),
            "taxable_gain_inr": float(self.taxable_gain),
            "tax_rate": float(self.tax_rate),
            "tax_amount_inr": float(self.tax_amount),
            "cess_amount_inr": float(self.cess_amount),
            "total_tax_inr": float(self.total_tax),
            "notes": self.notes,
        }


# ─────────────────────────────────────────────
# Asset Lot — the atomic unit of WealthMap
# ─────────────────────────────────────────────

@dataclass
class AssetLot:
    lot_id: str
    symbol: str
    asset_class: AssetClass
    platform: Platform
    member_id: str
    quantity: Decimal
    acquisition_date: date
    cost_basis_per_unit: Decimal        # Always in INR
    current_price: Decimal              # Always in INR
    grandfathered_cost: Optional[Decimal] = None  # For pre-2018 equity

    # Optional metadata
    isin: Optional[str] = None
    name: Optional[str] = None
    exchange: Optional[str] = None

    # ── Computed Properties ──────────────────

    @property
    def holding_days(self) -> int:
        return (date.today() - self.acquisition_date).days

    @property
    def effective_cost_basis(self) -> Decimal:
        """Applies grandfathering for pre-Jan 31 2018 equity holdings."""
        if (
            self.grandfathered_cost is not None
            and self.acquisition_date <= TaxConstants.GRANDFATHERING_CUTOFF
            and self.asset_class in (AssetClass.EQUITY, AssetClass.MUTUAL_FUND)
        ):
            return max(self.cost_basis_per_unit, self.grandfathered_cost)
        return self.cost_basis_per_unit

    @property
    def is_long_term(self) -> bool:
        thresholds = {
            AssetClass.EQUITY: TaxConstants.EQUITY_LONG_TERM_DAYS,
            AssetClass.MUTUAL_FUND: TaxConstants.MF_EQUITY_LONG_TERM_DAYS,
            AssetClass.GOLD: TaxConstants.GOLD_LONG_TERM_DAYS,
            AssetClass.US_EQUITY: TaxConstants.EQUITY_LONG_TERM_DAYS,
        }
        threshold = thresholds.get(self.asset_class)
        if threshold is None:
            return False
        return self.holding_days >= threshold

    @property
    def days_to_long_term(self) -> int:
        thresholds = {
            AssetClass.EQUITY: TaxConstants.EQUITY_LONG_TERM_DAYS,
            AssetClass.MUTUAL_FUND: TaxConstants.MF_EQUITY_LONG_TERM_DAYS,
            AssetClass.GOLD: TaxConstants.GOLD_LONG_TERM_DAYS,
        }
        threshold = thresholds.get(self.asset_class, 0)
        remaining = threshold - self.holding_days
        return max(0, remaining)

    @property
    def current_value(self) -> Decimal:
        return (self.quantity * self.current_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def total_cost_basis(self) -> Decimal:
        return (self.quantity * self.effective_cost_basis).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def unrealized_gain(self) -> Decimal:
        return (self.current_value - self.total_cost_basis).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def unrealized_gain_pct(self) -> Decimal:
        if self.total_cost_basis == 0:
            return Decimal("0")
        return ((self.unrealized_gain / self.total_cost_basis) * 100).quantize(Decimal("0.01"))

    def to_dict(self) -> dict:
        return {
            "lot_id": self.lot_id,
            "symbol": self.symbol,
            "name": self.name or self.symbol,
            "asset_class": self.asset_class.value,
            "platform": self.platform.value,
            "member_id": self.member_id,
            "quantity": float(self.quantity),
            "acquisition_date": self.acquisition_date.isoformat(),
            "cost_basis_per_unit_inr": float(self.cost_basis_per_unit),
            "current_price_inr": float(self.current_price),
            "current_value_inr": float(self.current_value),
            "total_cost_basis_inr": float(self.total_cost_basis),
            "unrealized_gain_inr": float(self.unrealized_gain),
            "unrealized_gain_pct": float(self.unrealized_gain_pct),
            "holding_days": self.holding_days,
            "is_long_term": self.is_long_term,
            "days_to_long_term": self.days_to_long_term,
        }


# ─────────────────────────────────────────────
# Realized Transaction
# ─────────────────────────────────────────────

@dataclass
class RealizedTransaction:
    transaction_id: str
    lot_id: str
    symbol: str
    asset_class: AssetClass
    member_id: str
    quantity: Decimal
    sale_date: date
    sale_price_per_unit: Decimal
    cost_basis_per_unit: Decimal
    acquisition_date: date
    tax_breakdown: TaxBreakdown

    @property
    def gain(self) -> Decimal:
        return (self.quantity * (self.sale_price_per_unit - self.cost_basis_per_unit)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


# ─────────────────────────────────────────────
# LTCG Unlock Event
# ─────────────────────────────────────────────

@dataclass
class UnlockEvent:
    lot_id: str
    symbol: str
    member_id: str
    unlock_date: date
    quantity: Decimal
    current_gain_inr: Decimal
    tax_saving_inr: Decimal    # STCG tax - LTCG tax on this lot

    @property
    def days_remaining(self) -> int:
        return max(0, (self.unlock_date - date.today()).days)

    def to_dict(self) -> dict:
        return {
            "lot_id": self.lot_id,
            "symbol": self.symbol,
            "member_id": self.member_id,
            "unlock_date": self.unlock_date.isoformat(),
            "days_remaining": self.days_remaining,
            "quantity": float(self.quantity),
            "current_gain_inr": float(self.current_gain_inr),
            "tax_saving_inr": float(self.tax_saving_inr),
        }


# ─────────────────────────────────────────────
# TLH Opportunity
# ─────────────────────────────────────────────

@dataclass
class TLHOpportunity:
    loss_lot: AssetLot
    offsettable_gain_lots: list[AssetLot]
    net_tax_saving: Decimal
    loss_amount: Decimal
    risk_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "loss_symbol": self.loss_lot.symbol,
            "loss_lot_id": self.loss_lot.lot_id,
            "unrealized_loss_inr": float(self.loss_amount),
            "net_tax_saving_inr": float(self.net_tax_saving),
            "can_offset_symbols": [l.symbol for l in self.offsettable_gain_lots],
            "risk_notes": self.risk_notes,
        }


# ─────────────────────────────────────────────
# Portfolio Snapshot
# ─────────────────────────────────────────────

@dataclass
class PortfolioSnapshot:
    member_id: str
    as_of: datetime
    lots: list[AssetLot]
    ytd_realized_ltcg: Decimal = Decimal("0")
    ytd_realized_stcg: Decimal = Decimal("0")
    ytd_realized_crypto_gain: Decimal = Decimal("0")
    ytd_tax_paid: Decimal = Decimal("0")

    @property
    def total_value(self) -> Decimal:
        return sum(lot.current_value for lot in self.lots)

    @property
    def total_cost_basis(self) -> Decimal:
        return sum(lot.total_cost_basis for lot in self.lots)

    @property
    def total_unrealized_gain(self) -> Decimal:
        return sum(lot.unrealized_gain for lot in self.lots)

    def by_asset_class(self) -> dict[AssetClass, list[AssetLot]]:
        result: dict[AssetClass, list[AssetLot]] = {}
        for lot in self.lots:
            result.setdefault(lot.asset_class, []).append(lot)
        return result

    def asset_class_values(self) -> dict[str, Decimal]:
        breakdown: dict[str, Decimal] = {}
        for lot in self.lots:
            key = lot.asset_class.value
            breakdown[key] = breakdown.get(key, Decimal("0")) + lot.current_value
        return breakdown
