import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import SecretStr
from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.core import config
from app.core.email.verification import (
    EmailVerificationTokenCodec,
    InvalidEmailVerificationTokenError,
    digest_verification_code,
    generate_verification_code,
)
from app.core.exceptions import (
    EmailDeliveryUnavailableError,
    EmailVerificationAttemptsExceededError,
    EmailVerificationExpiredError,
    EmailVerificationInvalidError,
    EmailVerificationRateLimitedError,
    InvalidEmailVerificationCodeError,
    SignupEmailAlreadyExistsError,
)
from app.models.background_jobs import BackgroundJob
from app.models.email_verifications import EmailVerification
from app.models.enums import BackgroundJobStatus, EmailVerificationPurpose
from app.repositories.email_verification_repository import EmailVerificationRepository
from app.repositories.user_repository import UserRepository


class SignupVerificationEmailEnqueuer(Protocol):
    async def enqueue_signup_verification(
        self,
        *,
        verification_id: int,
        recipient_email: str,
        verification_code: str,
        expires_at: datetime,
    ) -> BackgroundJob: ...


@dataclass(frozen=True)
class EmailVerificationRequestResult:
    verification_id: int
    expires_in: int
    resend_available_in: int


@dataclass(frozen=True)
class EmailVerificationVerifyResult:
    verification_token: str
    expires_in: int


class EmailVerificationService:
    def __init__(
        self,
        *,
        repository: EmailVerificationRepository | None = None,
        user_repository: UserRepository | None = None,
        email_job_service: SignupVerificationEmailEnqueuer | None = None,
        token_codec: EmailVerificationTokenCodec | None = None,
        code_generator: Callable[[], str] = generate_verification_code,
        now_provider: Callable[[], datetime] | None = None,
        secret: str | SecretStr | None = None,
    ) -> None:
        self.repository = repository or EmailVerificationRepository()
        self.user_repository = user_repository or UserRepository()
        if email_job_service is None:
            from app.services.email_jobs import EmailJobService

            email_job_service = EmailJobService()
        self.email_job_service = email_job_service
        self._token_codec = token_codec
        self.code_generator = code_generator
        self.now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))
        self.secret = secret if secret is not None else config.EMAIL_VERIFICATION_SECRET

    def _codec(self) -> EmailVerificationTokenCodec:
        return self._token_codec or EmailVerificationTokenCodec(
            self.secret,
            algorithm=config.JWT_ALGORITHM,
            ttl_seconds=config.EMAIL_VERIFICATION_TOKEN_TTL_SECONDS,
        )

    async def request(self, email: str) -> EmailVerificationRequestResult:
        normalized_email = email.casefold()
        if await self.user_repository.exists_by_email(normalized_email):
            raise SignupEmailAlreadyExistsError()

        now = self.now_provider()
        code = self.code_generator()
        purpose = EmailVerificationPurpose.SIGNUP
        expires_at = now + timedelta(seconds=config.EMAIL_VERIFICATION_TTL_SECONDS)
        async with in_transaction() as connection:
            latest = await self.repository.get_latest(
                email=normalized_email,
                purpose=purpose,
                using_db=connection,
            )
            if latest is not None and latest.expires_at > now:
                raise EmailVerificationRateLimitedError()
            await self.repository.expire_open(
                email=normalized_email,
                purpose=purpose,
                now=now,
                using_db=connection,
            )
            verification = await EmailVerification.create(
                email=normalized_email,
                purpose=purpose,
                code_digest="0" * 64,
                expires_at=expires_at,
                using_db=connection,
            )
            verification.code_digest = digest_verification_code(
                secret=self.secret,
                verification_id=verification.id,
                email=normalized_email,
                purpose=purpose,
                code=code,
            )
            await verification.save(using_db=connection, update_fields=["code_digest"])

        job = await self.email_job_service.enqueue_signup_verification(
            verification_id=verification.id,
            recipient_email=normalized_email,
            verification_code=code,
            expires_at=expires_at,
        )
        if job.status is BackgroundJobStatus.FAILED:
            await EmailVerification.filter(id=verification.id).update(expires_at=now, updated_at=now)
            raise EmailDeliveryUnavailableError()
        return EmailVerificationRequestResult(
            verification_id=verification.id,
            expires_in=config.EMAIL_VERIFICATION_TTL_SECONDS,
            resend_available_in=config.EMAIL_VERIFICATION_RESEND_SECONDS,
        )

    async def verify(self, verification_id: int, code: str) -> EmailVerificationVerifyResult:
        now = self.now_provider()
        verification_error: Exception | None = None
        async with in_transaction() as connection:
            verification = await self.repository.get_for_update(verification_id, using_db=connection)
            if verification is None or verification.consumed_at is not None:
                raise EmailVerificationInvalidError()
            latest = await self.repository.get_latest(
                email=verification.email,
                purpose=verification.purpose,
                using_db=connection,
            )
            if latest is None or latest.id != verification.id:
                raise EmailVerificationInvalidError()
            if verification.expires_at <= now:
                raise EmailVerificationExpiredError()
            if verification.attempt_count >= config.EMAIL_VERIFICATION_MAX_ATTEMPTS:
                raise EmailVerificationAttemptsExceededError()
            candidate = digest_verification_code(
                secret=self.secret,
                verification_id=verification.id,
                email=verification.email,
                purpose=verification.purpose,
                code=code,
            )
            if not hmac.compare_digest(candidate, verification.code_digest):
                verification.attempt_count += 1
                verification.updated_at = now
                await verification.save(
                    using_db=connection,
                    update_fields=["attempt_count", "updated_at"],
                )
                if verification.attempt_count >= config.EMAIL_VERIFICATION_MAX_ATTEMPTS:
                    verification_error = EmailVerificationAttemptsExceededError()
                else:
                    verification_error = InvalidEmailVerificationCodeError()
            else:
                verification.verified_at = now
                verification.updated_at = now
                await verification.save(using_db=connection, update_fields=["verified_at", "updated_at"])

        if verification_error is not None:
            raise verification_error

        return EmailVerificationVerifyResult(
            verification_token=self._codec().issue(
                verification_id=verification.id,
                email=verification.email,
                purpose=verification.purpose,
            ),
            expires_in=config.EMAIL_VERIFICATION_TOKEN_TTL_SECONDS,
        )

    async def validate_signup_token(
        self,
        token: str,
        email: str,
        *,
        using_db: BaseDBAsyncClient,
    ) -> EmailVerification:
        try:
            claims = self._codec().verify(token)
        except InvalidEmailVerificationTokenError as exc:
            raise EmailVerificationInvalidError() from exc
        verification = await self.repository.get_for_update(claims.verification_id, using_db=using_db)
        if (
            verification is None
            or claims.purpose is not EmailVerificationPurpose.SIGNUP
            or verification.purpose is not EmailVerificationPurpose.SIGNUP
            or claims.email != email.casefold()
            or verification.email != email.casefold()
            or verification.verified_at is None
            or verification.consumed_at is not None
        ):
            raise EmailVerificationInvalidError()
        return verification
