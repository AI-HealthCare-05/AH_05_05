from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette import status
from tortoise.contrib.test import TestCase

from app.models.admins import Admin
from app.models.enums import AdminRole, BackgroundJobStatus
from app.services.email_jobs import EmailJobService
from app.tests.admin_apis.conftest import ADMIN_ACCOUNTS_URL, auth_header, create_admin, request

CREATE_PAYLOAD = {"name": "한지수", "email": "jisu@ozcoding.ai", "role": "STAFF", "isActive": True}


class TestAdminCreateQueuesMail(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.admin.id)

    async def test_reports_queued_email_job(self) -> None:
        job = SimpleNamespace(id=71, status=BackgroundJobStatus.QUEUED)
        with patch.object(
            EmailJobService,
            "enqueue_admin_temporary_password",
            new=AsyncMock(return_value=job),
        ):
            response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["emailJobId"] == 71
        assert response.json()["emailJobStatus"] == "QUEUED"

    async def test_queues_temporary_password_for_new_admin(self) -> None:
        job = SimpleNamespace(id=72, status=BackgroundJobStatus.QUEUED)
        enqueue = AsyncMock(return_value=job)
        with patch.object(EmailJobService, "enqueue_admin_temporary_password", new=enqueue):
            await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        enqueue.assert_awaited_once()
        arguments = enqueue.await_args.kwargs
        assert arguments["recipient_email"] == "jisu@ozcoding.ai"
        assert arguments["recipient_name"] == "한지수"
        assert arguments["temporary_password"]

    async def test_keeps_account_when_queue_registration_fails(self) -> None:
        job = SimpleNamespace(id=73, status=BackgroundJobStatus.FAILED)
        with patch.object(
            EmailJobService,
            "enqueue_admin_temporary_password",
            new=AsyncMock(return_value=job),
        ):
            response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["emailJobStatus"] == "FAILED"
        assert await Admin.filter(email="jisu@ozcoding.ai").exists()

    async def test_response_never_contains_plain_password(self) -> None:
        job = SimpleNamespace(id=74, status=BackgroundJobStatus.QUEUED)
        enqueue = AsyncMock(return_value=job)
        with patch.object(EmailJobService, "enqueue_admin_temporary_password", new=enqueue):
            response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        temporary_password = enqueue.await_args.kwargs["temporary_password"]
        assert temporary_password not in response.text
        assert not any("password" in key.lower() for key in response.json())
