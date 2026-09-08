import json
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.core.email.payload import (
    EmailJobPayload,
    EmailPayloadCodec,
    EmailPayloadConfigurationError,
    EmailTemplate,
    InvalidEmailPayloadError,
)


def payload() -> EmailJobPayload:
    return EmailJobPayload(
        template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
        recipient_email="recipient@example.com",
        recipient_name="홍길동",
        temporary_password="Temp1234!",
    )


def test_email_payload_round_trip_is_encrypted() -> None:
    codec = EmailPayloadCodec(Fernet.generate_key().decode())
    original = payload()

    token = codec.encrypt(original)

    assert codec.decrypt(token) == original
    assert original.recipient_email not in token
    assert original.recipient_name not in token
    assert original.temporary_password not in token


def test_email_payload_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        EmailJobPayload(
            template=EmailTemplate.ADMIN_TEMPORARY_PASSWORD,
            recipient_email="invalid",
            recipient_name="홍길동",
            temporary_password="Temp1234!",
        )


@pytest.mark.parametrize("key", [None, "", "not-a-fernet-key"])
def test_email_payload_codec_rejects_missing_or_invalid_key(key: str | None) -> None:
    with pytest.raises(EmailPayloadConfigurationError):
        EmailPayloadCodec(key)


def test_email_payload_codec_rejects_corrupt_token_without_echoing_it() -> None:
    codec = EmailPayloadCodec(Fernet.generate_key().decode())
    token = "sensitive-corrupt-token"

    with pytest.raises(InvalidEmailPayloadError) as error:
        codec.decrypt(token)

    assert token not in str(error.value)


def test_signup_verification_payload_round_trip_is_encrypted() -> None:
    codec = EmailPayloadCodec(Fernet.generate_key().decode())
    original = EmailJobPayload(
        template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
        recipient_email="recipient@example.com",
        verification_id=17,
        verification_code="012345",
        expires_in=60,
        expires_at=datetime(2026, 9, 7, 3, 1, tzinfo=UTC),
    )

    token = codec.encrypt(original)

    assert codec.decrypt(token) == original
    assert "recipient@example.com" not in token
    assert "012345" not in token


def test_signup_verification_payload_requires_six_digit_code() -> None:
    with pytest.raises(ValidationError):
        EmailJobPayload(
            template=EmailTemplate.SIGNUP_VERIFICATION_CODE,
            recipient_email="recipient@example.com",
            verification_id=17,
            verification_code="12345",
            expires_in=60,
            expires_at=datetime(2026, 9, 7, 3, 1, tzinfo=UTC),
        )


def test_signup_verification_payload_decodes_legacy_job_without_expiry_duration() -> None:
    key = Fernet.generate_key()
    codec = EmailPayloadCodec(key.decode())
    legacy_payload = json.dumps(
        {
            "template": "SIGNUP_VERIFICATION_CODE",
            "recipient_email": "recipient@example.com",
            "verification_id": 17,
            "verification_code": "012345",
            "expires_at": "2099-09-07T03:01:00+00:00",
        }
    ).encode()
    token = Fernet(key).encrypt(legacy_payload).decode()

    decoded = codec.decrypt(token)

    assert decoded.expires_in is None
    assert decoded.expires_at == datetime(2099, 9, 7, 3, 1, tzinfo=UTC)


def test_user_password_reset_payload_requires_only_temporary_password() -> None:
    payload = EmailJobPayload(
        template=EmailTemplate.USER_PASSWORD_RESET,
        recipient_email="recipient@example.com",
        temporary_password="Temp1234!",
    )

    assert payload.recipient_name is None
    assert payload.temporary_password == "Temp1234!"


def test_user_password_reset_payload_requires_temporary_password() -> None:
    with pytest.raises(ValidationError):
        EmailJobPayload(
            template=EmailTemplate.USER_PASSWORD_RESET,
            recipient_email="recipient@example.com",
        )
