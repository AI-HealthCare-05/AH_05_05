from datetime import UTC, date, datetime

from cryptography.fernet import Fernet
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.email.payload import EmailPayloadCodec, EmailPayloadConfigurationError, EmailTemplate
from app.models.enums import AccountStatus, BackgroundJobStatus, BackgroundJobType
from app.models.users import User
from app.services.email_jobs import EmailJobService


class FailingCodec:
    def encrypt(self, _payload: object) -> str:
        raise EmailPayloadConfigurationError("secret-value-must-not-leak")


class RecordingScheduler:
    def __init__(self) -> None:
        self.job_ids: list[int] = []

    def schedule(self, job_id: int) -> None:
        self.job_ids.append(job_id)


class FailingScheduler:
    def schedule(self, _job_id: int) -> None:
        raise RuntimeError("scheduler contains Temp1234!")


class TestEmailJobService(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.scheduler = RecordingScheduler()
        self.codec = EmailPayloadCodec(Fernet.generate_key().decode())
        self.service = EmailJobService(codec=self.codec)

    async def test_creates_email_job_and_enqueues_only_encrypted_payload(self) -> None:
        job = await self.service.enqueue_admin_temporary_password(
            admin_id=17,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
            scheduler=self.scheduler,
        )

        assert job.job_type is BackgroundJobType.EMAIL
        assert job.status is BackgroundJobStatus.QUEUED
        assert job.reference_table == "admin"
        assert job.reference_id == 17
        assert job.max_retry_count == config.EMAIL_MAX_RETRY_COUNT
        await job.refresh_from_db()
        encrypted_payload = job.encrypted_payload or ""
        assert "recipient@example.com" not in encrypted_payload
        assert "홍길동" not in encrypted_payload
        assert "Temp1234!" not in encrypted_payload
        assert self.codec.decrypt(encrypted_payload).recipient_name == "홍길동"
        assert job.next_attempt_at is not None
        assert self.scheduler.job_ids == [job.id]

    async def test_marks_job_failed_when_task_scheduling_fails(self) -> None:
        job = await self.service.enqueue_admin_temporary_password(
            admin_id=18,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
            scheduler=FailingScheduler(),
        )

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_TASK_SCHEDULING_FAILED"
        assert job.completed_at is not None
        assert "Temp1234!" not in (job.error_message or "")
        assert job.encrypted_payload is None

    async def test_marks_job_failed_when_payload_encryption_fails(self) -> None:
        service = EmailJobService(codec=FailingCodec())  # type: ignore[arg-type]

        job = await service.enqueue_admin_temporary_password(
            admin_id=19,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
            scheduler=self.scheduler,
        )

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_PAYLOAD_ENCRYPTION_FAILED"
        assert "secret-value-must-not-leak" not in (job.error_message or "")
        assert self.scheduler.job_ids == []

    async def test_signup_verification_job_references_verification_and_encrypts_code(self) -> None:
        expires_at = datetime(2026, 9, 7, 3, 1, tzinfo=UTC)

        job = await self.service.enqueue_signup_verification(
            verification_id=27,
            recipient_email="recipient@example.com",
            verification_code="012345",
            expires_in=60,
            expires_at=expires_at,
            scheduler=self.scheduler,
        )

        assert job.job_type is BackgroundJobType.EMAIL
        assert job.reference_table == "email_verifications"
        assert job.reference_id == 27
        assert job.idempotency_key.startswith("email:signup-verification:27:")
        await job.refresh_from_db()
        encrypted_payload = job.encrypted_payload or ""
        assert "recipient@example.com" not in encrypted_payload
        assert "012345" not in encrypted_payload
        payload = self.codec.decrypt(encrypted_payload)
        assert payload.template is EmailTemplate.SIGNUP_VERIFICATION_CODE
        assert payload.verification_id == 27
        assert payload.verification_code == "012345"
        assert payload.expires_in == 60
        assert payload.expires_at == expires_at
        assert self.scheduler.job_ids == [job.id]

    async def test_user_password_reset_job_references_user_and_encrypts_password(self) -> None:
        job = await self.service.enqueue_user_password_reset(
            user_id=31,
            recipient_email="recipient@example.com",
            temporary_password="Temp1234!",
            scheduler=self.scheduler,
        )

        assert job.job_type is BackgroundJobType.EMAIL
        assert job.reference_table == "user"
        assert job.reference_id == 31
        assert job.idempotency_key.startswith("email:user-password-reset:31:")
        await job.refresh_from_db()
        encrypted_payload = job.encrypted_payload or ""
        assert "Temp1234!" not in encrypted_payload
        payload = self.codec.decrypt(encrypted_payload)
        assert payload.template is EmailTemplate.USER_PASSWORD_RESET
        assert payload.temporary_password == "Temp1234!"

    async def test_intake_report_job_requeues_existing_queued_job_with_same_encrypted_report(self) -> None:
        user = await User.create(
            id=31,
            email="recipient@example.com",
            hashed_password="hashed-password",
            name="보고서 사용자",
            status=AccountStatus.ACTIVE,
        )
        first = await self.service.enqueue_intake_report(
            user_id=user.id,
            recipient_email="recipient@example.com",
            report_id="report-20260911-abc123",
            report_birth_date=date(1990, 1, 2),
            recipient_name=user.name,
            report_markdown="# 복용약 보고서\n\n아주 긴 제품명",
            scheduler=self.scheduler,
        )
        second = await self.service.enqueue_intake_report(
            user_id=user.id,
            recipient_email="recipient@example.com",
            report_id="report-20260911-abc123",
            report_birth_date=date(1990, 1, 2),
            recipient_name=user.name,
            report_markdown="# 복용약 보고서\n\n아주 긴 제품명",
            scheduler=self.scheduler,
        )

        assert first.id == second.id
        assert first.reference_table == "intake_reports"
        assert first.reference_id == 31
        assert first.user_id == 31
        assert first.idempotency_key == "email:intake-report:31:report-20260911-abc123"
        await second.refresh_from_db()
        assert self.scheduler.job_ids == [first.id, second.id]
        encrypted_payload = second.encrypted_payload or ""
        assert "복용약 보고서" not in encrypted_payload
        payload = self.codec.decrypt(encrypted_payload)
        assert payload.template is EmailTemplate.INTAKE_REPORT
        assert payload.report_id == "report-20260911-abc123"
        assert payload.report_birth_date == date(1990, 1, 2)
        assert payload.recipient_name == user.name
