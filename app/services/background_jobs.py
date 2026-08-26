from datetime import date, datetime, time, timedelta
from uuid import uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool
from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError

from app.core import config
from app.dtos.background_jobs import BackgroundJobFilter, BackgroundJobStatsResponse
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType
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
