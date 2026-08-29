import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from arq import Retry
from cryptography.fernet import Fernet
from tortoise.contrib.test import TestCase

from app.core import config
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate
from app.core.email.renderer import EmailTemplateRenderer
from app.core.email.smtp_sender import EmailDeliveryError, SmtpEmailSender
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.services.admin_settings import SmtpRuntimeSettings, SmtpSettingsService
from app.workers import email_worker as worker


def test_admin_settings_import_does_not_require_ai_worker() -> None:
    project_root = Path(__file__).resolve().parents[3]
    script = """
import builtins

real_import = builtins.__import__


def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "ai_worker" or name.startswith("ai_worker."):
        raise ModuleNotFoundError("blocked ai_worker")
    return real_import(name, globals, locals, fromlist, level)


builtins.__import__ = guarded_import
from app.services.admin_settings import SmtpSettingsService

assert SmtpSettingsService.__name__ == "SmtpSettingsService"
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


class FakeSmtpSettingsService:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    async def get_runtime_settings(self) -> SmtpRuntimeSettings:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return SmtpRuntimeSettings(
            host="smtp.db.example.com",
            port=2525,
            username="db-user@example.com",
            password="db-password",
            from_email="from@example.com",
        )


class TestEmailWorker(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.codec = EmailPayloadCodec(Fernet.generate_key().decode())
        self.sender = MagicMock(spec=SmtpEmailSender)
        self.settings_service = FakeSmtpSettingsService()
        self.sender_factory = MagicMock(return_value=self.sender)
        self.context = {
            "codec": self.codec,
            "renderer": EmailTemplateRenderer(),
            "settings_service": self.settings_service,
            "sender_factory": self.sender_factory,
        }

    async def create_job(
        self,
        *,
        status: BackgroundJobStatus = BackgroundJobStatus.QUEUED,
        retry_count: int = 0,
        max_retry_count: int = 3,
    ) -> BackgroundJob:
        return await BackgroundJob.create(
            idempotency_key=f"email-worker-{status}-{retry_count}-{max_retry_count}",
            job_type=BackgroundJobType.EMAIL,
            status=status,
            reference_table="admin",
            reference_id=7,
            retry_count=retry_count,
            max_retry_count=max_retry_count,
        )

    def encrypted_payload(self, password: str = "Temp1234!") -> str:
        return self.codec.encrypt(
            EmailJobPayload(
                template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
                recipient_email="recipient@example.com",
                recipient_name="홍길동",
                temporary_password=password,
            )
        )

    async def test_successful_delivery_completes_claimed_job(self) -> None:
        job = await self.create_job()

        await worker.send_email(self.context, job.id, self.encrypted_payload())

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.COMPLETED
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.duration_ms is not None
        assert job.error_code is None
        self.sender.send.assert_called_once()
        assert self.settings_service.calls == 1
        self.sender_factory.assert_called_once_with(
            host="smtp.db.example.com",
            port=2525,
            username="db-user@example.com",
            password="db-password",
            from_address="from@example.com",
        )

    async def test_retryable_failure_waits_and_raises_arq_retry(self) -> None:
        job = await self.create_job(max_retry_count=3)
        self.sender.send.side_effect = EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True)

        with pytest.raises(Retry):
            await worker.send_email(self.context, job.id, self.encrypted_payload())

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.RETRY_WAITING
        assert job.retry_count == 1
        assert job.error_code == "EMAIL_CONNECTION_ERROR"
        assert job.completed_at is None

    async def test_retryable_failure_after_limit_is_failed(self) -> None:
        job = await self.create_job(retry_count=1, max_retry_count=1)
        self.sender.send.side_effect = EmailDeliveryError("EMAIL_CONNECTION_ERROR", retryable=True)

        await worker.send_email(self.context, job.id, self.encrypted_payload())

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.retry_count == 2
        assert job.completed_at is not None

    async def test_permanent_failure_is_not_retried(self) -> None:
        job = await self.create_job()
        self.sender.send.side_effect = EmailDeliveryError("EMAIL_AUTH_FAILED", retryable=False)

        await worker.send_email(self.context, job.id, self.encrypted_payload())

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.retry_count == 0
        assert job.error_code == "EMAIL_AUTH_FAILED"

    async def test_invalid_runtime_settings_fail_job_without_sending(self) -> None:
        job = await self.create_job()
        self.settings_service.error = RuntimeError("configuration secret")

        await worker.send_email(self.context, job.id, self.encrypted_payload())

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_CONFIG_INVALID"
        assert "configuration secret" not in (job.error_message or "")
        self.sender.send.assert_not_called()

    async def test_invalid_payload_is_failed_without_leaking_token(self) -> None:
        job = await self.create_job()
        token = "sensitive-invalid-token"

        await worker.send_email(self.context, job.id, token)

        await job.refresh_from_db()
        assert job.status is BackgroundJobStatus.FAILED
        assert job.error_code == "EMAIL_PAYLOAD_INVALID"
        assert token not in (job.error_message or "")
        self.sender.send.assert_not_called()

    async def test_job_that_cannot_be_claimed_is_not_sent(self) -> None:
        job = await self.create_job(status=BackgroundJobStatus.COMPLETED)

        await worker.send_email(self.context, job.id, self.encrypted_payload())

        self.sender.send.assert_not_called()


@pytest.mark.asyncio
async def test_startup_and_shutdown_manage_worker_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    init = AsyncMock()
    close_connections = AsyncMock()
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(worker.Tortoise, "_inited", False)
    monkeypatch.setattr(worker.Tortoise, "init", init)
    monkeypatch.setattr(worker.Tortoise, "close_connections", close_connections)
    monkeypatch.setattr(worker.config, "EMAIL_PAYLOAD_ENCRYPTION_KEY", key)

    ctx: dict[str, object] = {}
    await worker.startup(ctx)

    init.assert_awaited_once_with(config=worker.TORTOISE_ORM)
    assert isinstance(ctx["codec"], EmailPayloadCodec)
    assert isinstance(ctx["renderer"], EmailTemplateRenderer)
    assert isinstance(ctx["settings_service"], SmtpSettingsService)
    assert ctx["sender_factory"] is SmtpEmailSender

    await worker.shutdown(ctx)
    close_connections.assert_awaited_once_with()


def test_worker_settings_use_dedicated_queue_and_retry_limit() -> None:
    assert worker.WorkerSettings.functions == [worker.send_email]
    assert worker.WorkerSettings.queue_name == config.EMAIL_QUEUE_NAME
    assert worker.WorkerSettings.max_tries == config.EMAIL_MAX_RETRY_COUNT + 1
