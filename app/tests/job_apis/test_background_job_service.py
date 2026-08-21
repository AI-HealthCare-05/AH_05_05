from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, status
from tortoise.contrib.test import TestCase

from app.models.alarms import AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import AlarmEventType, BackgroundJobStatus, BackgroundJobType
from app.services.alarms import AlarmService
from app.services.background_jobs import BackgroundJobService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request


class TestBackgroundJobService(TestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.user = await create_user("background-job@example.com")
        self.alarm = await AlarmService().create_alarm(self.user, medication_alarm_request())
        self.subscription = await PushSubscription.create(
            user=self.user,
            endpoint="https://push.example.test/background-job",
            p256dh_key="p256dh",
            auth_key="auth",
        )
        self.redis_pool = AsyncMock()
        self.redis_pool.enqueue_job.return_value = object()
        self.service = BackgroundJobService(redis_pool=self.redis_pool)

    async def test_alarm_job_creation_is_idempotent(self):
        first, first_created = await self.service.create_alarm_job(
            self.alarm,
            self.subscription,
            self.alarm.next_trigger_at,
        )
        second, second_created = await self.service.create_alarm_job(
            self.alarm,
            self.subscription,
            self.alarm.next_trigger_at,
        )

        assert first.id == second.id
        assert first_created is True
        assert second_created is False

    async def test_manual_retry_creates_child_of_failed_job(self):
        event = await AlarmEvent.create(
            alarm=self.alarm,
            event_type=AlarmEventType.FAILED,
            push_subscription=self.subscription,
            error_code="PUSH_FAILED",
        )
        failed = await BackgroundJob.create(
            idempotency_key="failed-alarm-job",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.FAILED,
            user=self.user,
            reference_table="alarm_events",
            reference_id=event.id,
            max_retry_count=3,
        )

        retried = await self.service.retry_failed(failed.id)

        assert retried.parent_job_id == failed.id
        assert retried.status == BackgroundJobStatus.QUEUED
        assert retried.idempotency_key != failed.idempotency_key
        self.redis_pool.enqueue_job.assert_awaited_once()

    async def test_processing_job_cannot_be_cancelled(self):
        job = await BackgroundJob.create(
            idempotency_key="processing-job",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.PROCESSING,
        )

        with pytest.raises(HTTPException) as error:
            await self.service.cancel(job.id)

        assert error.value.status_code == status.HTTP_409_CONFLICT
