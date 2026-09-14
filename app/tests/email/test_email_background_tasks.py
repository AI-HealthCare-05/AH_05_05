import asyncio
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate
from app.core.email.renderer import EmailTemplateRenderer
from app.core.email.smtp_sender import EmailDeliveryError, SmtpEmailSender
from app.core.utils.security import hash_password, verify_password
from app.models.background_jobs import BackgroundJob
from app.models.email_verifications import EmailVerification
from app.models.enums import AccountStatus, BackgroundJobStatus, BackgroundJobType, EmailVerificationPurpose
from app.models.users import User
from app.services.admin_settings import SmtpRuntimeSettings
from app.services.email_background_tasks import EmailBackgroundTaskExecutor, EmailBackgroundTaskManager


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)
        await asyncio.sleep(0)


class FakeSmtpSettingsService:
    def __init__(self) -> None:
        self.error: Exception | None = None

    async def get_runtime_settings(self) -> SmtpRuntimeSettings:
        if self.error is not None:
            raise self.error
        return SmtpRuntimeSettings(
            host="smtp.example.com",
            port=2525,
            username="sender@example.com",
            password="secret",
            from_email="from@example.com",
        )


class BlockingExecutor:
    def __init__(self, recoverable_ids: list[int] | None = None) -> None:
        self.recoverable_ids = recoverable_ids or []
        self.run_calls: list[int] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def recoverable_job_ids(self, _now: datetime) -> list[int]:
        return self.recoverable_ids

    async def run(self, job_id: int) -> None:
        self.run_calls.append(job_id)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.mark.asyncio
async def test_manager_deduplicates_same_job_inside_one_process() -> None:
    executor = BlockingExecutor()
    manager = EmailBackgroundTaskManager(executor)

    await asyncio.gather(manager.start(17), manager.start(17))
    await executor.started.wait()

    assert executor.run_calls == [17]
    executor.release.set()
    await manager.wait_until_idle()


@pytest.mark.asyncio
async def test_manager_recovers_jobs_and_shutdown_cancels_owned_tasks() -> None:
    executor = BlockingExecutor([2, 5, 9])
    manager = EmailBackgroundTaskManager(executor, now_provider=lambda: datetime.now(config.TIMEZONE))

    await manager.recover()
    await executor.started.wait()
    assert sorted(executor.run_calls) == [2, 5, 9]

    await manager.shutdown()

    assert executor.cancelled is True
    assert manager.active_job_ids == set()


class TestEmailBackgroundTaskExecutor(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.now = datetime(2026, 9, 14, 12, 0, tzinfo=config.TIMEZONE)
        self.clock = MutableClock(self.now)
        self.codec = EmailPayloadCodec(Fernet.generate_key().decode())
        self.sender = MagicMock(spec=SmtpEmailSender)
        self.sender_factory = MagicMock(return_value=self.sender)
        self.settings = FakeSmtpSettingsService()
        self.executor = EmailBackgroundTaskExecutor(
            codec=self.codec,
            renderer=EmailTemplateRenderer(),
            settings_service=self.settings,
            sender_factory=self.sender_factory,
            now_provider=self.clock.now,
            sleep=self.clock.sleep,
        )

    async def create_job(
        self,
        *,
        payload: str | None = None,
        status: BackgroundJobStatus = BackgroundJobStatus.QUEUED,
        retry_count: int = 0,
        max_retry_count: int = 3,
        next_attempt_at: datetime | None = None,
        lease_expires_at: datetime | None = None,
        reference_table: str = "admin",
        reference_id: int = 7,
        user_id: int | None = None,
        job_type: BackgroundJobType = BackgroundJobType.EMAIL,
    ) -> BackgroundJob:
        return await BackgroundJob.create(
            idempotency_key=f"email-background-{uuid4().hex}",
            job_type=job_type,
            status=status,
            user_id=user_id,
            reference_table=reference_table,
            reference_id=reference_id,
            retry_count=retry_count,
            max_retry_count=max_retry_count,
            encrypted_payload=payload,
            next_attempt_at=next_attempt_at,
            lease_expires_at=lease_expires_at,
        )

    def admin_payload(self) -> str:
        return self.codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
                recipient_email="recipient@example.com",
                recipient_name="관리자",
                temporary_password="Temp1234!",
            )
        )

    def signup_payload(self, verification_id: int, expires_at: datetime) -> str:
        return self.codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
                recipient_email="recipient@example.com",
                verification_id=verification_id,
                verification_code="123456",
                expires_in=180,
                expires_at=expires_at,
            )
        )

    def password_reset_payload(self, password: str = "Reset1234!") -> str:
        return self.codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.USER_PASSWORD_RESET,
                recipient_email="recipient@example.com",
                temporary_password=password,
            )
        )

    def intake_payload(self) -> str:
        return self.codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.INTAKE_REPORT,
                recipient_email="recipient@example.com",
                report_id="report-1",
                report_markdown="# report",
                report_birth_date=date(1990, 1, 2),
            )
        )

    async def test_success_claims_sends_and_clears_sensitive_payload(self) -> None:
        job = await self.create_job(payload=self.admin_payload())

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.COMPLETED
        assert job.started_at == self.now
        assert job.completed_at == self.now
        assert job.encrypted_payload is None
        assert job.next_attempt_at is None
        assert job.lease_expires_at is None
        self.sender.send.assert_called_once()

    async def test_retryable_error_waits_and_retries_until_success(self) -> None:
        job = await self.create_job(payload=self.admin_payload())
        self.sender.send.side_effect = [
            EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True),
            None,
        ]

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.COMPLETED
        assert job.retry_count == 1
        assert self.clock.sleeps == [config.EMAIL_RETRY_BASE_SECONDS]
        assert self.sender.send.call_count == 2

    async def test_retryable_error_after_limit_fails_and_clears_payload(self) -> None:
        job = await self.create_job(
            payload=self.admin_payload(),
            retry_count=1,
            max_retry_count=1,
        )
        self.sender.send.side_effect = EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True)

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.retry_count == 2
        assert job.error_code == "EMAIL_CONNECTION_ERROR"
        assert job.encrypted_payload is None

    async def test_future_retry_waits_until_due_then_claims(self) -> None:
        job = await self.create_job(
            payload=self.admin_payload(),
            status=BackgroundJobStatus.RETRY_WAITING,
            next_attempt_at=self.now + timedelta(seconds=30),
        )

        await self.executor.run(job.id)

        assert self.clock.sleeps == [30]
        self.sender.send.assert_called_once()

    async def test_unexpired_processing_lease_is_not_claimed_early(self) -> None:
        sleep_started = asyncio.Event()
        never_release = asyncio.Event()

        async def blocking_sleep(_seconds: float) -> None:
            sleep_started.set()
            await never_release.wait()

        executor = EmailBackgroundTaskExecutor(
            codec=self.codec,
            renderer=EmailTemplateRenderer(),
            settings_service=self.settings,
            sender_factory=self.sender_factory,
            now_provider=self.clock.now,
            sleep=blocking_sleep,
        )
        job = await self.create_job(
            payload=self.admin_payload(),
            status=BackgroundJobStatus.PROCESSING,
            lease_expires_at=self.now + timedelta(seconds=60),
        )

        task = asyncio.create_task(executor.run(job.id))
        await sleep_started.wait()
        self.sender.send.assert_not_called()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_invalid_payload_and_configuration_fail_without_secret_leak(self) -> None:
        invalid = await self.create_job(payload="sensitive-invalid-token")
        await self.executor.run(invalid.id)
        await invalid.refresh_from_db()
        assert invalid.status is BackgroundJobStatus.FAILED
        assert invalid.error_code == "EMAIL_PAYLOAD_INVALID"
        assert "sensitive-invalid-token" not in (invalid.error_message or "")

        configured = await self.create_job(payload=self.admin_payload())
        self.settings.error = RuntimeError("smtp-password-secret")
        await self.executor.run(configured.id)
        await configured.refresh_from_db()
        assert configured.status is BackgroundJobStatus.FAILED
        assert configured.error_code == "EMAIL_CONFIG_INVALID"
        assert "smtp-password-secret" not in (configured.error_message or "")

    async def test_signup_expiry_cancels_without_sending(self) -> None:
        verification = await EmailVerification.create(
            email="recipient@example.com",
            purpose=EmailVerificationPurpose.SIGNUP,
            code_digest="a" * 64,
            expires_at=self.now - timedelta(seconds=1),
        )
        job = await self.create_job(
            payload=self.signup_payload(verification.id, verification.expires_at),
            reference_table="email_verifications",
            reference_id=verification.id,
        )

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.CANCELLED
        assert job.error_code == "EMAIL_VERIFICATION_EXPIRED"
        assert job.encrypted_payload is None
        self.sender.send.assert_not_called()

    async def test_signup_retry_that_reaches_expiry_is_cancelled(self) -> None:
        verification = await EmailVerification.create(
            email="recipient@example.com",
            purpose=EmailVerificationPurpose.SIGNUP,
            code_digest="a" * 64,
            expires_at=self.now + timedelta(seconds=1),
        )
        job = await self.create_job(
            payload=self.signup_payload(verification.id, verification.expires_at),
            reference_table="email_verifications",
            reference_id=verification.id,
        )
        self.sender.send.side_effect = EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True)

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.CANCELLED
        assert job.retry_count == 1
        assert job.error_code == "EMAIL_VERIFICATION_EXPIRED"
        assert self.clock.sleeps == []

    async def test_password_changes_only_after_successful_delivery(self) -> None:
        user = await User.create(
            email="recipient@example.com",
            hashed_password=hash_password("Original123!"),
            name="재설정 사용자",
            status=AccountStatus.ACTIVE,
        )
        job = await self.create_job(
            payload=self.password_reset_payload(),
            reference_table="user",
            reference_id=user.id,
        )

        await self.executor.run(job.id)

        await user.refresh_from_db()
        assert verify_password("Reset1234!", user.hashed_password)

    async def test_invalid_password_and_intake_targets_are_cancelled(self) -> None:
        password_job = await self.create_job(
            payload=self.password_reset_payload(),
            reference_table="user",
            reference_id=9999,
        )
        intake_job = await self.create_job(
            payload=self.intake_payload(),
            reference_table="intake_reports",
            reference_id=9999,
            user_id=None,
        )

        await self.executor.run(password_job.id)
        await self.executor.run(intake_job.id)

        await password_job.refresh_from_db()
        await intake_job.refresh_from_db()
        assert password_job.error_code == "EMAIL_PASSWORD_RESET_TARGET_INVALID"
        assert intake_job.error_code == "EMAIL_INTAKE_REPORT_TARGET_INVALID"
        assert password_job.status is BackgroundJobStatus.CANCELLED
        assert intake_job.status is BackgroundJobStatus.CANCELLED

    async def test_recovery_selects_every_unfinished_email_job(self) -> None:
        queued = await self.create_job(payload=self.admin_payload())
        future_retry = await self.create_job(
            payload=self.admin_payload(),
            status=BackgroundJobStatus.RETRY_WAITING,
            next_attempt_at=self.now + timedelta(minutes=1),
        )
        active_lease = await self.create_job(
            payload=self.admin_payload(),
            status=BackgroundJobStatus.PROCESSING,
            lease_expires_at=self.now + timedelta(minutes=1),
        )
        payloadless = await self.create_job(payload=None)
        await self.create_job(payload=self.admin_payload(), status=BackgroundJobStatus.COMPLETED)
        await self.create_job(payload=self.admin_payload(), job_type=BackgroundJobType.ALARM)

        ids = await self.executor.recoverable_job_ids(self.now)

        assert ids == [queued.id, future_retry.id, active_lease.id, payloadless.id]

    async def test_payloadless_legacy_job_fails_without_sending(self) -> None:
        job = await self.create_job(payload=None)

        await self.executor.run(job.id)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_PAYLOAD_UNAVAILABLE"
        self.sender.send.assert_not_called()
