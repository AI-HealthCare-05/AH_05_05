from datetime import date
from typing import Literal

from pydantic import Field

from app.dtos.base import CamelModel


class SupplementDoseRequest(CamelModel):
    supplement_id: int = Field(gt=0)
    date: date
    slot: Literal["morning", "lunch", "evening", "bedtime"]
    taken: bool


class SupplementDoseResponse(SupplementDoseRequest):
    pass
