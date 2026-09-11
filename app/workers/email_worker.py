import asyncio
from datetime import datetime, timedelta
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_ORM
from app.core.email.payload import EmailJobPayload, EmailPayloadCodec, EmailTemplate, InvalidEmailPayloadError
from app.core.email.renderer import EmailTemplateRenderer
from app.core.email.smtp_sender import EmailDeliveryError, SmtpEmailSender
from app.core.utils.security import hash_password
from app.models.background_jobs import BackgroundJob
from app.models.email_verifications import EmailVerification
from app.models.enums import AccountStatus, BackgroundJobStatus, EmailVerificationPurpose
from app.models.users import User
from app.repositories.background_job_repository import BackgroundJobRepository
from app.services.admin_settings import SmtpSettingsService


async def startup(ctx: dict[str, Any]) -> None:
    if not Tortoise._inited:  # noqa: SLF001
        await Tortoise.init(config=TORTOISE_ORM)
    ctx["codec"] = EmailPayloadCodec(config.EMAIL_PAYLOAD_ENCRYPTION_KEY)
    ctx["renderer"] = EmailTemplateRenderer()
    ctx["settings_service"] = SmtpSettingsService()
    ctx["sender_factory"] = SmtpEmailSender


async def shutdown(_ctx: dict[str, Any]) -> None:
    await Tortoise.close_connections()


async def send_email(ctx: dict[str, Any], job_id: int, encrypted_payload: str) -> None:
    started_at = datetime.now(config.TIMEZONE)
    if not await BackgroundJobRepository().claim(job_id, started_at):
        return
    job = await BackgroundJob.get(id=job_id)

    try:
        payload = ctx["codec"].decrypt(encrypted_payload)
        cancellation_code = await _sendability_cancellation_code(payload, job)
        if cancellation_code is not None:
            await _cancel_job(job, cancellation_code)
            return
        message = ctx["renderer"].render(payload)
    except (InvalidEmailPayloadError, ValueError):
        await _fail_job(job, "EMAIL_PAYLOAD_INVALID")
        return

    try:
        settings = await ctx["settings_service"].get_runtime_settings()
        sender = ctx["sender_factory"](
            host=settings.host,
            port=settings.port,
            username=settings.username,
            password=settings.password,
            from_address=settings.from_email,
        )
    except (RuntimeError, ValueError):
        await _fail_job(job, "EMAIL_CONFIG_INVALID")
        return
    except Exception:
        await _retry_or_fail(
            job,
            EmailDeliveryError("EMAIL_CONFIG_UNAVAILABLE", retryable=True),
            expires_at=payload.expires_at,
        )
        return

    try:
        await asyncio.to_thread(sender.send, message)
    except EmailDeliveryError as error:
        if error.retryable:
            await _retry_or_fail(job, error, expires_at=payload.expires_at)
            return
        await _fail_job(job, error.code)
        return

    if not await _apply_post_delivery_effect(payload, job):
        await _fail_job(job, "EMAIL_PASSWORD_UPDATE_FAILED")
        return

    await _complete_job(job)


async def _complete_job(job: BackgroundJob) -> None:
    now = datetime.now(config.TIMEZONE)
    job.status = BackgroundJobStatus.COMPLETED
    job.completed_at = now
    job.updated_at = now
    job.duration_ms = _duration_ms(job.started_at, now)
    job.error_code = None
    job.error_message = None
    await job.save(update_fields=["status", "completed_at", "updated_at", "duration_ms", "error_code", "error_message"])


async def _retry_or_fail(
    job: BackgroundJob,
    error: EmailDeliveryError,
    *,
    expires_at: datetime | None = None,
) -> None:
    retry_count = job.retry_count + 1
    if retry_count <= job.max_retry_count:
        now = datetime.now(config.TIMEZONE)
        job.status = BackgroundJobStatus.RETRY_WAITING
        job.retry_count = retry_count
        job.updated_at = now
        job.error_code = error.code
        job.error_message = type(error).__name__
        await job.save(update_fields=["status", "retry_count", "updated_at", "error_code", "error_message"])
        delay = config.EMAIL_RETRY_BASE_SECONDS * (2 ** (retry_count - 1))
        if expires_at is not None and now + timedelta(seconds=delay) >= expires_at:
            await _cancel_job(job, "EMAIL_VERIFICATION_EXPIRED")
            return
        raise Retry(defer=timedelta(seconds=delay))
    await _fail_job(job, error.code, retry_count=retry_count)


async def _fail_job(job: BackgroundJob, error_code: str, *, retry_count: int | None = None) -> None:
    now = datetime.now(config.TIMEZONE)
    job.status = BackgroundJobStatus.FAILED
    job.completed_at = now
    job.updated_at = now
    job.duration_ms = _duration_ms(job.started_at, now)
    job.error_code = error_code
    job.error_message = error_code
    update_fields = ["status", "completed_at", "updated_at", "duration_ms", "error_code", "error_message"]
    if retry_count is not None:
        job.retry_count = retry_count
        update_fields.append("retry_count")
    await job.save(update_fields=update_fields)


async def _cancel_job(job: BackgroundJob, error_code: str) -> None:
    now = datetime.now(config.TIMEZONE)
    job.status = BackgroundJobStatus.CANCELLED
    job.completed_at = now
    job.updated_at = now
    job.duration_ms = _duration_ms(job.started_at, now)
    job.error_code = error_code
    job.error_message = error_code
    await job.save(update_fields=["status", "completed_at", "updated_at", "duration_ms", "error_code", "error_message"])


async def _is_signup_verification_sendable(verification_id: int | None, now: datetime) -> bool:
    if verification_id is None:
        return False
    return await EmailVerification.filter(
        id=verification_id,
        expires_at__gt=now,
        consumed_at=None,
    ).exists()


async def _is_user_password_reset_sendable(job: BackgroundJob, recipient_email: str) -> bool:
    if job.reference_table != "user" or job.reference_id is None:
        return False
    return await User.filter(
        id=job.reference_id,
        email=recipient_email,
        status=AccountStatus.ACTIVE,
    ).exists()


async def _is_intake_report_sendable(job: BackgroundJob, recipient_email: str) -> bool:
    if (
        job.reference_table != "intake_reports"
        or job.reference_id is None
        or job.user_id != job.reference_id
    ):
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


async def _sendability_cancellation_code(payload: EmailJobPayload, job: BackgroundJob) -> str | None:
    if payload.template is EmailTemplate.SIGNUP_VERIFICATION_CODE:
        if not await _is_signup_verification_sendable(payload.verification_id, datetime.now(config.TIMEZONE)):
            return "EMAIL_VERIFICATION_EXPIRED"
    elif payload.template is EmailTemplate.USER_PASSWORD_RESET:
        if not await _is_user_password_reset_sendable(job, str(payload.recipient_email)):
            return "EMAIL_PASSWORD_RESET_TARGET_INVALID"
    elif payload.template is EmailTemplate.INTAKE_REPORT:
        if not await _is_intake_report_sendable(job, str(payload.recipient_email)):
            return "EMAIL_INTAKE_REPORT_TARGET_INVALID"
    return None


async def _apply_post_delivery_effect(payload: EmailJobPayload, job: BackgroundJob) -> bool:
    if payload.template is not EmailTemplate.USER_PASSWORD_RESET:
        return True
    updated = await User.filter(
        id=job.reference_id,
        email=str(payload.recipient_email),
        status=AccountStatus.ACTIVE,
    ).update(hashed_password=hash_password(payload.temporary_password or ""))
    return updated == 1


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


class WorkerSettings:
    functions = [send_email]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
    queue_name = config.EMAIL_QUEUE_NAME
    max_tries = config.EMAIL_MAX_RETRY_COUNT + 1
