from datetime import datetime

from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.models.background_jobs import BackgroundJob
from app.models.enums import AdminRole, BackgroundJobStatus, BackgroundJobType
from app.tests.admin_apis.conftest import auth_header, create_admin, request

ADMIN_JOBS_URL = "/api/v1/admin/jobs"
ADMIN_JOB_STATS_URL = "/api/v1/admin/jobs/stats"


class TestAdminJobAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="운영자", email="jobs-admin@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.admin.id)

    async def test_filters_actual_jobs_with_all_search_conditions(self) -> None:
        matched = await BackgroundJob.create(
            idempotency_key="admin-job-matched",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.FAILED,
            error_code="PUSH_FAILED",
            error_message="push delivery failed",
        )
        excluded = await BackgroundJob.create(
            idempotency_key="admin-job-excluded",
            job_type=BackgroundJobType.CHAT,
            status=BackgroundJobStatus.COMPLETED,
        )
        await BackgroundJob.filter(id=matched.id).update(
            requested_at=datetime(2026, 8, 20, 23, 59, 59, tzinfo=config.TIMEZONE)
        )
        await BackgroundJob.filter(id=excluded.id).update(
            requested_at=datetime(2026, 8, 21, 0, 0, tzinfo=config.TIMEZONE)
        )

        response = await request(
            "GET",
            ADMIN_JOBS_URL,
            headers=self.headers,
            params={
                "keyword": str(matched.id),
                "jobType": "ALARM",
                "status": "FAILED",
                "startDate": "2026-08-20",
                "endDate": "2026-08-20",
            },
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == {
            "items": [
                {
                    "jobId": matched.id,
                    "jobType": "ALARM",
                    "status": "FAILED",
                    "userId": None,
                    "userName": None,
                    "requestedAt": "2026-08-20T23:59:59+09:00",
                    "errorCode": "PUSH_FAILED",
                    "errorMessage": "push delivery failed",
                }
            ],
            "totalCount": 1,
            "page": 1,
            "size": 20,
        }

    async def test_requires_admin_authentication(self) -> None:
        response = await request("GET", ADMIN_JOBS_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_returns_status_counts_for_selected_date_range(self) -> None:
        statuses = [
            BackgroundJobStatus.QUEUED,
            BackgroundJobStatus.PROCESSING,
            BackgroundJobStatus.RETRY_WAITING,
            BackgroundJobStatus.COMPLETED,
            BackgroundJobStatus.FAILED,
            BackgroundJobStatus.CANCELLED,
        ]
        for index, job_status in enumerate(statuses):
            job = await BackgroundJob.create(
                idempotency_key=f"admin-stats-{job_status}",
                job_type=BackgroundJobType.ALARM,
                status=job_status,
            )
            await BackgroundJob.filter(id=job.id).update(
                created_at=datetime(2026, 8, 20, 12, index, tzinfo=config.TIMEZONE)
            )

        response = await request(
            "GET",
            ADMIN_JOB_STATS_URL,
            headers=self.headers,
            params={"startDate": "2026-08-20", "endDate": "2026-08-20"},
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == {
            "startDate": "2026-08-20",
            "endDate": "2026-08-20",
            "total": 6,
            "counts": {
                "QUEUED": 1,
                "PROCESSING": 1,
                "RETRY_WAITING": 1,
                "COMPLETED": 1,
                "FAILED": 1,
                "CANCELLED": 1,
            },
        }
