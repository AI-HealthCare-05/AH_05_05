from datetime import date, datetime
from typing import Protocol
from uuid import uuid4

from tortoise.exceptions import IntegrityError

from app.core import config
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType


class EmailPayloadEncoder(Protocol):
    def encrypt(self, payload: EmailJobPayload) -> str: ...


class EmailTaskScheduler(Protocol):
    def schedule(self, job_id: int) -> None: ...


class EmailJobService:
    def __init__(self, *, codec: EmailPayloadEncoder | None = None) -> None:
        self.codec = codec

    async def enqueue_admin_temporary_password(
        self,
        *,
        admin_id: int,
        recipient_email: str,
        recipient_name: str,
        temporary_password: str,
        scheduler: EmailTaskScheduler,
    ) -> BackgroundJob:
        job = await self._create_job(
            idempotency_key=f"email:admin-temporary-password:{admin_id}:{uuid4().hex}",
            reference_table="admin",
            reference_id=admin_id,
        )
        payload = EmailJobPayload(
            template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            temporary_password=temporary_password,
        )
        return await self._persist_and_schedule(job, payload, scheduler)

    async def enqueue_signup_verification(
        self,
        *,
        verification_id: int,
        recipient_email: str,
        verification_code: str,
        expires_in: int,
        expires_at: datetime,
        scheduler: EmailTaskScheduler,
    ) -> BackgroundJob:
        job = await self._create_job(
            idempotency_key=f"email:signup-verification:{verification_id}:{uuid4().hex}",
            reference_table="email_verifications",
            reference_id=verification_id,
        )
        payload = EmailJobPayload(
            template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
            recipient_email=recipient_email,
            verification_id=verification_id,
            verification_code=verification_code,
            expires_in=expires_in,
            expires_at=expires_at,
        )
        return await self._persist_and_schedule(job, payload, scheduler)

    async def enqueue_user_password_reset(
        self,
        *,
        user_id: int,
        recipient_email: str,
        temporary_password: str,
        scheduler: EmailTaskScheduler,
    ) -> BackgroundJob:
        job = await self._create_job(
            idempotency_key=f"email:user-password-reset:{user_id}:{uuid4().hex}",
            reference_table="user",
            reference_id=user_id,
        )
        payload = EmailJobPayload(
            template=EmailTemplate.USER_PASSWORD_RESET,
            recipient_email=recipient_email,
            temporary_password=temporary_password,
        )
        return await self._persist_and_schedule(job, payload, scheduler)

    async def enqueue_intake_report(
        self,
        *,
        user_id: int,
        recipient_email: str,
        report_markdown: str,
        report_id: str,
        report_birth_date: date,
        scheduler: EmailTaskScheduler,
        recipient_name: str | None = None,
        report_html: str | None = None,
    ) -> BackgroundJob:
        idempotency_key = f"email:intake-report:{user_id}:{report_id}"
        try:
            job = await self._create_job(
                idempotency_key=idempotency_key,
                reference_table="intake_reports",
                reference_id=user_id,
                user_id=user_id,
            )
        except IntegrityError:
            existing = await BackgroundJob.get_or_none(idempotency_key=idempotency_key)
            if existing is None:
                raise
            if existing.status is not BackgroundJobStatus.QUEUED:
                return existing
            job = existing

        payload = EmailJobPayload(
            template=EmailTemplate.INTAKE_REPORT,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            report_birth_date=report_birth_date,
            report_id=report_id,
            report_markdown=report_markdown,
            report_html=report_html,
        )
        return await self._persist_and_schedule(job, payload, scheduler)

    @staticmethod
    async def _create_job(
        *,
        idempotency_key: str,
        reference_table: str,
        reference_id: int,
        user_id: int | None = None,
    ) -> BackgroundJob:
        return await BackgroundJob.create(
            idempotency_key=idempotency_key,
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.QUEUED,
            user_id=user_id,
            reference_table=reference_table,
            reference_id=reference_id,
            retry_count=0,
            max_retry_count=config.EMAIL_MAX_RETRY_COUNT,
        )

    async def _persist_and_schedule(
        self,
        job: BackgroundJob,
        payload: EmailJobPayload,
        scheduler: EmailTaskScheduler,
    ) -> BackgroundJob:
        try:
            codec = self.codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
            encrypted_payload = codec.encrypt(payload)
            now = datetime.now(config.TIMEZONE)
            job.encrypted_payload = encrypted_payload
            job.next_attempt_at = now
            job.updated_at = now
            await job.save(update_fields=["encrypted_payload", "next_attempt_at", "updated_at"])
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_PAYLOAD_ENCRYPTION_FAILED", exc)
            return job

        try:
            scheduler.schedule(job.id)
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_TASK_SCHEDULING_FAILED", exc)
        return job

    @staticmethod
    async def _mark_failed(job: BackgroundJob, error_code: str, error: Exception) -> None:
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.FAILED
        job.completed_at = now
        job.updated_at = now
        job.error_code = error_code
        job.error_message = type(error).__name__
        job.encrypted_payload = None
        job.next_attempt_at = None
        job.lease_expires_at = None
        await job.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
                "error_code",
                "error_message",
                "encrypted_payload",
                "next_attempt_at",
                "lease_expires_at",
            ]
        )
