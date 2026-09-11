from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.dependencies.intake_report import (
    get_intake_report_email_job_service,
    get_intake_report_email_service,
)
from app.dependencies.security import get_request_user
from app.main import app
from app.models.background_jobs import BackgroundJob
from app.models.email_verifications import EmailVerification
from app.models.enums import AccountStatus, BackgroundJobStatus, BackgroundJobType, EmailVerificationPurpose
from app.models.users import User
from app.services.intake_report_email import (
    INTAKE_REPORT_EMAIL_TOKEN_TTL_SECONDS,
    IntakeReportEmailNotVerifiedError,
    IntakeReportEmailService,
    IntakeReportEmailTokenError,
)


class TestIntakeReportEmailService(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.key = Fernet.generate_key().decode("ascii")
        self.service = IntakeReportEmailService(encryption_key=self.key)
        self.user = await User.create(
            email="Report.User@Example.com",
            hashed_password="hash",
            name="보고서 사용자",
            status=AccountStatus.ACTIVE,
        )

    def test_snapshot_is_bound_to_owner_and_cannot_be_tampered(self) -> None:
        token = self.service.create_snapshot_token(user=self.user, report_markdown="# 보고서\n\n제품명")
        assert token is not None

        snapshot = self.service.consume_snapshot_token(token=token, user=self.user)
        assert snapshot.recipient_email == "report.user@example.com"
        assert snapshot.report_markdown == "# 보고서\n\n제품명"

        with pytest.raises(IntakeReportEmailTokenError):
            self.service.consume_snapshot_token(token=token + "x", user=self.user)
        with pytest.raises(IntakeReportEmailTokenError):
            self.service.consume_snapshot_token(
                token=token,
                user=User(id=self.user.id + 1, email="other@example.com", hashed_password="hash", name="다른 사용자"),
            )

    def test_snapshot_expires_after_one_hour(self) -> None:
        old_payload = {
            "purpose": "intake-report-email-v1",
            "userId": self.user.id,
            "email": self.user.email.casefold(),
            "reportId": "report-id",
            "reportMarkdown": "# 보고서",
        }
        token = (
            Fernet(self.key.encode("ascii"))
            .encrypt_at_time(
                json.dumps(old_payload).encode("utf-8"),
                current_time=int(time.time()) - INTAKE_REPORT_EMAIL_TOKEN_TTL_SECONDS - 1,
            )
            .decode("ascii")
        )

        with pytest.raises(IntakeReportEmailTokenError):
            self.service.consume_snapshot_token(token=token, user=self.user)

    async def test_recipient_requires_signup_verified_active_user(self) -> None:
        with pytest.raises(IntakeReportEmailNotVerifiedError):
            await self.service.require_verified_recipient(user=self.user)

        await EmailVerification.create(
            email=self.user.email.casefold(),
            purpose=EmailVerificationPurpose.SIGNUP,
            code_digest="0" * 64,
            expires_at=datetime(2026, 9, 12, tzinfo=UTC),
            verified_at=datetime(2026, 9, 11, tzinfo=UTC),
        )
        assert await self.service.require_verified_recipient(user=self.user) == "report.user@example.com"

        self.user.status = AccountStatus.SUSPENDED
        await self.user.save(update_fields=["status"])
        with pytest.raises(IntakeReportEmailNotVerifiedError):
            await self.service.require_verified_recipient(user=self.user)

    async def test_status_api_only_returns_the_requesting_users_report_job(self) -> None:
        own_job = await BackgroundJob.create(
            idempotency_key="email:intake-report:owner:one",
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.RETRY_WAITING,
            user=self.user,
            reference_table="intake_reports",
            reference_id=self.user.id,
        )
        other_user = await User.create(
            email="other@example.com",
            hashed_password="hash",
            name="다른 사용자",
            status=AccountStatus.ACTIVE,
        )
        other_job = await BackgroundJob.create(
            idempotency_key="email:intake-report:other:one",
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.QUEUED,
            user=other_user,
            reference_table="intake_reports",
            reference_id=other_user.id,
        )
        app.dependency_overrides[get_request_user] = lambda: self.user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                own_response = await client.get(f"/api/v1/intake-reports/email/{own_job.id}")
                other_response = await client.get(f"/api/v1/intake-reports/email/{other_job.id}")
        finally:
            app.dependency_overrides.clear()

        assert own_response.status_code == status.HTTP_200_OK
        assert own_response.json() == {"jobId": own_job.id, "status": "RETRY_WAITING"}
        assert other_response.status_code == status.HTTP_404_NOT_FOUND


class StubSnapshotService:
    def consume_snapshot_token(self, *, token: str, user: object):
        assert token == "server-issued-token"
        assert user.id == 7  # type: ignore[attr-defined]
        return SimpleNamespace(report_markdown="# 서버 보고서", report_id="report-7")

    async def require_verified_recipient(self, *, user: object) -> str:
        assert user.email == "verified@example.com"  # type: ignore[attr-defined]
        return "verified@example.com"


class StubEmailJobService:
    def __init__(self, job_status: BackgroundJobStatus = BackgroundJobStatus.QUEUED) -> None:
        self.job = SimpleNamespace(id=91, status=job_status)
        self.calls: list[dict[str, object]] = []

    async def enqueue_intake_report(self, **kwargs):
        self.calls.append(kwargs)
        return self.job


async def test_email_api_only_enqueues_server_snapshot_to_verified_owner() -> None:
    job_service = StubEmailJobService()
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7, email="verified@example.com")
    app.dependency_overrides[get_intake_report_email_service] = lambda: StubSnapshotService()
    app.dependency_overrides[get_intake_report_email_job_service] = lambda: job_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/intake-reports/email", json={"emailToken": "server-issued-token"})
            repeated_response = await client.post(
                "/api/v1/intake-reports/email", json={"emailToken": "server-issued-token"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json() == {"jobId": 91, "status": "QUEUED"}
    assert repeated_response.status_code == status.HTTP_202_ACCEPTED
    assert repeated_response.json() == {"jobId": 91, "status": "QUEUED"}
    assert (
        job_service.calls
        == [
            {
                "user_id": 7,
                "recipient_email": "verified@example.com",
                "report_markdown": "# 서버 보고서",
                "report_id": "report-7",
            }
        ]
        * 2
    )


async def test_email_api_rejects_extra_client_content_and_queue_failure() -> None:
    app.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=7, email="verified@example.com")
    app.dependency_overrides[get_intake_report_email_service] = lambda: StubSnapshotService()
    app.dependency_overrides[get_intake_report_email_job_service] = lambda: StubEmailJobService(
        job_status=BackgroundJobStatus.FAILED
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            extra_response = await client.post(
                "/api/v1/intake-reports/email",
                json={"emailToken": "server-issued-token", "recipientEmail": "attacker@example.com"},
            )
            failed_response = await client.post(
                "/api/v1/intake-reports/email",
                json={"emailToken": "server-issued-token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert extra_response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert failed_response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
