import secrets

import pytest

from app.core.email.verification import (
    EmailVerificationConfigurationError,
    EmailVerificationTokenCodec,
    InvalidEmailVerificationTokenError,
    digest_verification_code,
    generate_verification_code,
)
from app.models.enums import EmailVerificationPurpose


def test_generated_code_is_six_digits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "randbelow", lambda _limit: 42)

    assert generate_verification_code() == "000042"


def test_digest_is_bound_to_verification_identity() -> None:
    first = digest_verification_code(
        secret="secret",
        verification_id=1,
        email="User@Example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
        code="123456",
    )
    second = digest_verification_code(
        secret="secret",
        verification_id=2,
        email="user@example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
        code="123456",
    )

    assert len(first) == 64
    assert first != second


def test_digest_requires_secret() -> None:
    with pytest.raises(EmailVerificationConfigurationError):
        digest_verification_code(
            secret=None,
            verification_id=1,
            email="user@example.com",
            purpose=EmailVerificationPurpose.SIGNUP,
            code="123456",
        )


def test_token_round_trip_and_tampering_rejection() -> None:
    codec = EmailVerificationTokenCodec("secret", algorithm="HS256", ttl_seconds=600)
    token = codec.issue(
        verification_id=7,
        email="user@example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
    )

    claims = codec.verify(token)

    assert claims.verification_id == 7
    assert claims.email == "user@example.com"
    assert claims.purpose is EmailVerificationPurpose.SIGNUP
    with pytest.raises(InvalidEmailVerificationTokenError):
        codec.verify(token + "tampered")


def test_token_rejects_expiry() -> None:
    codec = EmailVerificationTokenCodec("secret", algorithm="HS256", ttl_seconds=-1)
    token = codec.issue(
        verification_id=7,
        email="user@example.com",
        purpose=EmailVerificationPurpose.SIGNUP,
    )

    with pytest.raises(InvalidEmailVerificationTokenError):
        codec.verify(token)
