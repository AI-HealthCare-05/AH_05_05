from datetime import datetime

from pydantic import BaseModel, Field

from app.dtos.base import BaseSerializerModel
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
