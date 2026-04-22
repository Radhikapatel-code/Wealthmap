from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.asset import ManualAssetCreate
from core.wealth_service import get_wealth_service


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/family")
def family_portfolio() -> dict:
    return get_wealth_service().family_snapshot()


@router.get("/member/{member_id}")
def member_portfolio(member_id: str) -> dict:
    service = get_wealth_service()
    try:
        return service.member_snapshot(member_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Member not found.") from exc


@router.get("/net-worth")
def net_worth() -> dict:
    return get_wealth_service().net_worth_breakdown()


@router.post("/manual-asset")
def add_manual_asset(payload: ManualAssetCreate) -> dict:
    try:
        return get_wealth_service().add_manual_asset(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
