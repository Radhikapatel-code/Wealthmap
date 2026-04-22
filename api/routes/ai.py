from __future__ import annotations

from fastapi import APIRouter

from api.schemas.family import ScenarioRequest
from core.ai.cfo_engine import CFOEngine
from core.wealth_service import get_wealth_service


router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/portfolio-health")
def portfolio_health() -> dict:
    service = get_wealth_service()
    return CFOEngine().portfolio_health(service.family_unit())


@router.post("/tax-advice")
def tax_advice() -> dict:
    service = get_wealth_service()
    return CFOEngine().tax_advice(service.family_unit())


@router.post("/scenario")
def scenario(payload: ScenarioRequest) -> dict:
    service = get_wealth_service()
    return CFOEngine().scenario_analysis(service.family_unit(), query=payload.query)


@router.get("/daily-digest")
def daily_digest() -> dict:
    service = get_wealth_service()
    return CFOEngine().daily_digest(service.family_unit())
