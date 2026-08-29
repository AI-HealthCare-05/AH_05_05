from unittest.mock import AsyncMock

from cryptography.fernet import Fernet
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.email.payload import EmailPayloadCodec, EmailPayloadConfigurationError
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.services.email_jobs import EmailJobService


class FailingCodec:
    def encrypt(self, _payload: object) -> str:
        raise EmailPayloadConfigurationError("secret-value-must-not-leak")


class TestEmailJobService(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.redis_pool = AsyncMock()
        self.redis_pool.enqueue_job.return_value = object()
        self.codec = EmailPayloadCodec(Fernet.generate_key().decode())
        self.service = EmailJobService(redis_pool=self.redis_pool, codec=self.codec)

    async def test_creates_email_job_and_enqueues_only_encrypted_payload(self) -> None:
        job = await self.service.enqueue_admin_temporary_password(
            admin_id=17,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
        )

        assert job.job_type is BackgroundJobType.EMAIL
        assert job.status is BackgroundJobStatus.QUEUED
        assert job.reference_table == "admin"
        assert job.reference_id == 17
        assert job.max_retry_count == config.EMAIL_MAX_RETRY_COUNT
        call = self.redis_pool.enqueue_job.await_args
        assert call.args[:2] == ("send_email", job.id)
        encrypted_payload = call.args[2]
        assert "recipient@example.com" not in encrypted_payload
        assert "홍길동" not in encrypted_payload
        assert "Temp1234!" not in encrypted_payload
        assert self.codec.decrypt(encrypted_payload).recipient_name == "홍길동"
        assert call.kwargs == {
            "_job_id": job.idempotency_key,
            "_queue_name": config.EMAIL_QUEUE_NAME,
        }
        self.redis_pool.aclose.assert_not_awaited()

    async def test_marks_job_failed_when_redis_enqueue_fails(self) -> None:
        self.redis_pool.enqueue_job.side_effect = ConnectionError("redis contains Temp1234!")

        job = await self.service.enqueue_admin_temporary_password(
            admin_id=18,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
        )

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_QUEUE_UNAVAILABLE"
        assert job.completed_at is not None
        assert "Temp1234!" not in (job.error_message or "")

    async def test_marks_job_failed_when_payload_encryption_fails(self) -> None:
        service = EmailJobService(redis_pool=self.redis_pool, codec=FailingCodec())  # type: ignore[arg-type]

        job = await service.enqueue_admin_temporary_password(
            admin_id=19,
            recipient_email="recipient@example.com",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
        )

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_PAYLOAD_ENCRYPTION_FAILED"
        assert "secret-value-must-not-leak" not in (job.error_message or "")
        self.redis_pool.enqueue_job.assert_not_awaited()
