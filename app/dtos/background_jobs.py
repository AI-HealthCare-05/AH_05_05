from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.dtos.base import BaseSerializerModel, CamelModel
from app.dtos.pagination import PageQuery
from app.models.enums import BackgroundJobStatus, BackgroundJobType


class BackgroundJobFilter(BaseModel):
    job_type: BackgroundJobType | None = None
    status: BackgroundJobStatus | None = None
    user_id: int | None = Field(default=None, gt=0)
    requested_from: datetime | None = None
    requested_to: datetime | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class BackgroundJobResponse(BaseSerializerModel):
    id: int
    idempotency_key: str
    job_type: BackgroundJobType
    status: BackgroundJobStatus
    user_id: int | None
    user_name: str | None = None
    reference_table: str | None
    reference_id: int | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    retry_count: int
    max_retry_count: int
    parent_job_id: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime | None


class BackgroundJobListResponse(BaseModel):
    items: list[BackgroundJobResponse]
    total: int
    offset: int
    limit: int


class BackgroundJobStatsResponse(BaseModel):
    start_date: date
    end_date: date
    total: int
    counts: dict[BackgroundJobStatus, int]


class AdminBackgroundJobListQuery(PageQuery):
    keyword: str | None = Field(default=None, description="작업 ID 또는 작업 유형 검색")
    job_type: BackgroundJobType | None = None
    status: BackgroundJobStatus | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("조회 기간이 올바르지 않습니다.")
        return self


class AdminBackgroundJobListItem(CamelModel):
    job_id: int
    job_type: BackgroundJobType
    status: BackgroundJobStatus
    user_id: int | None
    user_name: str | None
    requested_at: datetime
    error_code: str | None
    error_message: str | None


class AdminBackgroundJobStatsResponse(CamelModel):
    start_date: date
    end_date: date
    total: int
    counts: dict[BackgroundJobStatus, int]
