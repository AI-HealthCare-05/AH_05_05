import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from tortoise.contrib.test import TestCase

from app.core import config
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import (
    AccountStatus,
    AlarmEventType,
    AlarmType,
    BackgroundJobStatus,
    MealSlot,
)
from app.models.users import UserSettings
from app.services.alarm_background_tasks import (
    ALARM_TASK_LEASE,
    AlarmBackgroundTaskExecutor,
    AlarmBackgroundTaskManager,
)
from app.services.alarms import AlarmService
from app.services.web_push import PushResult, PushResultKind, WebPushService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request


class TestAlarmBackgroundTaskExecutor(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.now = datetime.now(config.TIMEZONE).replace(microsecond=0)
        self.user = await create_user("alarm-background-task@example.com")
        request = medication_alarm_request().model_copy(update={"scheduled_at": self.now})
        self.alarm = await AlarmService().create_alarm(self.user, request)
        self.subscription = await PushSubscription.create(
            user=self.user,
            endpoint="https://push.example.test/background-task",
            p256dh_key="p256dh",
            auth_key="auth",
        )
        self.push_service = AsyncMock(spec=WebPushService)

    def executor(self) -> AlarmBackgroundTaskExecutor:
        return AlarmBackgroundTaskExecutor(
            push_service=self.push_service,
            now_provider=lambda: self.now,
        )

    async def create_job(self) -> BackgroundJob:
        return await BackgroundJob.create(
            idempotency_key=f"alarm:{self.alarm.id}:{self.subscription.id}:{self.now.isoformat()}",
            job_type="ALARM",
            status=BackgroundJobStatus.QUEUED,
            user=self.user,
            reference_table="alarms",
            reference_id=self.alarm.id,
            max_retry_count=3,
        )

    async def test_successful_push_completes_claimed_job(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert job.lease_expires_at is None
        self.push_service.send.assert_awaited_once()

    async def test_retryable_push_persists_next_attempt_without_arq_retry(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.RETRYABLE,
            503,
            "PUSH_TEMPORARY_ERROR",
        )

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.RETRY_WAITING
        assert job.retry_count == 1
        assert job.next_attempt_at == self.now + timedelta(seconds=config.ALARM_RETRY_BASE_SECONDS)
        assert job.lease_expires_at is None

    async def test_claim_sets_alarm_lease(self) -> None:
        job = await self.create_job()
        executor = self.executor()

        assert await executor.claim(job.id, self.now) is True

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.PROCESSING
        assert job.lease_expires_at == self.now + ALARM_TASK_LEASE

    async def test_expired_processing_lease_becomes_unknown_without_push(self) -> None:
        job = await self.create_job()
        await BackgroundJob.filter(id=job.id).update(
            status=BackgroundJobStatus.PROCESSING,
            started_at=self.now - timedelta(minutes=10),
            lease_expires_at=self.now - timedelta(seconds=1),
        )

        await self.executor().recover_stalled_processing(self.now)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.error_code == "PUSH_DELIVERY_UNKNOWN"
        self.push_service.send.assert_not_awaited()

    async def test_same_time_alarm_types_create_independent_jobs(self) -> None:
        nutrient_alarm = await Alarm.create(
            user=self.user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.MORNING,
            title="영양제",
            scheduled_at=self.now,
            next_trigger_at=self.now,
        )
        visit_alarm = await Alarm.create(
            user=self.user,
            alarm_type=AlarmType.FOLLOW_UP_VISIT,
            title="진료일정",
            scheduled_at=self.now,
            next_trigger_at=self.now,
        )

        job_ids = await self.executor().poll_due_alarm_job_ids()

        jobs = await BackgroundJob.filter(id__in=job_ids)
        assert len(jobs) == 3
        assert {job.reference_id for job in jobs} == {self.alarm.id, nutrient_alarm.id, visit_alarm.id}

    async def test_concurrent_claim_sends_only_once(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)
        executor = self.executor()

        await asyncio.gather(executor.run(job.id), executor.run(job.id))

        self.push_service.send.assert_awaited_once()
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).count() == 1

    async def test_retry_exhaustion_fails_job(self) -> None:
        job = await self.create_job()
        job.max_retry_count = 0
        await job.save(update_fields=["max_retry_count"])
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.RETRYABLE,
            503,
            "PUSH_TEMPORARY_ERROR",
        )

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.retry_count == 1

    async def test_expired_subscription_is_deactivated(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.EXPIRED,
            410,
            "PUSH_SUBSCRIPTION_EXPIRED",
        )

        await self.executor().run(job.id)

        await job.refresh_from_db()
        await self.subscription.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert self.subscription.is_active is False

    async def test_inactive_user_is_cancelled_without_push(self) -> None:
        job = await self.create_job()
        self.user.status = AccountStatus.SUSPENDED
        await self.user.save(update_fields=["status"])

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SKIPPED).exists()
        self.push_service.send.assert_not_awaited()

    async def test_disabled_notification_is_cancelled_without_push(self) -> None:
        job = await self.create_job()
        await UserSettings.create(user=self.user, is_notify_medication=False)

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        self.push_service.send.assert_not_awaited()

    async def test_legacy_stale_processing_becomes_unknown(self) -> None:
        job = await self.create_job()
        await BackgroundJob.filter(id=job.id).update(
            status=BackgroundJobStatus.PROCESSING,
            started_at=self.now - timedelta(minutes=10),
            lease_expires_at=None,
        )

        await self.executor().recover_stalled_processing(self.now)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.error_code == "PUSH_DELIVERY_UNKNOWN"

    async def test_recovery_returns_only_queued_and_due_retry_jobs(self) -> None:
        queued = await self.create_job()
        due = await BackgroundJob.create(
            idempotency_key="alarm:due:retry",
            job_type="ALARM",
            status=BackgroundJobStatus.RETRY_WAITING,
            next_attempt_at=self.now,
        )
        future = await BackgroundJob.create(
            idempotency_key="alarm:future:retry",
            job_type="ALARM",
            status=BackgroundJobStatus.RETRY_WAITING,
            next_attempt_at=self.now + timedelta(minutes=1),
        )

        job_ids = await self.executor().recoverable_job_ids(self.now)

        assert queued.id in job_ids
        assert due.id in job_ids
        assert future.id not in job_ids


class RecordingExecutor:
    def __init__(self, *, recoverable: list[int] | None = None, due: list[int] | None = None) -> None:
        self.recoverable = recoverable or []
        self.due = due or []
        self.recovered = False
        self.polled = asyncio.Event()
        self.run_ids: list[int] = []

    async def recover_stalled_processing(self, _now: datetime) -> None:
        self.recovered = True

    async def recoverable_job_ids(self, _now: datetime) -> list[int]:
        return self.recoverable

    async def poll_due_alarm_job_ids(self) -> list[int]:
        self.polled.set()
        return self.due

    async def run(self, job_id: int) -> None:
        self.run_ids.append(job_id)


class BlockingExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, job_id: int) -> None:
        self.run_ids.append(job_id)
        self.started.set()
        await self.release.wait()


async def test_manager_recovers_then_polls_without_http_requests() -> None:
    executor = RecordingExecutor(recoverable=[11], due=[12])
    manager = AlarmBackgroundTaskManager(executor, poll_seconds=0.01)

    await manager.start()
    await asyncio.wait_for(executor.polled.wait(), timeout=0.1)
    await manager.wait_until_idle()
    await manager.shutdown()

    assert executor.recovered is True
    assert {11, 12} <= set(executor.run_ids)


async def test_manager_deduplicates_local_job_start() -> None:
    executor = BlockingExecutor()
    manager = AlarmBackgroundTaskManager(executor, poll_seconds=60)

    await asyncio.gather(manager.start_job(31), manager.start_job(31))
    await asyncio.wait_for(executor.started.wait(), timeout=0.1)

    assert executor.run_ids == [31]
    executor.release.set()
    await manager.wait_until_idle()
    await manager.shutdown()


async def test_manager_shutdown_cancels_running_jobs() -> None:
    executor = BlockingExecutor()
    manager = AlarmBackgroundTaskManager(executor, poll_seconds=60)

    await manager.start_job(41)
    await asyncio.wait_for(executor.started.wait(), timeout=0.1)
    await manager.shutdown()

    assert manager.active_job_ids == set()
