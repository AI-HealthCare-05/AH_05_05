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
