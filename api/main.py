"""
WealthMap FastAPI Application — main entry point.
Run: uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations
import logging
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Bootstrap path
sys.path.insert(0, ".")

from config.settings import get_settings, Settings
from core.aggregator.normalizer import PortfolioNormalizer
from core.family.family_unit import FamilyUnit, FamilyMember
from core.tax.lot_tracker import LotTracker
from core.tax.equity_tax import EquityTaxEngine
from core.tax.crypto_tax import CryptoTaxEngine
from core.tax.tlh_scanner import TLHScanner
from core.tax.tax_calendar import TaxCalendar
from core.ai.context_builder import CFOContextBuilder
from core.ai.cfo_engine import CFOEngine
from core.alerts.ltcg_watcher import LTCGWatcher
from api.schemas.asset import (
    ManualAssetRequest, SimulateSaleRequest, ScenarioRequest, ChatRequest,
    AddMemberRequest, AIResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# App State (in-memory for demo; swap for DB in prod)
# ─────────────────────────────────────────────

_family: Optional[FamilyUnit] = None
_normalizer: Optional[PortfolioNormalizer] = None
_lot_tracker: LotTracker = LotTracker()
_cfo_engine: Optional[CFOEngine] = None
_context_builder = CFOContextBuilder()
_equity_engine = EquityTaxEngine()
_crypto_engine = CryptoTaxEngine()
_tlh_scanner = TLHScanner()
_tax_calendar = TaxCalendar()
_ltcg_watcher = LTCGWatcher()


def _get_family() -> FamilyUnit:
    if _family is None:
        raise HTTPException(status_code=503, detail="Family data not initialized. Call /init first.")
    return _family


def _get_cfo() -> CFOEngine:
    if _cfo_engine is None:
        raise HTTPException(status_code=503, detail="AI engine not initialized.")
    return _cfo_engine


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _family, _normalizer, _cfo_engine
    settings = get_settings()
    _normalizer = PortfolioNormalizer(settings)
    _cfo_engine = CFOEngine(api_key=settings.gemini_api_key)
    _family = _init_demo_family(settings)
    logger.info("WealthMap initialized with demo family data.")
    yield
    logger.info("WealthMap shutting down.")


def _init_demo_family(settings: Settings) -> FamilyUnit:
    """Bootstrap a demo family with sample portfolios."""
    family = FamilyUnit(family_name="Demo Family")

    member_configs = [
        ("father", "Rajesh Sharma", "SELF", Decimal("0.30")),
        ("mother", "Priya Sharma", "SPOUSE", Decimal("0.30")),
        ("son", "Arjun Sharma", "CHILD", Decimal("0.20")),
    ]

    for mid, name, rel, slab in member_configs:
        snapshot = _normalizer.build_demo_snapshot(mid)
        member = FamilyMember(
            member_id=mid,
            name=name,
            relationship=rel,
            tax_slab_rate=slab,
            portfolio=snapshot,
            ytd_realized_ltcg=Decimal("87000") if mid == "father" else Decimal("15000"),
            ytd_realized_stcg=Decimal("23000") if mid == "father" else Decimal("5000"),
            ytd_realized_crypto=Decimal("120000") if mid == "father" else Decimal("0"),
            ytd_tax_paid=Decimal("52000") if mid == "father" else Decimal("6000"),
        )
        family.add_member(member)
        # Load lots into tracker
        for lot in snapshot.lots:
            _lot_tracker.add_lot(lot)

    return family


# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────

app = FastAPI(
    title="WealthMap API",
    description="AI-Powered Portfolio Intelligence for Indian HNI Families",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Portfolio Routes
# ─────────────────────────────────────────────

@app.get("/portfolio/family", tags=["Portfolio"])
def get_family_portfolio():
    """Full family portfolio snapshot."""
    family = _get_family()
    return family.to_summary_dict()


@app.get("/portfolio/member/{member_id}", tags=["Portfolio"])
def get_member_portfolio(member_id: str):
    """Individual member portfolio."""
    family = _get_family()
    member = family.get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found.")
    if not member.portfolio:
        raise HTTPException(status_code=404, detail="No portfolio data for member.")
    return {
        "member": member.to_dict(),
        "lots": [lot.to_dict() for lot in member.portfolio.lots],
        "asset_class_values": {k: float(v) for k, v in member.portfolio.asset_class_values().items()},
        "total_value_inr": float(member.portfolio.total_value),
        "total_unrealized_gain_inr": float(member.portfolio.total_unrealized_gain),
    }


@app.get("/portfolio/net-worth", tags=["Portfolio"])
def get_net_worth():
    """Current net worth breakdown by asset class and member."""
    family = _get_family()
    return {
        "total_net_worth_inr": float(family.total_net_worth),
        "asset_class_breakdown": family.asset_class_breakdown(),
        "by_member": [
            {
                "member_id": m.member_id,
                "name": m.name,
                "net_worth_inr": float(m.net_worth),
                "pct_of_family": float(
                    (m.net_worth / family.total_net_worth * 100).quantize(Decimal("0.01"))
                ) if family.total_net_worth else 0.0,
            }
            for m in family.members
        ],
        "concentration_risks": family.concentration_risks(),
    }


@app.post("/portfolio/manual-asset", tags=["Portfolio"])
def add_manual_asset(request: ManualAssetRequest):
    """Add a manual asset (FD, gold, US equity) to a member's portfolio."""
    family = _get_family()
    member = family.get_member(request.member_id)
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{request.member_id}' not found.")

    from core.aggregator.manual_import import ManualAssetImporter
    importer = ManualAssetImporter()
    asset_data = request.dict()
    lots = importer.import_from_json([asset_data], request.member_id)

    if not lots:
        raise HTTPException(status_code=400, detail="Could not parse asset data.")

    for lot in lots:
        member.portfolio.lots.append(lot)
        _lot_tracker.add_lot(lot)

    return {"added": [lot.to_dict() for lot in lots]}


# ─────────────────────────────────────────────
# Tax Routes
# ─────────────────────────────────────────────

@app.get("/tax/liability", tags=["Tax"])
def get_tax_liability(member_id: Optional[str] = None):
    """Current FY tax liability — all members or specific member."""
    family = _get_family()
    return family.ytd_tax_summary()


@app.get("/tax/ltcg-calendar", tags=["Tax"])
def get_ltcg_calendar(days: int = Query(default=90, ge=7, le=365)):
    """Upcoming LTCG unlock events within specified days."""
    family = _get_family()
    all_lots = family.all_lots
    events = _tax_calendar.ltcg_unlock_events(all_lots, look_ahead_days=days)
    return {
        "look_ahead_days": days,
        "events_count": len(events),
        "events": events,
        "total_potential_saving_inr": sum(e["potential_saving_inr"] for e in events),
    }


@app.post("/tax/simulate-sale", tags=["Tax"])
def simulate_sale(request: SimulateSaleRequest):
    """Simulate selling shares — detailed lot-by-lot tax breakdown."""
    family = _get_family()
    member = family.get_member(request.member_id)
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{request.member_id}' not found.")

    # Get current price for this symbol
    all_lots = _lot_tracker.get_lots(request.member_id, request.symbol)
    if not all_lots:
        # Try with .NS suffix
        all_lots = _lot_tracker.get_lots(request.member_id, request.symbol + ".NS")
    if not all_lots:
        raise HTTPException(status_code=404, detail=f"No lots found for {request.symbol} ({request.member_id})")

    current_price = all_lots[0].current_price
    try:
        result = _lot_tracker.simulate_sale(
            member_id=request.member_id,
            symbol=all_lots[0].symbol,
            quantity=Decimal(str(request.quantity)),
            sale_price=current_price,
            ytd_realized_ltcg=member.ytd_realized_ltcg,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/tax/tlh-opportunities", tags=["Tax"])
def get_tlh_opportunities():
    """Tax loss harvesting candidates."""
    family = _get_family()
    all_lots = family.all_lots
    ytd_ltcg = sum(m.ytd_realized_ltcg for m in family.members)
    ytd_stcg = sum(m.ytd_realized_stcg for m in family.members)
    return _tlh_scanner.generate_report(all_lots, ytd_ltcg, ytd_stcg)


@app.get("/tax/advance-tax", tags=["Tax"])
def get_advance_tax():
    """Advance tax installment schedule."""
    family = _get_family()
    tax_summary = family.ytd_tax_summary()
    estimated = Decimal(str(tax_summary.get("estimated_total_tax_inr", 0)))
    ytd_paid = sum(m.ytd_tax_paid for m in family.members)
    schedule = _tax_calendar.advance_tax_dates(estimated, ytd_paid)
    return {
        "estimated_annual_tax_inr": float(estimated),
        "ytd_tax_paid_inr": float(ytd_paid),
        "schedule": schedule,
    }


@app.get("/tax/key-dates", tags=["Tax"])
def get_key_dates():
    """All key tax dates for current financial year."""
    return _tax_calendar.key_dates_this_fy()


# ─────────────────────────────────────────────
# Family Routes
# ─────────────────────────────────────────────

@app.get("/family/members", tags=["Family"])
def get_family_members():
    """List all family members."""
    family = _get_family()
    return {"members": [m.to_dict() for m in family.members]}


@app.get("/family/gift-alerts", tags=["Family"])
def get_gift_alerts():
    """Intra-family gift tax alerts."""
    family = _get_family()
    return {"alerts": family.gift_tax_alerts()}


# ─────────────────────────────────────────────
# AI Routes
# ─────────────────────────────────────────────

@app.post("/ai/portfolio-health", response_model=AIResponse, tags=["AI"])
def ai_portfolio_health():
    """Claude portfolio health assessment."""
    family = _get_family()
    cfo = _get_cfo()
    context = _context_builder.build_portfolio_context(family)
    response = cfo.portfolio_health(context)
    return AIResponse(response=response)


@app.post("/ai/tax-advice", response_model=AIResponse, tags=["AI"])
def ai_tax_advice(request: Optional[ScenarioRequest] = None):
    """Claude tax optimization advice."""
    family = _get_family()
    cfo = _get_cfo()
    query = request.query if request else None
    context = _context_builder.build_tax_advice_context(family, specific_query=query)
    response = cfo.tax_advice(context)
    return AIResponse(response=response)


@app.post("/ai/scenario", response_model=AIResponse, tags=["AI"])
def ai_scenario(request: ScenarioRequest):
    """Claude scenario analysis — free-form query."""
    family = _get_family()
    cfo = _get_cfo()
    context = _context_builder.build_scenario_context(
        family, request.query, request.additional_context
    )
    response = cfo.scenario_analysis(context, request.query)
    return AIResponse(response=response)


@app.post("/ai/chat", response_model=AIResponse, tags=["AI"])
def ai_chat(request: ChatRequest):
    """Multi-turn CFO chat."""
    family = _get_family()
    cfo = _get_cfo()
    context = _context_builder.build_portfolio_context(family)
    response = cfo.chat(context, request.message, request.conversation_history)
    return AIResponse(response=response)


@app.get("/ai/daily-digest", response_model=AIResponse, tags=["AI"])
def ai_daily_digest():
    """Generate daily portfolio digest."""
    family = _get_family()
    cfo = _get_cfo()
    context = _context_builder.build_daily_digest_context(family)
    response = cfo.daily_digest(context)
    return AIResponse(response=response)


# ─────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────

@app.get("/alerts", tags=["Alerts"])
def get_all_alerts():
    """All active alerts — LTCG unlocks, advance tax, TDS."""
    family = _get_family()
    all_lots = family.all_lots

    ltcg_alerts = _ltcg_watcher.generate_alerts(all_lots)

    total_estimated_tax = Decimal(str(family.ytd_tax_summary().get("estimated_total_tax_inr", 0)))
    ytd_paid = sum(m.ytd_tax_paid for m in family.members)
    from core.alerts.ltcg_watcher import TDSTracker
    tds_tracker = TDSTracker()
    at_alert = tds_tracker.advance_tax_alert(total_estimated_tax, ytd_paid)

    alerts = ltcg_alerts
    if at_alert:
        alerts.append(at_alert)

    alerts.sort(key=lambda a: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(a.get("priority", "MEDIUM"), 2))

    return {
        "total_alerts": len(alerts),
        "alerts": alerts,
    }


# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": "WealthMap API", "version": "1.0.0"}
