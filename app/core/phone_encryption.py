from __future__ import annotations

from typing import Final

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from app.core import config

_USE_CONFIG: Final = object()


class PhoneEncryptionConfigurationError(RuntimeError):
    """전화번호 암호화 키가 없거나 Fernet 형식이 아닐 때 발생한다."""


class PhoneDecryptionError(ValueError):
    """전화번호 암호문이 손상됐거나 다른 키로 생성됐을 때 발생한다."""


def _fernet(key: str | SecretStr | None | object = _USE_CONFIG) -> Fernet:
    selected_key = config.PHONE_ENCRYPTION_KEY if key is _USE_CONFIG else key
    if isinstance(selected_key, SecretStr):
        selected_key = selected_key.get_secret_value()
    if not isinstance(selected_key, str) or not selected_key:
        raise PhoneEncryptionConfigurationError("PHONE_ENCRYPTION_KEY가 설정되지 않았습니다.")

    try:
        return Fernet(selected_key.encode("ascii"))
    except (TypeError, ValueError) as exc:
        raise PhoneEncryptionConfigurationError("PHONE_ENCRYPTION_KEY가 올바른 Fernet 키가 아닙니다.") from exc


def encrypt_phone_number(
    phone_number: str | None,
    *,
    key: str | SecretStr | None | object = _USE_CONFIG,
) -> str | None:
    if phone_number is None:
        return None
    return _fernet(key).encrypt(phone_number.encode("utf-8")).decode("ascii")


def decrypt_phone_number(
    encrypted_phone_number: str | None,
    *,
    key: str | SecretStr | None | object = _USE_CONFIG,
) -> str | None:
    if encrypted_phone_number is None:
        return None
    try:
        return _fernet(key).decrypt(encrypted_phone_number.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise PhoneDecryptionError("전화번호를 복호화할 수 없습니다.") from exc
