from datetime import datetime
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.job_router import get_background_job_service
from app.core import config
from app.main import app
from app.models.alarms import AlarmEvent, PushSubscription
from app.models.background_jobs import BackgroundJob
from app.models.enums import AlarmEventType, BackgroundJobStatus, BackgroundJobType
from app.services.alarms import AlarmService
from app.services.background_jobs import BackgroundJobService
from app.tests.alarm_apis.helpers import create_user, medication_alarm_request

INTERNAL_HEADERS = {"X-Internal-API-Key": "test-internal-key"}


class TestJobAPI(TestCase):
    async def test_job_list_requires_internal_key(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/internal/jobs")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_job_list_is_not_scoped_by_user(self):
        first_user = await create_user("job-list-first@example.com")
        second_user = await create_user("job-list-second@example.com")
        await BackgroundJob.create(
            idempotency_key="job-list-first",
            job_type=BackgroundJobType.ALARM,
            user=first_user,
        )
        await BackgroundJob.create(
            idempotency_key="job-list-second",
            job_type=BackgroundJobType.CHAT,
            user=second_user,
        )

        with patch.object(config, "INTERNAL_API_KEY", "test-internal-key"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/internal/jobs", headers=INTERNAL_HEADERS)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total"] == 2

    async def test_job_stats_counts_statuses_by_inclusive_created_date_range(self):
        jobs = []
        for index, job_status in enumerate(
            [BackgroundJobStatus.QUEUED, BackgroundJobStatus.COMPLETED, BackgroundJobStatus.COMPLETED]
        ):
            job = await BackgroundJob.create(
                idempotency_key=f"job-stats-inside-{index}",
                job_type=BackgroundJobType.ALARM,
                status=job_status,
            )
            jobs.append(job)

        outside = await BackgroundJob.create(
            idempotency_key="job-stats-outside",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.FAILED,
        )
        await BackgroundJob.filter(id=jobs[0].id).update(created_at=datetime(2026, 8, 10, 0, 0, tzinfo=config.TIMEZONE))
        await BackgroundJob.filter(id=jobs[1].id).update(
            created_at=datetime(2026, 8, 11, 12, 30, tzinfo=config.TIMEZONE)
        )
        await BackgroundJob.filter(id=jobs[2].id).update(
            created_at=datetime(2026, 8, 12, 23, 59, 59, tzinfo=config.TIMEZONE)
        )
        await BackgroundJob.filter(id=outside.id).update(created_at=datetime(2026, 8, 13, 0, 0, tzinfo=config.TIMEZONE))

        with patch.object(config, "INTERNAL_API_KEY", "test-internal-key"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/internal/jobs/stats",
                    params={"start_date": "2026-08-10", "end_date": "2026-08-12"},
                    headers=INTERNAL_HEADERS,
                )

        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == {
            "start_date": "2026-08-10",
            "end_date": "2026-08-12",
            "total": 3,
            "counts": {
                "QUEUED": 1,
                "PROCESSING": 0,
                "RETRY_WAITING": 0,
                "COMPLETED": 2,
                "FAILED": 0,
                "CANCELLED": 0,
            },
        }

    async def test_job_stats_rejects_reversed_date_range(self):
        with patch.object(config, "INTERNAL_API_KEY", "test-internal-key"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/internal/jobs/stats",
                    params={"start_date": "2026-08-12", "end_date": "2026-08-10"},
                    headers=INTERNAL_HEADERS,
                )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_queued_job_can_be_cancelled(self):
        job = await BackgroundJob.create(
            idempotency_key="job-api-cancel",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.QUEUED,
        )

        with patch.object(config, "INTERNAL_API_KEY", "test-internal-key"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/internal/jobs/{job.id}/cancel",
                    headers=INTERNAL_HEADERS,
                )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == BackgroundJobStatus.CANCELLED

    async def test_failed_alarm_job_can_be_retried(self):
        user = await create_user("job-retry-api@example.com")
        alarm = await AlarmService().create_alarm(user, medication_alarm_request())
        subscription = await PushSubscription.create(
            user=user,
            endpoint="https://push.example.test/job-retry-api",
            p256dh_key="p256dh",
            auth_key="auth",
        )
        event = await AlarmEvent.create(
            alarm=alarm,
            event_type=AlarmEventType.FAILED,
            push_subscription=subscription,
        )
        failed = await BackgroundJob.create(
            idempotency_key="job-api-retry",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.FAILED,
            reference_table="alarm_events",
            reference_id=event.id,
        )
        redis_pool = AsyncMock()
        redis_pool.enqueue_job.return_value = object()
        app.dependency_overrides[get_background_job_service] = lambda: BackgroundJobService(redis_pool=redis_pool)
        try:
            with patch.object(config, "INTERNAL_API_KEY", "test-internal-key"):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/internal/jobs/{failed.id}/retry",
                        headers=INTERNAL_HEADERS,
                    )
        finally:
            app.dependency_overrides.pop(get_background_job_service, None)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["parent_job_id"] == failed.id
