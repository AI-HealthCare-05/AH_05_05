from datetime import datetime
from typing import Any

from app.dtos.background_jobs import BackgroundJobFilter
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus


class BackgroundJobRepository:
    async def get(self, job_id: int) -> BackgroundJob | None:
        return await BackgroundJob.get_or_none(id=job_id)

    async def get_by_idempotency_key(self, key: str) -> BackgroundJob | None:
        return await BackgroundJob.get_or_none(idempotency_key=key)

    async def create(self, data: dict[str, Any]) -> BackgroundJob:
        return await BackgroundJob.create(**data)

    async def list(self, filters: BackgroundJobFilter) -> tuple[list[BackgroundJob], int]:
        query = BackgroundJob.all()
        if filters.job_type is not None:
            query = query.filter(job_type=filters.job_type)
        if filters.status is not None:
            query = query.filter(status=filters.status)
        if filters.user_id is not None:
            query = query.filter(user_id=filters.user_id)
        if filters.requested_from is not None:
            query = query.filter(requested_at__gte=filters.requested_from)
        if filters.requested_to is not None:
            query = query.filter(requested_at__lte=filters.requested_to)
        total = await query.count()
        items = await query.order_by("-requested_at", "-id").offset(filters.offset).limit(filters.limit)
        return items, total

    async def claim(self, job_id: int, started_at: datetime) -> bool:
        updated = await BackgroundJob.filter(
            id=job_id,
            status__in=[BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING],
        ).update(status=BackgroundJobStatus.PROCESSING, started_at=started_at, updated_at=started_at)
        return updated == 1
