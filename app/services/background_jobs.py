from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError
from tortoise.functions import Count

from app.core import config
from app.dtos.background_jobs import (
    AdminBackgroundJobListItem,
    AdminBackgroundJobListQuery,
    BackgroundJobFilter,
    BackgroundJobStatsResponse,
)
from app.dtos.pagination import PageResponse
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import AlarmType, BackgroundJobStatus, BackgroundJobType, OcrJobStatus
from app.models.ocr import OcrJob
from app.repositories.background_job_repository import BackgroundJobRepository


class BackgroundJobService:
    def __init__(
        self,
        repository: BackgroundJobRepository | None = None,
        redis_pool: ArqRedis | None = None,
    ):
        self.repository = repository or BackgroundJobRepository()
        self.redis_pool = redis_pool

    async def get(self, job_id: int) -> BackgroundJob:
        job = await self.repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background job not found.")
        return job

    async def list(self, filters: BackgroundJobFilter) -> tuple[list[BackgroundJob], int]:
        return await self.repository.list(filters)

    async def list_for_admin(self, filters: AdminBackgroundJobListQuery) -> PageResponse[AdminBackgroundJobListItem]:
        candidate_limit = filters.page * filters.size
        jobs, background_total = await self.repository.list_for_admin(
            filters,
            offset=0,
            limit=candidate_limit,
        )
        ocr_jobs, ocr_total = await self._list_ocr_for_admin(filters, limit=candidate_limit)
        alarm_ids_by_job_id = {
            job.id: self._alarm_id_from_job(job) for job in jobs if job.job_type == BackgroundJobType.ALARM
        }
        alarm_ids = {alarm_id for alarm_id in alarm_ids_by_job_id.values() if alarm_id is not None}
        alarm_type_by_id: dict[int, AlarmType] = {}
        if alarm_ids:
            alarm_rows = await Alarm.filter(id__in=alarm_ids).values("id", "alarm_type")
            alarm_type_by_id = {int(row["id"]): AlarmType(row["alarm_type"]) for row in alarm_rows}
        items = [
            AdminBackgroundJobListItem(
                job_id=job.id,
                job_type=job.job_type,
                alarm_type=alarm_type_by_id.get(alarm_ids_by_job_id.get(job.id)),
                status=job.status,
                user_id=job.user_id,
                user_name=getattr(job.user, "name", None) if job.user_id is not None else None,
                requested_at=job.requested_at,
                error_code=job.error_code,
                error_message=job.error_message,
            )
            for job in jobs
        ]
        items.extend(self._ocr_list_item(job) for job in ocr_jobs)
        items.sort(key=lambda item: (item.requested_at, str(item.job_id)), reverse=True)
        offset = (filters.page - 1) * filters.size
        return PageResponse[AdminBackgroundJobListItem](
            items=items[offset : offset + filters.size],
            total_count=background_total + ocr_total,
            page=filters.page,
            size=filters.size,
        )

    @staticmethod
    def _alarm_id_from_job(job: BackgroundJob) -> int | None:
        if job.reference_table == "alarms" and job.reference_id is not None:
            return job.reference_id
        matched = re.match(r"^alarm:(\d+):", job.idempotency_key)
        return int(matched.group(1)) if matched else None

    async def _list_ocr_for_admin(
        self,
        filters: AdminBackgroundJobListQuery,
        *,
        limit: int,
    ) -> tuple[list[OcrJob], int]:
        if filters.job_type is not None and filters.job_type != BackgroundJobType.OCR:
            return [], 0

        query = OcrJob.all()
        keyword = filters.keyword.strip() if filters.keyword else ""
        if keyword:
            matched = re.fullmatch(r"OCR-(\d+)", keyword, flags=re.IGNORECASE)
            if matched:
                query = query.filter(id=int(matched.group(1)))
            elif keyword.upper() != "OCR":
                return [], 0
        if filters.status is not None:
            ocr_statuses = self._ocr_statuses_for(filters.status)
            if not ocr_statuses:
                return [], 0
            query = query.filter(status__in=ocr_statuses)
        if filters.start_date is not None:
            query = query.filter(created_at__gte=filters.start_date)
        if filters.end_date is not None:
            query = query.filter(created_at__lt=filters.end_date + timedelta(days=1))

        total = await query.count()
        jobs = await query.prefetch_related("user").order_by("-created_at", "-id").limit(limit)
        return jobs, total

    @staticmethod
    def _ocr_statuses_for(status: BackgroundJobStatus) -> tuple[OcrJobStatus, ...]:
        return {
            BackgroundJobStatus.QUEUED: (OcrJobStatus.QUEUED,),
            BackgroundJobStatus.PROCESSING: (OcrJobStatus.PROCESSING,),
            BackgroundJobStatus.RETRY_WAITING: (),
            BackgroundJobStatus.COMPLETED: (OcrJobStatus.READY_FOR_REVIEW, OcrJobStatus.COMPLETE),
            BackgroundJobStatus.FAILED: (OcrJobStatus.FAILED,),
            BackgroundJobStatus.CANCELLED: (OcrJobStatus.CANCELLED,),
        }[status]

    @staticmethod
    def _background_status_for_ocr(status: OcrJobStatus) -> BackgroundJobStatus:
        return {
            OcrJobStatus.QUEUED: BackgroundJobStatus.QUEUED,
            OcrJobStatus.PROCESSING: BackgroundJobStatus.PROCESSING,
            OcrJobStatus.READY_FOR_REVIEW: BackgroundJobStatus.COMPLETED,
            OcrJobStatus.COMPLETE: BackgroundJobStatus.COMPLETED,
            OcrJobStatus.FAILED: BackgroundJobStatus.FAILED,
            OcrJobStatus.CANCELLED: BackgroundJobStatus.CANCELLED,
        }[status]

    @classmethod
    def _ocr_list_item(cls, job: OcrJob) -> AdminBackgroundJobListItem:
        return AdminBackgroundJobListItem(
            job_id=f"OCR-{job.id}",
            job_type=BackgroundJobType.OCR,
            alarm_type=None,
            status=cls._background_status_for_ocr(job.status),
            user_id=job.user_id,
            user_name=getattr(job.user, "name", None),
            requested_at=job.created_at,
            error_code=job.error_code,
            error_message=None,
        )

    async def stats(self, start_date: date, end_date: date) -> BackgroundJobStatsResponse:
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="start_date must be on or before end_date.",
            )
        created_from = datetime.combine(start_date, time.min, tzinfo=config.TIMEZONE)
        created_to = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=config.TIMEZONE)
        stored_counts = await self.repository.count_by_status(created_from, created_to)
        counts = {job_status: stored_counts.get(job_status, 0) for job_status in BackgroundJobStatus}
        return BackgroundJobStatsResponse(
            start_date=start_date,
            end_date=end_date,
            total=sum(counts.values()),
            counts=counts,
        )

    async def stats_for_admin(self, start_date: date, end_date: date) -> BackgroundJobStatsResponse:
        result = await self.stats(start_date, end_date)
        created_from = datetime.combine(start_date, time.min, tzinfo=config.TIMEZONE)
        created_to = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=config.TIMEZONE)
        rows: list[dict[str, Any]] = (
            await OcrJob.filter(created_at__gte=created_from, created_at__lt=created_to)
            .annotate(total=Count("id"))
            .group_by("status")
            .values("status", "total")
        )
        counts = dict(result.counts)
        for row in rows:
            ocr_status = OcrJobStatus(row["status"])
            status = self._background_status_for_ocr(ocr_status)
            counts[status] += row["total"]
        return BackgroundJobStatsResponse(
            start_date=start_date,
            end_date=end_date,
            total=sum(counts.values()),
            counts=counts,
        )

    @staticmethod
    def alarm_idempotency_key(alarm_id: int, subscription_id: int, trigger_at: datetime) -> str:
        return f"alarm:{alarm_id}:{subscription_id}:{trigger_at.isoformat()}"

    async def create_alarm_job(
        self,
        alarm: Alarm,
        subscription: PushSubscription,
        trigger_at: datetime,
    ) -> tuple[BackgroundJob, bool]:
        key = self.alarm_idempotency_key(alarm.id, subscription.id, trigger_at)
        existing = await self.repository.get_by_idempotency_key(key)
        if existing is not None:
            return existing, False
        try:
            job = await self.repository.create(
                {
                    "idempotency_key": key,
                    "job_type": BackgroundJobType.ALARM,
                    "status": BackgroundJobStatus.QUEUED,
                    "user_id": alarm.user_id,
                    "reference_table": "alarms",
                    "reference_id": alarm.id,
                    "retry_count": 0,
                    "max_retry_count": config.ALARM_MAX_RETRY_COUNT,
                }
            )
        except IntegrityError:
            existing = await self.repository.get_by_idempotency_key(key)
            if existing is None:
                raise
            return existing, False
        return job, True

    async def enqueue(
        self,
        job: BackgroundJob,
        *,
        alarm_id: int,
        subscription_id: int,
        trigger_at: datetime,
        defer_seconds: int = 0,
    ) -> None:
        pool = self.redis_pool
        owns_pool = pool is None
        if pool is None:
            pool = await create_pool(
                RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
            )
        enqueue_options: dict[str, object] = {"_job_id": job.idempotency_key}
        if defer_seconds > 0:
            enqueue_options["_defer_by"] = timedelta(seconds=defer_seconds)
        try:
            await pool.enqueue_job(
                "send_alarm_push",
                job.id,
                alarm_id,
                subscription_id,
                trigger_at.isoformat(),
                **enqueue_options,
            )
        finally:
            if owns_pool:
                await pool.aclose()

    async def cancel(self, job_id: int) -> BackgroundJob:
        job = await self.get(job_id)
        if job.status == BackgroundJobStatus.CANCELLED:
            return job
        if job.status not in {BackgroundJobStatus.QUEUED, BackgroundJobStatus.RETRY_WAITING}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Background job cannot be cancelled.")
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.CANCELLED
        job.completed_at = now
        job.updated_at = now
        await job.save(update_fields=["status", "completed_at", "updated_at"])
        return job

    async def retry_failed(self, job_id: int) -> BackgroundJob:
        original = await self.get(job_id)
        if original.status != BackgroundJobStatus.FAILED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed jobs can be retried.")
        if original.error_code == "PUSH_DELIVERY_UNKNOWN":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="발송 결과가 불명확하여 재발송할 수 없습니다. 중복 알림 여부를 먼저 확인해주세요.",
            )
        if original.job_type != BackgroundJobType.ALARM or original.reference_table != "alarm_events":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job retry handler is not available.")
        event = await AlarmEvent.get_or_none(id=original.reference_id)
        if event is None or event.push_subscription_id is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm retry context is missing.")
        alarm = await Alarm.get_or_none(id=event.alarm_id)
        subscription = await PushSubscription.get_or_none(id=event.push_subscription_id)
        if alarm is None or subscription is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Alarm retry target is missing.")

        retried = await self.repository.create(
            {
                "idempotency_key": f"{original.idempotency_key}:manual:{uuid4().hex}",
                "job_type": original.job_type,
                "status": BackgroundJobStatus.QUEUED,
                "user_id": original.user_id,
                "retry_count": 0,
                "max_retry_count": original.max_retry_count,
                "parent_job_id": original.id,
            }
        )
        await self.enqueue(
            retried,
            alarm_id=alarm.id,
            subscription_id=subscription.id,
            trigger_at=event.event_at,
        )
        return retried
