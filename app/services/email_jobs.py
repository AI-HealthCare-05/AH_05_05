from datetime import datetime
from typing import Protocol
from uuid import uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool
from tortoise.exceptions import IntegrityError

from app.core import config
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType


class EmailPayloadEncoder(Protocol):
    def encrypt(self, payload: EmailJobPayload) -> str: ...


class EmailJobService:
    def __init__(
        self,
        *,
        redis_pool: ArqRedis | None = None,
        codec: EmailPayloadEncoder | None = None,
    ) -> None:
        self.redis_pool = redis_pool
        self.codec = codec

    async def enqueue_admin_temporary_password(
        self,
        *,
        admin_id: int,
        recipient_email: str,
        recipient_name: str,
        temporary_password: str,
    ) -> BackgroundJob:
        job = await BackgroundJob.create(
            idempotency_key=f"email:admin-temporary-password:{admin_id}:{uuid4().hex}",
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.QUEUED,
            reference_table="admin",
            reference_id=admin_id,
            retry_count=0,
            max_retry_count=config.EMAIL_MAX_RETRY_COUNT,
        )

        try:
            codec = self.codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
            encrypted_payload = codec.encrypt(
                EmailJobPayload(
                    template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
                    recipient_email=recipient_email,
                    recipient_name=recipient_name,
                    temporary_password=temporary_password,
                )
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_PAYLOAD_ENCRYPTION_FAILED", exc)
            return job

        pool = self.redis_pool
        owns_pool = pool is None
        try:
            if pool is None:
                pool = await create_pool(
                    RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
                )
            await pool.enqueue_job(
                "send_email",
                job.id,
                encrypted_payload,
                _job_id=job.idempotency_key,
                _queue_name=config.EMAIL_QUEUE_NAME,
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_QUEUE_UNAVAILABLE", exc)
        finally:
            if owns_pool and pool is not None:
                await pool.aclose()
        return job

    async def enqueue_signup_verification(
        self,
        *,
        verification_id: int,
        recipient_email: str,
        verification_code: str,
        expires_in: int,
        expires_at: datetime,
    ) -> BackgroundJob:
        job = await BackgroundJob.create(
            idempotency_key=f"email:signup-verification:{verification_id}:{uuid4().hex}",
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.QUEUED,
            reference_table="email_verifications",
            reference_id=verification_id,
            retry_count=0,
            max_retry_count=config.EMAIL_MAX_RETRY_COUNT,
        )
        try:
            codec = self.codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
            encrypted_payload = codec.encrypt(
                EmailJobPayload(
                    template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
                    recipient_email=recipient_email,
                    verification_id=verification_id,
                    verification_code=verification_code,
                    expires_in=expires_in,
                    expires_at=expires_at,
                )
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_PAYLOAD_ENCRYPTION_FAILED", exc)
            return job

        pool = self.redis_pool
        owns_pool = pool is None
        try:
            if pool is None:
                pool = await create_pool(
                    RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
                )
            await pool.enqueue_job(
                "send_email",
                job.id,
                encrypted_payload,
                _job_id=job.idempotency_key,
                _queue_name=config.EMAIL_QUEUE_NAME,
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_QUEUE_UNAVAILABLE", exc)
        finally:
            if owns_pool and pool is not None:
                await pool.aclose()
        return job

    async def enqueue_user_password_reset(
        self,
        *,
        user_id: int,
        recipient_email: str,
        temporary_password: str,
    ) -> BackgroundJob:
        job = await BackgroundJob.create(
            idempotency_key=f"email:user-password-reset:{user_id}:{uuid4().hex}",
            job_type=BackgroundJobType.EMAIL,
            status=BackgroundJobStatus.QUEUED,
            reference_table="user",
            reference_id=user_id,
            retry_count=0,
            max_retry_count=config.EMAIL_MAX_RETRY_COUNT,
        )
        try:
            codec = self.codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
            encrypted_payload = codec.encrypt(
                EmailJobPayload(
                    template=EmailTemplate.USER_PASSWORD_RESET,
                    recipient_email=recipient_email,
                    temporary_password=temporary_password,
                )
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_PAYLOAD_ENCRYPTION_FAILED", exc)
            return job

        pool = self.redis_pool
        owns_pool = pool is None
        try:
            if pool is None:
                pool = await create_pool(
                    RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
                )
            await pool.enqueue_job(
                "send_email",
                job.id,
                encrypted_payload,
                _job_id=job.idempotency_key,
                _queue_name=config.EMAIL_QUEUE_NAME,
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_QUEUE_UNAVAILABLE", exc)
        finally:
            if owns_pool and pool is not None:
                await pool.aclose()
        return job

    async def enqueue_intake_report(
        self,
        *,
        user_id: int,
        recipient_email: str,
        report_markdown: str,
        report_id: str,
    ) -> BackgroundJob:
        idempotency_key = f"email:intake-report:{user_id}:{report_id}"
        try:
            job = await BackgroundJob.create(
                idempotency_key=idempotency_key,
                job_type=BackgroundJobType.EMAIL,
                status=BackgroundJobStatus.QUEUED,
                user_id=user_id,
                reference_table="intake_reports",
                reference_id=user_id,
                retry_count=0,
                max_retry_count=config.EMAIL_MAX_RETRY_COUNT,
            )
        except IntegrityError:
            existing = await BackgroundJob.get_or_none(idempotency_key=idempotency_key)
            if existing is None:
                raise
            if existing.status is not BackgroundJobStatus.QUEUED:
                return existing
            job = existing

        try:
            codec = self.codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
            encrypted_payload = codec.encrypt(
                EmailJobPayload(
                    template=EmailTemplate.INTAKE_REPORT,
                    recipient_email=recipient_email,
                    report_id=report_id,
                    report_markdown=report_markdown,
                )
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_PAYLOAD_ENCRYPTION_FAILED", exc)
            return job

        pool = self.redis_pool
        owns_pool = pool is None
        try:
            if pool is None:
                pool = await create_pool(
                    RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
                )
            await pool.enqueue_job(
                "send_email",
                job.id,
                encrypted_payload,
                _job_id=job.idempotency_key,
                _queue_name=config.EMAIL_QUEUE_NAME,
            )
        except Exception as exc:
            await self._mark_failed(job, "EMAIL_QUEUE_UNAVAILABLE", exc)
        finally:
            if owns_pool and pool is not None:
                await pool.aclose()
        return job

    @staticmethod
    async def _mark_failed(job: BackgroundJob, error_code: str, error: Exception) -> None:
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.FAILED
        job.completed_at = now
        job.updated_at = now
        job.error_code = error_code
        job.error_message = type(error).__name__
        await job.save(update_fields=["status", "completed_at", "updated_at", "error_code", "error_message"])
