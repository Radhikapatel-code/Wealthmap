from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.tax import SaleSimulationRequest
from core.wealth_service import get_wealth_service


router = APIRouter(prefix="/tax", tags=["tax"])


@router.get("/liability")
def tax_liability() -> dict:
    return get_wealth_service().tax_liability()


@router.get("/ltcg-calendar")
def ltcg_calendar(window_days: int = Query(default=90, ge=1, le=365)) -> dict:
    return get_wealth_service().ltcg_calendar(window_days=window_days)


@router.post("/simulate-sale")
def simulate_sale(payload: SaleSimulationRequest) -> dict:
    try:
        return get_wealth_service().simulate_sale(
            member_id=payload.member_id,
            symbol=payload.symbol,
            quantity=payload.quantity,
            method=payload.method,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tlh-opportunities")
def tlh_opportunities() -> dict:
    return get_wealth_service().tlh_opportunities()


@router.get("/crypto-tds")
def crypto_tds() -> dict:
    return get_wealth_service().crypto_tds_summary()


@router.get("/advance-tax")
def advance_tax() -> dict:
    return get_wealth_service().advance_tax()
