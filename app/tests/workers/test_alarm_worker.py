from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from arq import Retry
from tortoise.contrib.test import TestCase

from app.core import config
from app.models.alarms import AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import AlarmEventType, AlarmType, BackgroundJobStatus
from app.models.users import UserSettings
from app.services.alarms import AlarmService
from app.services.background_jobs import BackgroundJobService
from app.services.web_push import PushResult, PushResultKind, WebPushService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request
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
        self.redis_pool.enqueue_job.assert_not_awaited()

    async def test_due_alarm_fans_out_one_job_per_active_subscription(self):
        await self.create_subscription("1")
        await self.create_subscription("2")

        await poll_due_alarms(self.context())

        assert await BackgroundJob.filter(status=BackgroundJobStatus.QUEUED).count() == 2
        assert self.redis_pool.enqueue_job.await_count == 2

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
