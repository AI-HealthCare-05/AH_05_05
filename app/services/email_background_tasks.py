from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Protocol

from tortoise.expressions import Q

from app.core import config
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate, InvalidEmailPayloadError
from app.core.email.renderer import EmailTemplateRenderer
from app.core.email.smtp_sender import EmailDeliveryError, SmtpEmailSender
from app.core.utils.security import hash_password
from app.models.background_jobs import BackgroundJob
from app.models.email_verifications import EmailVerification
from app.models.enums import (
    AccountStatus,
    BackgroundJobStatus,
    BackgroundJobType,
    EmailVerificationPurpose,
)
from app.models.users import User
from app.services.admin_settings import SmtpRuntimeSettings, SmtpSettingsService

EMAIL_TASK_LEASE = timedelta(seconds=60)
_UNFINISHED_STATUSES = (
    BackgroundJobStatus.QUEUED,
    BackgroundJobStatus.PROCESSING,
    BackgroundJobStatus.RETRY_WAITING,
)


class EmailPayloadDecoder(Protocol):
    def decrypt(self, token: str) -> EmailJobPayload: ...


class RuntimeSmtpSettingsProvider(Protocol):
    async def get_runtime_settings(self) -> SmtpRuntimeSettings: ...


class EmailTaskExecutor(Protocol):
    async def recoverable_job_ids(self, now: datetime) -> list[int]: ...

    async def run(self, job_id: int) -> None: ...


class EmailBackgroundTaskManager:
    def __init__(
        self,
        executor: EmailTaskExecutor,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.executor = executor
        self.now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))
        self._lock = asyncio.Lock()
        self._tasks_by_job_id: dict[int, asyncio.Task[None]] = {}

    @property
    def active_job_ids(self) -> set[int]:
        return {job_id for job_id, task in self._tasks_by_job_id.items() if not task.done()}

    async def start(self, job_id: int) -> None:
        async with self._lock:
            current = self._tasks_by_job_id.get(job_id)
            if current is not None and not current.done():
                return
            self._tasks_by_job_id[job_id] = asyncio.create_task(self._run(job_id))

    async def recover(self) -> None:
        for job_id in await self.executor.recoverable_job_ids(self.now_provider()):
            await self.start(job_id)

    async def wait_until_idle(self) -> None:
        while True:
            async with self._lock:
                tasks = [task for task in self._tasks_by_job_id.values() if not task.done()]
            if not tasks:
                return
            await asyncio.gather(*tasks)

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks_by_job_id.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._lock:
            self._tasks_by_job_id.clear()

    async def _run(self, job_id: int) -> None:
        current_task = asyncio.current_task()
        try:
            await self.executor.run(job_id)
        finally:
            async with self._lock:
                if self._tasks_by_job_id.get(job_id) is current_task:
                    self._tasks_by_job_id.pop(job_id, None)


def build_email_background_task_manager() -> EmailBackgroundTaskManager:
    return EmailBackgroundTaskManager(EmailBackgroundTaskExecutor())


class EmailBackgroundTaskExecutor:
    def __init__(
        self,
        *,
        codec: EmailPayloadDecoder | None = None,
        renderer: EmailTemplateRenderer | None = None,
        settings_service: RuntimeSmtpSettingsProvider | None = None,
        sender_factory: Callable[..., SmtpEmailSender] = SmtpEmailSender,
        now_provider: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.codec = codec or EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
        self.renderer = renderer or EmailTemplateRenderer()
        self.settings_service = settings_service or SmtpSettingsService()
        self.sender_factory = sender_factory
        self.now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))
        self.sleep = sleep

    async def recoverable_job_ids(self, now: datetime) -> list[int]:
        del now
        rows = (
            await BackgroundJob.filter(
                job_type=BackgroundJobType.EMAIL,
                status__in=_UNFINISHED_STATUSES,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        return list(rows)

    async def run(self, job_id: int) -> None:
        while True:
            job = await BackgroundJob.get_or_none(id=job_id, job_type=BackgroundJobType.EMAIL)
            if job is None or job.status not in _UNFINISHED_STATUSES:
                return
            if not job.encrypted_payload:
                await self._fail_job(job, "EMAIL_PAYLOAD_UNAVAILABLE")
                return

            wait_until = self._wait_until(job)
            now = self.now_provider()
            if wait_until is not None and wait_until > now:
                await self.sleep((wait_until - now).total_seconds())
                continue

            claimed = await self._claim(job.id, now)
            if not claimed:
                return
            job = await BackgroundJob.get(id=job.id)
            should_retry = await self._deliver(job)
            if not should_retry:
                return

    def _wait_until(self, job: BackgroundJob) -> datetime | None:
        if job.status is BackgroundJobStatus.RETRY_WAITING:
            return job.next_attempt_at
        if job.status is BackgroundJobStatus.PROCESSING:
            return job.lease_expires_at
        return None

    async def _claim(self, job_id: int, now: datetime) -> bool:
        claimable = Q(status=BackgroundJobStatus.QUEUED)
        claimable |= Q(status=BackgroundJobStatus.RETRY_WAITING) & (
            Q(next_attempt_at__lte=now) | Q(next_attempt_at=None)
        )
        claimable |= Q(status=BackgroundJobStatus.PROCESSING) & (
            Q(lease_expires_at__lte=now) | Q(lease_expires_at=None)
        )
        updated = await BackgroundJob.filter(Q(id=job_id, job_type=BackgroundJobType.EMAIL) & claimable).update(
            status=BackgroundJobStatus.PROCESSING,
            started_at=now,
            updated_at=now,
            next_attempt_at=None,
            lease_expires_at=now + EMAIL_TASK_LEASE,
        )
        return updated == 1

    async def _deliver(self, job: BackgroundJob) -> bool:
        try:
            payload = self.codec.decrypt(job.encrypted_payload or "")
            cancellation_code = await self._sendability_cancellation_code(payload, job)
            if cancellation_code is not None:
                await self._cancel_job(job, cancellation_code)
                return False
            message = self.renderer.render(payload)
        except (InvalidEmailPayloadError, ValueError):
            await self._fail_job(job, "EMAIL_PAYLOAD_INVALID")
            return False

        try:
            settings = await self.settings_service.get_runtime_settings()
            sender = self.sender_factory(
                host=settings.host,
                port=settings.port,
                username=settings.username,
                password=settings.password,
                from_address=settings.from_email,
            )
        except (RuntimeError, ValueError):
            await self._fail_job(job, "EMAIL_CONFIG_INVALID")
            return False
        except Exception:
            return await self._retry_or_fail(
                job,
                EmailDeliveryError("EMAIL_CONFIG_UNAVAILABLE", retryable=True),
                expires_at=payload.expires_at,
            )

        try:
            await asyncio.to_thread(sender.send, message)
        except EmailDeliveryError as error:
            if error.retryable:
                return await self._retry_or_fail(job, error, expires_at=payload.expires_at)
            await self._fail_job(job, error.code)
            return False

        if not await self._apply_post_delivery_effect(payload, job):
            await self._fail_job(job, "EMAIL_PASSWORD_UPDATE_FAILED")
            return False

        await self._complete_job(job)
        return False

    async def _complete_job(self, job: BackgroundJob) -> None:
        now = self.now_provider()
        job.status = BackgroundJobStatus.COMPLETED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = self._duration_ms(job.started_at, now)
        job.error_code = None
        job.error_message = None
        self._clear_recovery_fields(job)
        await job.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
                "duration_ms",
                "error_code",
                "error_message",
                "encrypted_payload",
                "next_attempt_at",
                "lease_expires_at",
            ]
        )

    async def _retry_or_fail(
        self,
        job: BackgroundJob,
        error: EmailDeliveryError,
        *,
        expires_at: datetime | None,
    ) -> bool:
        retry_count = job.retry_count + 1
        if retry_count > job.max_retry_count:
            await self._fail_job(job, error.code, retry_count=retry_count)
            return False

        now = self.now_provider()
        delay = config.EMAIL_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
        next_attempt_at = now + timedelta(seconds=delay)
        job.retry_count = retry_count
        if expires_at is not None and next_attempt_at >= expires_at:
            await self._cancel_job(job, "EMAIL_VERIFICATION_EXPIRED", retry_count=retry_count)
            return False

        job.status = BackgroundJobStatus.RETRY_WAITING
        job.updated_at = now
        job.next_attempt_at = next_attempt_at
        job.lease_expires_at = None
        job.error_code = error.code
        job.error_message = type(error).__name__
        await job.save(
            update_fields=[
                "status",
                "retry_count",
                "updated_at",
                "next_attempt_at",
                "lease_expires_at",
                "error_code",
                "error_message",
            ]
        )
        return True

    async def _fail_job(
        self,
        job: BackgroundJob,
        error_code: str,
        *,
        retry_count: int | None = None,
    ) -> None:
        now = self.now_provider()
        job.status = BackgroundJobStatus.FAILED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = self._duration_ms(job.started_at, now)
        job.error_code = error_code
        job.error_message = error_code
        if retry_count is not None:
            job.retry_count = retry_count
        self._clear_recovery_fields(job)
        update_fields = [
            "status",
            "completed_at",
            "updated_at",
            "duration_ms",
            "error_code",
            "error_message",
            "encrypted_payload",
            "next_attempt_at",
            "lease_expires_at",
        ]
        if retry_count is not None:
            update_fields.append("retry_count")
        await job.save(update_fields=update_fields)

    async def _cancel_job(
        self,
        job: BackgroundJob,
        error_code: str,
        *,
        retry_count: int | None = None,
    ) -> None:
        now = self.now_provider()
        job.status = BackgroundJobStatus.CANCELLED
        job.completed_at = now
        job.updated_at = now
        job.duration_ms = self._duration_ms(job.started_at, now)
        job.error_code = error_code
        job.error_message = error_code
        if retry_count is not None:
            job.retry_count = retry_count
        self._clear_recovery_fields(job)
        update_fields = [
            "status",
            "completed_at",
            "updated_at",
            "duration_ms",
            "error_code",
            "error_message",
            "encrypted_payload",
            "next_attempt_at",
            "lease_expires_at",
        ]
        if retry_count is not None:
            update_fields.append("retry_count")
        await job.save(update_fields=update_fields)

    @staticmethod
    def _clear_recovery_fields(job: BackgroundJob) -> None:
        job.encrypted_payload = None
        job.next_attempt_at = None
        job.lease_expires_at = None

    async def _sendability_cancellation_code(
        self,
        payload: EmailJobPayload,
        job: BackgroundJob,
    ) -> str | None:
        if payload.template is EmailTemplate.SIGNUP_VERIFICATION_CODE:
            sendable = (
                payload.verification_id is not None
                and await EmailVerification.filter(
                    id=payload.verification_id,
                    expires_at__gt=self.now_provider(),
                    consumed_at=None,
                ).exists()
            )
            if not sendable:
                return "EMAIL_VERIFICATION_EXPIRED"
        elif payload.template is EmailTemplate.USER_PASSWORD_RESET:
            if job.reference_table != "user" or job.reference_id is None:
                return "EMAIL_PASSWORD_RESET_TARGET_INVALID"
            if not await User.filter(
                id=job.reference_id,
                email=str(payload.recipient_email),
                status=AccountStatus.ACTIVE,
            ).exists():
                return "EMAIL_PASSWORD_RESET_TARGET_INVALID"
        elif payload.template is EmailTemplate.INTAKE_REPORT:
            if not await self._is_intake_report_sendable(job, str(payload.recipient_email)):
                return "EMAIL_INTAKE_REPORT_TARGET_INVALID"
        return None

    @staticmethod
    async def _is_intake_report_sendable(job: BackgroundJob, recipient_email: str) -> bool:
        if job.reference_table != "intake_reports" or job.reference_id is None or job.user_id != job.reference_id:
            return False
        user = await User.get_or_none(
            id=job.reference_id,
            email=recipient_email.casefold(),
            status=AccountStatus.ACTIVE,
        )
        if user is None:
            return False
        return await EmailVerification.filter(
            email=user.email.casefold(),
            purpose=EmailVerificationPurpose.SIGNUP,
            verified_at__not_isnull=True,
        ).exists()

    @staticmethod
    async def _apply_post_delivery_effect(payload: EmailJobPayload, job: BackgroundJob) -> bool:
        if payload.template is not EmailTemplate.USER_PASSWORD_RESET:
            return True
        updated = await User.filter(
            id=job.reference_id,
            email=str(payload.recipient_email),
            status=AccountStatus.ACTIVE,
        ).update(hashed_password=hash_password(payload.temporary_password or ""))
        return updated == 1

    @staticmethod
    def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
        if started_at is None:
            return None
        return max(0, int((completed_at - started_at).total_seconds() * 1000))
