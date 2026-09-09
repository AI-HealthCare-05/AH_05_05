from datetime import date, datetime, time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.dtos.base import BaseSerializerModel

HospitalName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class FollowUpVisitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date
    visit_time: time | None = None
    hospital: HospitalName


class FollowUpVisitUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visit_date: date | None = None
    visit_time: time | None = None
    hospital: HospitalName | None = None

    @field_validator("hospital")
    @classmethod
    def reject_explicit_null_hospital(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("hospital cannot be null.")
        return value


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
