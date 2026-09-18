"""
WealthMap FastAPI Application.
Run: uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
import logging
import sys
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Header, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

sys.path.insert(0, ".")

from config.settings import get_settings, Settings
from core.state_manager import get_state_manager, PortfolioStateManager
from core.tax.equity_tax import EquityTaxEngine
from core.tax.crypto_tax import CryptoTaxEngine
from core.tax.tlh_scanner import TLHScanner
from core.tax.tax_calendar import TaxCalendar
from core.ai.context_builder import CFOContextBuilder
from core.alerts.ltcg_watcher import LTCGWatcher, TDSTracker
from api.schemas.asset import (
    ManualAssetRequest, SimulateSaleRequest, ScenarioRequest, ChatRequest,
    AddMemberRequest, AIResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)

_state_manager = get_state_manager()
_context_builder = CFOContextBuilder()
_equity_engine = EquityTaxEngine()
_crypto_engine = CryptoTaxEngine()
_tlh_scanner = TLHScanner()
_tax_calendar = TaxCalendar()
_ltcg_watcher = LTCGWatcher()
_tds_tracker = TDSTracker()


def get_session_id(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_family_id: Optional[str] = Header(None, alias="X-Family-ID"),
    session_id: Optional[str] = Query(None),
) -> str:
    """Resolve session/family ID for multi-tenant isolation."""
    for val in (x_session_id, x_family_id, session_id):
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "default"


def verify_api_key(
    api_key_header_val: Optional[str] = Security(api_key_header),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth),
    settings: Settings = Depends(get_settings),
) -> bool:
    expected_key = settings.api_key
    if not expected_key:
        return True

    provided_token = api_key_header_val or (bearer_creds.credentials if bearer_creds else None)
    if not provided_token or provided_token != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state_manager.initialize_demo("default")
    logger.info("WealthMap initialized with multi-session state manager.")
    yield
    logger.info("WealthMap shutting down.")


app = FastAPI(
    title="WealthMap API",
    description="AI-Powered Portfolio Intelligence for Indian HNI Families",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": "WealthMap API", "version": "1.0.0"}


@app.get("/portfolio/family", tags=["Portfolio"], dependencies=[Depends(verify_api_key)])
def get_family_portfolio(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    return family.to_summary_dict()


@app.get("/portfolio/member/{member_id}", tags=["Portfolio"], dependencies=[Depends(verify_api_key)])
def get_member_portfolio(member_id: str, session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
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


@app.get("/portfolio/net-worth", tags=["Portfolio"], dependencies=[Depends(verify_api_key)])
def get_net_worth(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
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


@app.post("/portfolio/manual-asset", tags=["Portfolio"], dependencies=[Depends(verify_api_key)])
def add_manual_asset(request: ManualAssetRequest, session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    tracker = _state_manager.get_lot_tracker(session_id)
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
        tracker.add_lot(lot)

    return {"added": [lot.to_dict() for lot in lots]}


@app.get("/tax/liability", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def get_tax_liability(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    return family.ytd_tax_summary()


@app.get("/tax/ltcg-calendar", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def get_ltcg_calendar(days: int = Query(default=90, ge=7, le=365), session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    events = _tax_calendar.ltcg_unlock_events(family.all_lots, look_ahead_days=days)
    return {
        "look_ahead_days": days,
        "events_count": len(events),
        "events": events,
        "total_potential_saving_inr": sum(e["potential_saving_inr"] for e in events),
    }


@app.post("/tax/simulate-sale", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def simulate_sale(
    request: SimulateSaleRequest,
    use_rust: bool = Query(default=False, description="Execute simulation using high-performance Rust engine"),
    session_id: str = Depends(get_session_id),
):
    family = _state_manager.get_family(session_id)
    tracker = _state_manager.get_lot_tracker(session_id)
    member = family.get_member(request.member_id)
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{request.member_id}' not found.")

    all_lots = tracker.get_lots(request.member_id, request.symbol)
    if not all_lots:
        all_lots = tracker.get_lots(request.member_id, request.symbol + ".NS")
    if not all_lots:
        raise HTTPException(status_code=404, detail=f"No lots found for {request.symbol} ({request.member_id})")

    sale_price = Decimal(str(request.sale_price)) if getattr(request, "sale_price", None) is not None else all_lots[0].current_price

    if use_rust:
        from datetime import date
        from core.tax.rust_engine_bridge import RustEngineBridge

        if not RustEngineBridge.is_available():
            raise HTTPException(status_code=503, detail="Rust engine binding 'wealthmap_engine' is not available in this environment.")

        raw_txs = []
        for lot in all_lots:
            raw_txs.append({
                "transaction_id": f"TX-BUY-{lot.lot_id}",
                "member_id": request.member_id,
                "symbol": lot.symbol,
                "side": "BUY",
                "date": lot.acquisition_date.isoformat(),
                "quantity": str(lot.quantity),
                "price": str(lot.cost_basis_per_unit),
                "asset_class": lot.asset_class.value if hasattr(lot.asset_class, "value") else str(lot.asset_class),
                "lot_id": lot.lot_id,
            })
        raw_txs.append({
            "transaction_id": "TX-SELL-SIM",
            "member_id": request.member_id,
            "symbol": all_lots[0].symbol,
            "side": "SELL",
            "date": date.today().isoformat(),
            "quantity": str(request.quantity),
            "price": str(sale_price),
            "asset_class": all_lots[0].asset_class.value if hasattr(all_lots[0].asset_class, "value") else "EQUITY",
            "lot_id": None,
        })
        try:
            return RustEngineBridge.compute_tax_lots(raw_txs)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Rust engine execution failed: {e}") from e

    try:
        return tracker.simulate_sale(
            member_id=request.member_id,
            symbol=all_lots[0].symbol,
            quantity=Decimal(str(request.quantity)),
            sale_price=sale_price,
            ytd_realized_ltcg=member.ytd_realized_ltcg,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/tax/tlh-opportunities", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def get_tlh_opportunities(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    ytd_ltcg = sum(m.ytd_realized_ltcg for m in family.members)
    ytd_stcg = sum(m.ytd_realized_stcg for m in family.members)
    return _tlh_scanner.generate_report(family.all_lots, ytd_ltcg, ytd_stcg)


@app.get("/tax/advance-tax", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def get_advance_tax(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    tax_summary = family.ytd_tax_summary()
    estimated = Decimal(str(tax_summary.get("estimated_total_tax_inr", 0)))
    ytd_paid = sum(m.ytd_tax_paid for m in family.members)
    schedule = _tax_calendar.advance_tax_dates(estimated, ytd_paid)
    return {
        "estimated_annual_tax_inr": float(estimated),
        "ytd_tax_paid_inr": float(ytd_paid),
        "schedule": schedule,
    }


@app.get("/tax/key-dates", tags=["Tax"], dependencies=[Depends(verify_api_key)])
def get_key_dates():
    return _tax_calendar.key_dates_this_fy()


@app.get("/family/members", tags=["Family"], dependencies=[Depends(verify_api_key)])
def get_family_members(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    return {"members": [m.to_dict() for m in family.members]}


@app.get("/family/gift-alerts", tags=["Family"], dependencies=[Depends(verify_api_key)])
def get_gift_alerts(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    return {"alerts": family.gift_tax_alerts()}


@app.post("/ai/portfolio-health", response_model=AIResponse, tags=["AI"], dependencies=[Depends(verify_api_key)])
def ai_portfolio_health(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    cfo = _state_manager.get_cfo_engine()
    context = _context_builder.build_portfolio_context(family)
    response = cfo.portfolio_health(context)
    return AIResponse(response=response)


@app.post("/ai/tax-advice", response_model=AIResponse, tags=["AI"], dependencies=[Depends(verify_api_key)])
def ai_tax_advice(request: Optional[ScenarioRequest] = None, session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    cfo = _state_manager.get_cfo_engine()
    query = request.query if request else None
    context = _context_builder.build_tax_advice_context(family, specific_query=query)
    response = cfo.tax_advice(context)
    return AIResponse(response=response)


@app.post("/ai/scenario", response_model=AIResponse, tags=["AI"], dependencies=[Depends(verify_api_key)])
def ai_scenario(request: ScenarioRequest, session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    cfo = _state_manager.get_cfo_engine()
    context = _context_builder.build_scenario_context(
        family, request.query, request.additional_context
    )
    response = cfo.scenario_analysis(context, request.query)
    return AIResponse(response=response)


@app.post("/ai/chat", response_model=AIResponse, tags=["AI"], dependencies=[Depends(verify_api_key)])
def ai_chat(request: ChatRequest, session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    cfo = _state_manager.get_cfo_engine()
    context = _context_builder.build_portfolio_context(family)
    response = cfo.chat(context, request.message, request.conversation_history)
    return AIResponse(response=response)


@app.get("/ai/daily-digest", response_model=AIResponse, tags=["AI"], dependencies=[Depends(verify_api_key)])
def ai_daily_digest(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    cfo = _state_manager.get_cfo_engine()
    context = _context_builder.build_daily_digest_context(family)
    response = cfo.daily_digest(context)
    return AIResponse(response=response)


@app.get("/alerts", tags=["Alerts"], dependencies=[Depends(verify_api_key)])
def get_all_alerts(session_id: str = Depends(get_session_id)):
    family = _state_manager.get_family(session_id)
    ltcg_alerts = _ltcg_watcher.generate_alerts(family.all_lots)
    total_estimated_tax = Decimal(str(family.ytd_tax_summary().get("estimated_total_tax_inr", 0)))
    ytd_paid = sum(m.ytd_tax_paid for m in family.members)
    at_alert = _tds_tracker.advance_tax_alert(total_estimated_tax, ytd_paid)

    alerts = ltcg_alerts
    if at_alert:
        alerts.append(at_alert)

    alerts.sort(key=lambda a: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(a.get("priority", "MEDIUM"), 2))
    return {
        "total_alerts": len(alerts),
        "alerts": alerts,
    }


# ── Integrations & External Connectors ─────────────────────────────────────────

@app.get("/integrations/accounts", tags=["Integrations"], dependencies=[Depends(verify_api_key)])
def list_connected_accounts(session_id: str = Depends(get_session_id)):
    """List all connected accounts across providers and family members."""
    sync_engine = _state_manager.get_sync_engine(session_id)
    accounts = sync_engine.list_accounts()
    return {
        "total_accounts": len(accounts),
        "accounts": [
            {
                "account_id": a.account_id,
                "provider": a.provider,
                "family_member_id": a.family_member_id,
                "account_type": a.account_type,
                "currency": a.currency,
                "masked_identifier": a.masked_identifier,
                "status": a.status.value,
                "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
                "error_message": a.error_message,
            }
            for a in accounts
        ],
    }


@app.post("/integrations/sync", tags=["Integrations"], dependencies=[Depends(verify_api_key)])
def sync_accounts(
    connector_id: Optional[str] = Query(None, description="Specific connector ID, or omit to sync all"),
    session_id: str = Depends(get_session_id),
):
    """Trigger incremental sync on connected provider accounts."""
    sync_engine = _state_manager.get_sync_engine(session_id)
    family = _state_manager.get_family(session_id)
    tracker = _state_manager.get_lot_tracker(session_id)

    if connector_id:
        result = sync_engine.sync_connector(connector_id)
        results = [result]
    else:
        results = sync_engine.sync_all()

    # Refresh family snapshot and lot tracker
    for member in family.members:
        fresh_snapshot = sync_engine.build_member_snapshot(member.member_id, existing_snapshot=member.portfolio)
        member.portfolio = fresh_snapshot
        for lot in fresh_snapshot.lots:
            tracker.add_lot(lot)

    return {
        "sync_results": [
            {
                "account_id": r.account_id,
                "provider": r.provider,
                "status": r.status.value,
                "holdings_count": r.holdings_count,
                "transactions_count": r.transactions_count,
                "synced_at": r.synced_at.isoformat(),
                "error_message": r.error_message,
            }
            for r in results
        ]
    }


@app.post("/integrations/connect", tags=["Integrations"], dependencies=[Depends(verify_api_key)])
def connect_provider(
    payload: dict,
    session_id: str = Depends(get_session_id),
):
    """Register and authenticate a new provider connection."""
    from core.connectors.providers.zerodha import ZerodhaConnector
    from core.connectors.providers.binance import BinanceConnector
    from core.connectors.providers.coindcx import CoinDCXConnector
    from core.connectors.providers.alpaca import AlpacaConnector
    from core.connectors.providers.upstox import UpstoxConnector
    from core.connectors.providers.angel_one import AngelOneConnector
    from core.connectors.providers.wazirx import WazirXConnector

    sync_engine = _state_manager.get_sync_engine(session_id)
    provider = payload.get("provider", "").lower()
    member_id = payload.get("member_id", "father")
    cid = f"{provider}_{member_id}"

    if provider == "zerodha":
        conn = ZerodhaConnector(
            api_key=payload.get("api_key", ""),
            access_token=payload.get("access_token", ""),
            member_id=member_id,
            client_id=payload.get("client_id"),
        )
    elif provider == "binance":
        conn = BinanceConnector(
            api_key=payload.get("api_key", ""),
            api_secret=payload.get("api_secret", ""),
            member_id=member_id,
        )
    elif provider == "coindcx":
        conn = CoinDCXConnector(
            api_key=payload.get("api_key", ""),
            api_secret=payload.get("api_secret", ""),
            member_id=member_id,
        )
    elif provider == "alpaca":
        conn = AlpacaConnector(
            api_key_id=payload.get("api_key", ""),
            secret_key=payload.get("api_secret", ""),
            member_id=member_id,
            base_url=payload.get("base_url"),
        )
    elif provider == "upstox":
        conn = UpstoxConnector(
            api_key=payload.get("api_key", ""),
            api_secret=payload.get("api_secret", ""),
            redirect_uri=payload.get("redirect_uri", ""),
            member_id=member_id,
            access_token=payload.get("access_token"),
        )
    elif provider == "angel_one":
        conn = AngelOneConnector(
            api_key=payload.get("api_key", ""),
            client_code=payload.get("client_code", ""),
            password=payload.get("password", ""),
            totp_secret=payload.get("totp_secret"),
            member_id=member_id,
            jwt_token=payload.get("jwt_token"),
        )
    elif provider == "wazirx":
        conn = WazirXConnector(
            api_key=payload.get("api_key", ""),
            api_secret=payload.get("api_secret", ""),
            member_id=member_id,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    auth_success = conn.authenticate()
    sync_engine.register_connector(cid, conn)

    accounts = conn.get_accounts()
    acc = accounts[0] if accounts else None

    return {
        "connector_id": cid,
        "provider": provider,
        "authenticated": auth_success,
        "status": conn.status.value,
        "masked_identifier": acc.masked_identifier if acc else "",
        "error_message": conn.last_error,
    }


@app.delete("/integrations/disconnect/{connector_id}", tags=["Integrations"], dependencies=[Depends(verify_api_key)])
def disconnect_provider(connector_id: str, session_id: str = Depends(get_session_id)):
    sync_engine = _state_manager.get_sync_engine(session_id)
    success = sync_engine.unregister_connector(connector_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found.")
    return {"status": "disconnected", "connector_id": connector_id}


@app.post("/integrations/upload-statement", tags=["Integrations"], dependencies=[Depends(verify_api_key)])
def upload_statement(
    provider: str = Query("groww", description="groww | cams | generic"),
    member_id: str = Query("mother", description="father | mother | son | child"),
    payload: dict = None,
    session_id: str = Depends(get_session_id),
):
    """Ingest CSV statement and normalize into member portfolio."""
    from core.connectors.providers.csv_statement import CSVStatementConnector

    csv_text = payload.get("csv_content", "") if payload else ""
    if not csv_text:
        raise HTTPException(status_code=400, detail="Missing csv_content in payload.")

    sync_engine = _state_manager.get_sync_engine(session_id)
    family = _state_manager.get_family(session_id)
    tracker = _state_manager.get_lot_tracker(session_id)

    member = family.get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail=f"Member '{member_id}' not found.")

    cid = f"{provider}_{member_id}_upload"
    conn = CSVStatementConnector(provider_name=provider, member_id=member_id)
    holdings = conn.parse_holdings_csv(csv_text)
    sync_engine.register_connector(cid, conn)

    # Convert to AssetLots and add to member portfolio
    for h in holdings:
        lot = sync_engine.canonical_to_asset_lot(h, member_id)
        if member.portfolio:
            member.portfolio.lots.append(lot)
        tracker.add_lot(lot)

    return {
        "status": "imported",
        "provider": provider,
        "member_id": member_id,
        "holdings_imported": len(holdings),
    }

