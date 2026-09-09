from datetime import datetime

from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.models.background_jobs import BackgroundJob
from app.models.enums import AdminRole, BackgroundJobStatus, BackgroundJobType, OcrJobStatus
from app.models.ocr import OcrJob
from app.models.users import User
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

    async def test_merges_ocr_jobs_and_searches_prefixed_ocr_job_id(self) -> None:
        user = await User.create(
            email="ocr-job-user@example.com",
            hashed_password="unused",
            name="OCR 사용자",
        )
        ocr_job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="admin-ocr-job",
            input_manifest={},
            ocr_model="clova-general-v2",
            schema_version="medication-guide-review/v3",
        )
        await OcrJob.filter(id=ocr_job.id).update(created_at=datetime(2026, 8, 20, 13, 0, tzinfo=config.TIMEZONE))
        background_job = await BackgroundJob.create(
            idempotency_key="admin-regular-job",
            job_type=BackgroundJobType.ALARM,
            status=BackgroundJobStatus.COMPLETED,
        )
        await BackgroundJob.filter(id=background_job.id).update(
            requested_at=datetime(2026, 8, 20, 12, 0, tzinfo=config.TIMEZONE)
        )

        merged = await request(
            "GET",
            ADMIN_JOBS_URL,
            headers=self.headers,
            params={"startDate": "2026-08-20", "endDate": "2026-08-20"},
        )
        searched = await request(
            "GET",
            ADMIN_JOBS_URL,
            headers=self.headers,
            params={"keyword": f"OCR-{ocr_job.id}"},
        )

        assert merged.status_code == status.HTTP_200_OK, merged.text
        assert merged.json()["totalCount"] == 2
        assert [item["jobId"] for item in merged.json()["items"]] == [f"OCR-{ocr_job.id}", background_job.id]
        assert merged.json()["items"][0] == {
            "jobId": f"OCR-{ocr_job.id}",
            "jobType": "OCR",
            "status": "COMPLETED",
            "userId": user.id,
            "userName": "OCR 사용자",
            "requestedAt": "2026-08-20T13:00:00+09:00",
            "errorCode": None,
            "errorMessage": None,
        }
        assert searched.status_code == status.HTTP_200_OK, searched.text
        assert searched.json()["totalCount"] == 1
        assert searched.json()["items"][0]["jobId"] == f"OCR-{ocr_job.id}"

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
        user = await User.create(email="ocr-stats@example.com", hashed_password="unused", name="OCR 통계")
        ocr_statuses = [
            OcrJobStatus.QUEUED,
            OcrJobStatus.PROCESSING,
            OcrJobStatus.READY_FOR_REVIEW,
            OcrJobStatus.COMPLETE,
            OcrJobStatus.FAILED,
            OcrJobStatus.CANCELLED,
        ]
        for index, ocr_status in enumerate(ocr_statuses):
            ocr_job = await OcrJob.create(
                user=user,
                status=ocr_status,
                idempotency_key=f"admin-ocr-stats-{ocr_status}",
                input_manifest={},
                ocr_model="clova-general-v2",
                schema_version="medication-guide-review/v3",
            )
            await OcrJob.filter(id=ocr_job.id).update(
                created_at=datetime(2026, 8, 20, 13, index, tzinfo=config.TIMEZONE)
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
            "total": 12,
            "counts": {
                "QUEUED": 2,
                "PROCESSING": 2,
                "RETRY_WAITING": 1,
                "COMPLETED": 3,
                "FAILED": 2,
                "CANCELLED": 2,
            },
        }
