import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from tortoise.contrib.test import TestCase
from tortoise.exceptions import DBConnectionError, OperationalError

from app.core import config
from app.models.alarms import Alarm, AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.care import FollowUpVisit
from app.models.enums import (
    AccountStatus,
    AlarmEventType,
    AlarmType,
    BackgroundJobStatus,
    MealSlot,
    SupplementStatus,
)
from app.models.supplement_nutrients import UserSupplementNutrient, UserSupplementNutrientSlot
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

    async def test_due_alarm_fans_out_one_job_per_active_subscription(self) -> None:
        second = await PushSubscription.create(
            user=self.user,
            endpoint="https://push.example.test/background-task-second",
            p256dh_key="p256dh-2",
            auth_key="auth-2",
        )

        job_ids = await self.executor().poll_due_alarm_job_ids()

        assert len(job_ids) == 2
        keys = set(await BackgroundJob.filter(id__in=job_ids).values_list("idempotency_key", flat=True))
        assert keys == {
            self.executor().idempotency_key(self.alarm.id, subscription_id, self.now)
            for subscription_id in (self.subscription.id, second.id)
        }

    async def test_due_alarm_without_subscription_records_failure(self) -> None:
        self.subscription.is_active = False
        await self.subscription.save(update_fields=["is_active"])

        assert await self.executor().poll_due_alarm_job_ids() == []

        assert await AlarmEvent.filter(
            alarm=self.alarm,
            event_type=AlarmEventType.FAILED,
            error_code="NO_ACTIVE_SUBSCRIPTION",
        ).exists()
        await self.alarm.refresh_from_db()
        assert self.alarm.last_triggered_at == self.now

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

    async def test_missing_nutrient_context_is_cancelled_without_push(self) -> None:
        job = await self.create_job()
        self.alarm.alarm_type = AlarmType.NUTRIENT
        self.alarm.care_episode_id = None
        await self.alarm.save(update_fields=["alarm_type", "care_episode_id"])

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        self.push_service.send.assert_not_awaited()

    async def test_missing_follow_up_context_is_cancelled_without_push(self) -> None:
        job = await self.create_job()
        self.alarm.alarm_type = AlarmType.FOLLOW_UP_VISIT
        self.alarm.meal_slot = None
        self.alarm.care_episode_id = None
        await self.alarm.save(update_fields=["alarm_type", "meal_slot", "care_episode_id"])

        await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        self.push_service.send.assert_not_awaited()

    async def test_nutrient_push_uses_current_active_slot_content(self) -> None:
        job = await self.create_job()
        self.alarm.alarm_type = AlarmType.NUTRIENT
        self.alarm.care_episode_id = None
        await self.alarm.save(update_fields=["alarm_type", "care_episode_id"])
        registration = await UserSupplementNutrient.create(
            user=self.user,
            supplement_nutrient_id=None,
            custom_name="현재 복용 중인 영양제",
            dose_amount=1,
            dose_unit="정",
            start_date=self.now.date(),
            status=SupplementStatus.ACTIVE,
        )
        await UserSupplementNutrientSlot.create(user_suppl_nutrient=registration, slot=MealSlot.MORNING)
        self.push_service.build_payload = WebPushService.build_payload
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await self.executor().run(job.id)

        payload = self.push_service.send.await_args.args[1]
        assert payload["title"] == "영양제 알림"
        assert payload["body"] == "영양제 챙기실 시간이에요"

    async def test_follow_up_push_uses_current_visit_details(self) -> None:
        job = await self.create_job()
        visit = await FollowUpVisit.create(
            user=self.user,
            visit_date=self.now.date() + timedelta(days=1),
            visit_time="14:30:00",
            hospital="서울성모병원",
        )
        self.alarm.alarm_type = AlarmType.FOLLOW_UP_VISIT
        self.alarm.meal_slot = None
        self.alarm.care_episode_id = None
        self.alarm.follow_up_visit_id = visit.id
        await self.alarm.save(update_fields=["alarm_type", "meal_slot", "care_episode_id", "follow_up_visit_id"])
        self.push_service.build_payload = WebPushService.build_payload
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await self.executor().run(job.id)

        payload = self.push_service.send.await_args.args[1]
        assert payload["title"] == "진료 일정 알림"
        assert payload["body"] == "내일 14:30 서울성모병원 진료가 있어요"

    async def test_guide_push_preserves_alarm_message(self) -> None:
        job = await self.create_job()
        self.alarm.alarm_type = AlarmType.GUIDE_CHECK
        self.alarm.title = "생활가이드 알림"
        self.alarm.message = "오늘의 생활가이드를 확인해 주세요."
        await self.alarm.save(update_fields=["alarm_type", "title", "message"])
        self.push_service.build_payload = WebPushService.build_payload
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await self.executor().run(job.id)

        payload = self.push_service.send.await_args.args[1]
        assert payload["title"] == "생활가이드 알림"
        assert payload["body"] == "오늘의 생활가이드를 확인해 주세요."

    async def test_cancelled_job_is_not_sent(self) -> None:
        job = await self.create_job()
        job.status = BackgroundJobStatus.CANCELLED
        await job.save(update_fields=["status"])

        await self.executor().run(job.id)

        self.push_service.send.assert_not_awaited()

    async def test_completion_deadlock_retries_database_without_resending_push(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "알림"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)
        original_save = PushSubscription.save
        attempts = 0

        async def flaky_save(instance, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError(1213, "Deadlock found")
            return await original_save(instance, *args, **kwargs)

        with patch.object(PushSubscription, "save", autospec=True, side_effect=flaky_save):
            await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert attempts == 2
        self.push_service.send.assert_awaited_once()
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).count() == 1

    async def test_failure_deadlock_retries_database_without_resending_push(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "알림"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.EXPIRED,
            410,
            "PUSH_SUBSCRIPTION_EXPIRED",
        )
        original_save = PushSubscription.save
        attempts = 0

        async def flaky_save(instance, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError(1213, "Deadlock found")
            return await original_save(instance, *args, **kwargs)

        with patch.object(PushSubscription, "save", autospec=True, side_effect=flaky_save):
            await self.executor().run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert attempts == 2
        self.push_service.send.assert_awaited_once()
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.FAILED).count() == 1

    async def test_completion_recovers_lost_commit_ack_without_duplicate_event(self) -> None:
        job = await self.create_job()
        self.push_service.build_payload.return_value = {"title": "알림"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)
        executor = self.executor()
        persist = executor._persist_push_completion
        attempts = 0

        async def lost_ack(*args):
            nonlocal attempts
            attempts += 1
            await persist(*args)
            if attempts == 1:
                raise DBConnectionError("commit acknowledgement lost")

        with patch.object(executor, "_persist_push_completion", side_effect=lost_ack):
            await executor.run(job.id)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert attempts == 2
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).count() == 1
        self.push_service.send.assert_awaited_once()

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

    async def test_recovery_preserves_processing_job_with_active_lease(self) -> None:
        job = await self.create_job()
        await BackgroundJob.filter(id=job.id).update(
            status=BackgroundJobStatus.PROCESSING,
            started_at=self.now,
            lease_expires_at=self.now + timedelta(minutes=1),
        )

        await self.executor().recover_stalled_processing(self.now)

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.PROCESSING

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


class FlakyPollingExecutor(RecordingExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.poll_count = 0
        self.recovered_after_failure = asyncio.Event()

    async def poll_due_alarm_job_ids(self) -> list[int]:
        self.poll_count += 1
        if self.poll_count == 2:
            raise RuntimeError("temporary database outage")
        if self.poll_count >= 3:
            self.recovered_after_failure.set()
        return []


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


async def test_manager_continues_polling_after_transient_tick_failure() -> None:
    executor = FlakyPollingExecutor()
    manager = AlarmBackgroundTaskManager(executor, poll_seconds=0.01)

    await manager.start()
    await asyncio.wait_for(executor.recovered_after_failure.wait(), timeout=0.1)
    await manager.shutdown()

    assert executor.poll_count >= 3
