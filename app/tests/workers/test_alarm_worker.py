from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry
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
from app.services.alarms import AlarmService
from app.services.background_jobs import BackgroundJobService
from app.services.web_push import PushResult, PushResultKind, WebPushService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request
from app.workers import alarm_worker
from app.workers.alarm_worker import poll_due_alarms, recover_background_jobs, send_alarm_push


class TestAlarmWorker(TestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.user = await create_user("alarm-worker@example.com")
        self.alarm = await AlarmService().create_alarm(self.user, medication_alarm_request())
        self.alarm.next_trigger_at = datetime.now(config.TIMEZONE) - timedelta(minutes=1)
        self.alarm.last_triggered_at = None
        await self.alarm.save(update_fields=["next_trigger_at", "last_triggered_at"])
        self.redis_pool = AsyncMock()
        self.redis_pool.enqueue_job.return_value = object()
        self.redis_pool.exists.return_value = False
        self.job_service = BackgroundJobService(redis_pool=self.redis_pool)
        self.push_service = MagicMock(spec=WebPushService)
        self.push_service.send = AsyncMock()

    def context(self) -> dict[str, object]:
        return {
            "redis": self.redis_pool,
            "job_service": self.job_service,
            "push_service": self.push_service,
        }

    async def create_subscription(self, suffix: str = "1") -> PushSubscription:
        return await PushSubscription.create(
            user=self.user,
            endpoint=f"https://push.example.test/worker-{suffix}",
            p256dh_key="p256dh",
            auth_key="auth",
        )

    async def create_job(self, subscription: PushSubscription) -> BackgroundJob:
        job, _ = await self.job_service.create_alarm_job(
            self.alarm,
            subscription,
            self.alarm.next_trigger_at,
        )
        return job

    async def assert_notification_setting_blocks_alarm(self, alarm_type: AlarmType, setting_name: str) -> None:
        self.alarm.alarm_type = alarm_type
        update_fields = ["alarm_type"]
        if alarm_type not in {AlarmType.MEDICATION, AlarmType.NUTRIENT}:
            self.alarm.meal_slot = None
            update_fields.append("meal_slot")
        await self.alarm.save(update_fields=update_fields)
        await UserSettings.create(user=self.user, **{setting_name: False})
        await self.create_subscription()

        await poll_due_alarms(self.context())

        assert await BackgroundJob.all().count() == 0
        event = await AlarmEvent.get(alarm=self.alarm, event_type=AlarmEventType.SKIPPED)
        assert event.payload == {"reason": "USER_NOTIFICATION_DISABLED"}
        await self.alarm.refresh_from_db()
        assert self.alarm.status == "ACTIVE"
        self.redis_pool.enqueue_job.assert_not_awaited()

    async def test_due_alarm_fans_out_one_job_per_active_subscription(self):
        await self.create_subscription("1")
        await self.create_subscription("2")

        await poll_due_alarms(self.context())

        assert await BackgroundJob.filter(status=BackgroundJobStatus.QUEUED).count() == 2
        assert self.redis_pool.enqueue_job.await_count == 2

    async def test_same_time_medication_nutrient_and_schedule_alarms_create_independent_jobs(self):
        subscription = await self.create_subscription()
        trigger_at = self.alarm.next_trigger_at
        nutrient_alarm = await Alarm.create(
            user=self.user,
            alarm_type=AlarmType.NUTRIENT,
            meal_slot=MealSlot.MORNING,
            title="영양제 알림",
            scheduled_at=trigger_at,
            next_trigger_at=trigger_at,
        )
        schedule_alarm = await Alarm.create(
            user=self.user,
            alarm_type=AlarmType.FOLLOW_UP_VISIT,
            title="일정 알림",
            scheduled_at=trigger_at,
            next_trigger_at=trigger_at,
        )

        await poll_due_alarms(self.context())

        jobs = await BackgroundJob.filter(status=BackgroundJobStatus.QUEUED).order_by("id")
        assert len(jobs) == 3
        assert {job.idempotency_key for job in jobs} == {
            self.job_service.alarm_idempotency_key(alarm_id, subscription.id, trigger_at)
            for alarm_id in (self.alarm.id, nutrient_alarm.id, schedule_alarm.id)
        }
        assert self.redis_pool.enqueue_job.await_count == 3

    async def test_disabled_medication_notification_skips_push_job(self):
        await self.assert_notification_setting_blocks_alarm(
            AlarmType.MEDICATION,
            "is_notify_medication",
        )

    async def test_disabled_schedule_notification_skips_push_job(self):
        await self.assert_notification_setting_blocks_alarm(
            AlarmType.FOLLOW_UP_VISIT,
            "is_notify_schedule",
        )

    async def test_disabled_guide_notification_skips_push_job(self):
        await self.assert_notification_setting_blocks_alarm(
            AlarmType.GUIDE_CHECK,
            "is_notify_guide",
        )

    async def test_disabled_nutrient_notification_skips_push_job(self):
        await self.assert_notification_setting_blocks_alarm(
            AlarmType.NUTRIENT,
            "is_notify_supplement",
        )

    async def assert_account_status_blocks_alarm(self, status: AccountStatus) -> None:
        self.user.status = status
        await self.user.save(update_fields=["status"])
        await self.create_subscription()

        await poll_due_alarms(self.context())

        assert await BackgroundJob.all().count() == 0
        event = await AlarmEvent.get(alarm=self.alarm, event_type=AlarmEventType.SKIPPED)
        assert event.payload == {"reason": "USER_NOT_ACTIVE"}

    async def test_skips_delivery_when_user_withdrawn(self):
        await self.assert_account_status_blocks_alarm(AccountStatus.WITHDRAWN)

    async def test_skips_delivery_when_user_suspended(self):
        await self.assert_account_status_blocks_alarm(AccountStatus.SUSPENDED)

    async def test_withdrawn_after_queue_skips_send(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.user.status = AccountStatus.WITHDRAWN
        await self.user.save(update_fields=["status"])

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        event = await AlarmEvent.get(alarm=self.alarm, event_type=AlarmEventType.SKIPPED)
        assert event.payload == {"reason": "USER_NOT_ACTIVE"}
        self.push_service.send.assert_not_awaited()

    async def test_notification_disabled_after_queue_skips_send(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        await UserSettings.create(user=self.user, is_notify_medication=False)

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.CANCELLED
        assert await AlarmEvent.filter(
            alarm=self.alarm,
            event_type=AlarmEventType.SKIPPED,
        ).exists()
        self.push_service.send.assert_not_awaited()

    async def test_successful_push_creates_sent_event_and_completes_job(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert job.reference_table == "alarm_events"
        assert await AlarmEvent.filter(
            alarm=self.alarm,
            push_subscription=subscription,
            event_type=AlarmEventType.SENT,
        ).exists()

    async def test_nutrient_push_uses_current_active_slot_content(self):
        self.alarm.alarm_type = AlarmType.NUTRIENT
        self.alarm.care_episode_id = None
        self.alarm.title = "오래된 제목"
        self.alarm.message = "오래된 문구"
        await self.alarm.save(
            update_fields=["alarm_type", "care_episode_id", "title", "message"],
        )
        registration = await UserSupplementNutrient.create(
            user=self.user,
            supplement_nutrient_id=None,
            custom_name="현재 복용 중인 영양제",
            dose_amount=1,
            dose_unit="정",
            start_date=datetime.now(config.TIMEZONE).date(),
            status=SupplementStatus.ACTIVE,
        )
        await UserSupplementNutrientSlot.create(
            user_suppl_nutrient=registration,
            slot=MealSlot.MORNING,
        )
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload = WebPushService.build_payload
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        payload = self.push_service.send.await_args.args[1]
        assert payload["title"] == "영양제 알림"
        assert payload["body"] == "영양제 챙기실 시간이에요"

    async def test_follow_up_push_uses_current_visit_time_and_hospital(self):
        visit = await FollowUpVisit.create(
            user=self.user,
            visit_date=datetime.now(config.TIMEZONE).date() + timedelta(days=1),
            visit_time="14:30:00",
            hospital="서울성모병원",
        )
        self.alarm.alarm_type = AlarmType.FOLLOW_UP_VISIT
        self.alarm.meal_slot = None
        self.alarm.care_episode_id = None
        self.alarm.follow_up_visit_id = visit.id
        self.alarm.title = "오래된 제목"
        self.alarm.message = "오래된 문구"
        await self.alarm.save(
            update_fields=[
                "alarm_type",
                "meal_slot",
                "care_episode_id",
                "follow_up_visit_id",
                "title",
                "message",
            ],
        )
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload = WebPushService.build_payload
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        payload = self.push_service.send.await_args.args[1]
        assert payload["title"] == "진료 일정 알림"
        assert payload["body"] == "내일 14:30 서울성모병원 진료가 있어요"

    async def test_retryable_failure_moves_job_to_retry_waiting(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.RETRYABLE,
            503,
            "PUSH_TEMPORARY_ERROR",
        )

        with pytest.raises(Retry):
            await send_alarm_push(
                self.context(),
                job.id,
                self.alarm.id,
                subscription.id,
                self.alarm.next_trigger_at.isoformat(),
            )

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.RETRY_WAITING
        assert job.retry_count == 1

    async def test_expired_subscription_is_deactivated(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.EXPIRED,
            410,
            "PUSH_SUBSCRIPTION_EXPIRED",
        )

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        await subscription.refresh_from_db()
        await job.refresh_from_db()
        assert subscription.is_active is False
        assert job.status == BackgroundJobStatus.FAILED

    async def test_due_alarm_without_subscription_records_failure(self):
        await poll_due_alarms(self.context())

        assert await AlarmEvent.filter(
            alarm=self.alarm,
            event_type=AlarmEventType.FAILED,
            error_code="NO_ACTIVE_SUBSCRIPTION",
        ).exists()
        await self.alarm.refresh_from_db()
        assert self.alarm.last_triggered_at is not None

    async def test_retryable_failure_over_limit_becomes_failed(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        job.max_retry_count = 0
        await job.save(update_fields=["max_retry_count"])
        self.push_service.build_payload.return_value = {"title": "아침약"}
        self.push_service.send.return_value = PushResult(
            PushResultKind.RETRYABLE,
            503,
            "PUSH_TEMPORARY_ERROR",
        )

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.retry_count == 1

    async def test_cancelled_job_is_not_sent(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        job.status = BackgroundJobStatus.CANCELLED
        await job.save(update_fields=["status"])

        await send_alarm_push(
            self.context(),
            job.id,
            self.alarm.id,
            subscription.id,
            self.alarm.next_trigger_at.isoformat(),
        )

        self.push_service.send.assert_not_awaited()

    async def test_recovery_enqueues_stale_queued_job(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        job.requested_at = datetime.now(config.TIMEZONE) - timedelta(minutes=5)
        await job.save(update_fields=["requested_at"])

        await recover_background_jobs(self.context())

        self.redis_pool.enqueue_job.assert_awaited_once()

    async def test_completion_deadlock_retries_database_without_resending_push(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
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
            await send_alarm_push(
                self.context(), job.id, self.alarm.id, subscription.id, self.alarm.next_trigger_at.isoformat()
            )
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert attempts == 2
        self.push_service.send.assert_awaited_once()
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).count() == 1

    async def test_recovery_closes_stalled_processing_without_resending(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        started = datetime.now(config.TIMEZONE) - timedelta(minutes=10)
        events_before = await AlarmEvent.filter(alarm=self.alarm).count()
        await BackgroundJob.filter(id=job.id).update(status=BackgroundJobStatus.PROCESSING, started_at=started)
        await recover_background_jobs(self.context())
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.error_code == "PUSH_DELIVERY_UNKNOWN"
        assert job.completed_at is not None
        assert job.started_at == started
        self.push_service.send.assert_not_awaited()
        self.redis_pool.enqueue_job.assert_not_awaited()
        assert await AlarmEvent.filter(alarm=self.alarm).count() == events_before

    async def test_completion_recovers_lost_commit_ack_without_duplicate_event(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload.return_value = {"title": "알림"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)
        persist = alarm_worker._persist_push_completion
        attempts = 0

        async def lost_ack(*args):
            nonlocal attempts
            attempts += 1
            await persist(*args)
            if attempts == 1:
                raise DBConnectionError("commit acknowledgement lost")

        with patch.object(alarm_worker, "_persist_push_completion", side_effect=lost_ack):
            await send_alarm_push(
                self.context(), job.id, self.alarm.id, subscription.id, self.alarm.next_trigger_at.isoformat()
            )
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).count() == 1
        self.push_service.send.assert_awaited_once()

    async def test_exhausted_completion_retries_are_recovered_without_resending(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        self.push_service.build_payload.return_value = {"title": "알림"}
        self.push_service.send.return_value = PushResult(PushResultKind.SUCCESS, 201)
        with patch.object(PushSubscription, "save", side_effect=OperationalError(1213, "Deadlock")) as save:
            with pytest.raises(OperationalError):
                await send_alarm_push(
                    self.context(), job.id, self.alarm.id, subscription.id, self.alarm.next_trigger_at.isoformat()
                )
            assert save.await_count == 3
        await BackgroundJob.filter(id=job.id).update(started_at=datetime.now(config.TIMEZONE) - timedelta(minutes=10))
        await recover_background_jobs(self.context())
        await recover_background_jobs(self.context())
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.FAILED
        assert job.error_code == "PUSH_DELIVERY_UNKNOWN"
        assert not await AlarmEvent.filter(alarm=self.alarm, event_type=AlarmEventType.SENT).exists()
        self.push_service.send.assert_awaited_once()
        self.redis_pool.enqueue_job.assert_not_awaited()

    async def test_recovery_preserves_recent_and_actively_locked_processing(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        await BackgroundJob.filter(id=job.id).update(
            status=BackgroundJobStatus.PROCESSING, started_at=datetime.now(config.TIMEZONE)
        )
        await recover_background_jobs(self.context())
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.PROCESSING
        await BackgroundJob.filter(id=job.id).update(started_at=datetime.now(config.TIMEZONE) - timedelta(minutes=10))
        self.redis_pool.exists.return_value = True
        await recover_background_jobs(self.context())
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.PROCESSING
        self.redis_pool.enqueue_job.assert_not_awaited()

    async def test_recovery_does_not_overwrite_completion_during_lock_check(self):
        subscription = await self.create_subscription()
        job = await self.create_job(subscription)
        await BackgroundJob.filter(id=job.id).update(
            status=BackgroundJobStatus.PROCESSING, started_at=datetime.now(config.TIMEZONE) - timedelta(minutes=10)
        )

        async def complete_while_checking(_key):
            await BackgroundJob.filter(id=job.id).update(status=BackgroundJobStatus.COMPLETED)
            return False

        self.redis_pool.exists.side_effect = complete_while_checking
        await recover_background_jobs(self.context())
        await job.refresh_from_db()
        assert job.status == BackgroundJobStatus.COMPLETED
        assert job.error_code is None
