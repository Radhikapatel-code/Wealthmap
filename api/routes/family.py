from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.wealth_service import get_wealth_service


router = APIRouter(prefix="/family", tags=["family"])


@router.get("/")
def family_snapshot() -> dict:
    return get_wealth_service().family_snapshot()


@router.get("/{member_id}")
def family_member(member_id: str) -> dict:
    try:
        return get_wealth_service().member_snapshot(member_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Member not found.") from exc
