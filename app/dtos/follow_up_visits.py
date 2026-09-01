from datetime import date, datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.dtos.base import BaseSerializerModel


class FollowUpVisitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date
    visit_time: time | None = None
    hospital: Annotated[str | None, Field(max_length=255)] = None


class FollowUpVisitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date | None = None
    visit_time: time | None = None
    hospital: Annotated[str | None, Field(max_length=255)] = None


class FollowUpVisitResponse(BaseSerializerModel):
    id: int
    user_id: int
    visit_date: date
    visit_time: time | None
    hospital: str | None
    created_at: datetime
    updated_at: datetime | None


class FollowUpVisitListResponse(BaseModel):
    items: list[FollowUpVisitResponse]
    total: int
    offset: int
    limit: int
