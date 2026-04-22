from __future__ import annotations

from pydantic import BaseModel


class ScenarioRequest(BaseModel):
    query: str
