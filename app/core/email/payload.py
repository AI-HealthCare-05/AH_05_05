from enum import StrEnum

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, EmailStr, Field, SecretStr, ValidationError


class EmailTemplate(StrEnum):
    ADMIN_TEMPORARY_PASSWORD = "ADMIN_TEMPORARY_PASSWORD"


class EmailJobPayload(BaseModel):
    template: EmailTemplate
    recipient_email: EmailStr
    recipient_name: str = Field(min_length=1, max_length=100)
    temporary_password: str = Field(min_length=1, max_length=255)


class EmailPayloadConfigurationError(RuntimeError):
    """이메일 payload 암호화 키가 없거나 올바르지 않다."""


class InvalidEmailPayloadError(ValueError):
    """암호문이 손상됐거나 이메일 payload 계약과 맞지 않는다."""


class EmailPayloadCodec:
    def __init__(self, key: str | SecretStr | None):
        if isinstance(key, SecretStr):
            key = key.get_secret_value()
        if not key:
            raise EmailPayloadConfigurationError("EMAIL_PAYLOAD_ENCRYPTION_KEY가 설정되지 않았습니다.")
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise EmailPayloadConfigurationError("EMAIL_PAYLOAD_ENCRYPTION_KEY가 올바른 Fernet 키가 아닙니다.") from exc

    def encrypt(self, payload: EmailJobPayload) -> str:
        serialized = payload.model_dump_json().encode("utf-8")
        return self._fernet.encrypt(serialized).decode("ascii")

    def decrypt(self, token: str) -> EmailJobPayload:
        try:
            serialized = self._fernet.decrypt(token.encode("ascii"))
            return EmailJobPayload.model_validate_json(serialized)
        except (InvalidToken, UnicodeEncodeError, ValidationError, ValueError) as exc:
            raise InvalidEmailPayloadError("이메일 작업 payload를 복호화할 수 없습니다.") from exc
