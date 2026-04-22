from __future__ import annotations

from pydantic import BaseModel, Field


class SaleSimulationRequest(BaseModel):
    member_id: str
    symbol: str
    quantity: float = Field(gt=0)
    method: str = "FIFO"
