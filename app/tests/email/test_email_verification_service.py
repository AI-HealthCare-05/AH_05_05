from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from tortoise.contrib.test import TestCase
from tortoise.transactions import in_transaction

from app.core.email.verification import EmailVerificationTokenCodec
from app.core.exceptions import (
    EmailVerificationAttemptsExceededError,
    EmailVerificationExpiredError,
    EmailVerificationInvalidError,
    EmailVerificationRateLimitedError,
    InvalidEmailVerificationCodeError,
)
from app.models.email_verifications import EmailVerification
from app.models.enums import BackgroundJobStatus
from app.models.users import User
from app.services.email_verifications import EmailVerificationService

SEOUL = ZoneInfo("Asia/Seoul")


class StubEmailJobService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def enqueue_signup_verification(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(status=BackgroundJobStatus.QUEUED)


class TestEmailVerificationService(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.now = datetime(2026, 9, 7, 12, 0, tzinfo=SEOUL)
        self.jobs = StubEmailJobService()
        self.codec = EmailVerificationTokenCodec("verification-secret", algorithm="HS256", ttl_seconds=600)
        self.service = EmailVerificationService(
            email_job_service=self.jobs,
            token_codec=self.codec,
            code_generator=lambda: "123456",
            now_provider=lambda: self.now,
            secret="verification-secret",
        )

    async def test_request_stores_digest_only_and_enqueues_plain_code_in_memory(self) -> None:
        result = await self.service.request("User@Example.com")

        verification = await EmailVerification.get(id=result.verification_id)
        assert verification.email == "user@example.com"
        assert verification.code_digest != "123456"
        assert len(verification.code_digest) == 64
        assert result.expires_in == 180
        assert result.resend_available_in == 60
        assert self.jobs.calls == [
            {
                "verification_id": verification.id,
                "recipient_email": "user@example.com",
                "verification_code": "123456",
                "expires_at": self.now + timedelta(seconds=180),
            }
        ]

    async def test_request_is_rate_limited_for_sixty_seconds(self) -> None:
        await self.service.request("user@example.com")

        with pytest.raises(EmailVerificationRateLimitedError):
            await self.service.request("user@example.com")

    async def test_resend_expires_previous_open_record(self) -> None:
        first = await self.service.request("user@example.com")
        self.now += timedelta(seconds=180)

        second = await self.service.request("user@example.com")

        previous = await EmailVerification.get(id=first.verification_id)
        assert second.verification_id != first.verification_id
        assert previous.expires_at <= self.now

    async def test_verify_returns_token_and_marks_record_verified(self) -> None:
        requested = await self.service.request("user@example.com")

        result = await self.service.verify(requested.verification_id, "123456")

        verification = await EmailVerification.get(id=requested.verification_id)
        assert verification.verified_at == self.now
        assert result.expires_in == 600
        assert self.codec.verify(result.verification_token).verification_id == verification.id

    async def test_verify_wrong_code_increments_attempts_and_locks_after_five(self) -> None:
        requested = await self.service.request("user@example.com")

        for expected_attempt in range(1, 5):
            with pytest.raises(InvalidEmailVerificationCodeError):
                await self.service.verify(requested.verification_id, "000000")
            verification = await EmailVerification.get(id=requested.verification_id)
            assert verification.attempt_count == expected_attempt

        with pytest.raises(EmailVerificationAttemptsExceededError):
            await self.service.verify(requested.verification_id, "000000")
        with pytest.raises(EmailVerificationAttemptsExceededError):
            await self.service.verify(requested.verification_id, "123456")

    async def test_verify_rejects_expired_record(self) -> None:
        requested = await self.service.request("user@example.com")
        self.now += timedelta(seconds=180)

        with pytest.raises(EmailVerificationExpiredError):
            await self.service.verify(requested.verification_id, "123456")

    async def test_verify_rejects_superseded_record(self) -> None:
        first = await self.service.request("user@example.com")
        self.now += timedelta(seconds=180)
        await self.service.request("user@example.com")

        with pytest.raises(EmailVerificationInvalidError):
            await self.service.verify(first.verification_id, "123456")

    async def test_request_rejects_existing_user(self) -> None:
        await User.create(email="user@example.com", hashed_password="hash", name="사용자")

        from app.core.exceptions import SignupEmailAlreadyExistsError

        with pytest.raises(SignupEmailAlreadyExistsError):
            await self.service.request("user@example.com")

    async def test_signup_token_rejects_tampering_and_email_mismatch(self) -> None:
        requested = await self.service.request("user@example.com")
        verified = await self.service.verify(requested.verification_id, "123456")

        async with in_transaction() as connection:
            with pytest.raises(EmailVerificationInvalidError):
                await self.service.validate_signup_token(
                    verified.verification_token + "tampered",
                    "user@example.com",
                    using_db=connection,
                )
        async with in_transaction() as connection:
            with pytest.raises(EmailVerificationInvalidError):
                await self.service.validate_signup_token(
                    verified.verification_token,
                    "other@example.com",
                    using_db=connection,
                )

    async def test_signup_token_can_only_be_consumed_once(self) -> None:
        requested = await self.service.request("user@example.com")
        verified = await self.service.verify(requested.verification_id, "123456")

        async with in_transaction() as connection:
            verification = await self.service.validate_signup_token(
                verified.verification_token,
                "user@example.com",
                using_db=connection,
            )
            verification.consumed_at = self.now
            await verification.save(using_db=connection, update_fields=["consumed_at"])

        async with in_transaction() as connection:
            with pytest.raises(EmailVerificationInvalidError):
                await self.service.validate_signup_token(
                    verified.verification_token,
                    "user@example.com",
                    using_db=connection,
                )
