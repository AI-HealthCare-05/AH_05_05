from datetime import datetime
from typing import Protocol
from uuid import uuid4

from arq.connections import ArqRedis, RedisSettings, create_pool

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

    @staticmethod
    async def _mark_failed(job: BackgroundJob, error_code: str, error: Exception) -> None:
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.FAILED
        job.completed_at = now
        job.updated_at = now
        job.error_code = error_code
        job.error_message = type(error).__name__
        await job.save(update_fields=["status", "completed_at", "updated_at", "error_code", "error_message"])
