import pytest
from cryptography.fernet import Fernet

from app.core.smtp_settings_encryption import (
    SmtpSettingsDecryptionError,
    SmtpSettingsEncryptionConfigurationError,
    decrypt_smtp_password,
    encrypt_smtp_password,
)


def test_smtp_password_round_trip() -> None:
    key = Fernet.generate_key().decode()

    encrypted = encrypt_smtp_password("gmail-app-password", key=key)

    assert encrypted != "gmail-app-password"
    assert decrypt_smtp_password(encrypted, key=key) == "gmail-app-password"


def test_smtp_password_encryption_rejects_missing_key() -> None:
    with pytest.raises(SmtpSettingsEncryptionConfigurationError):
        encrypt_smtp_password("secret", key=None)


def test_smtp_password_decryption_rejects_invalid_token() -> None:
    key = Fernet.generate_key().decode()

    with pytest.raises(SmtpSettingsDecryptionError):
        decrypt_smtp_password("not-a-fernet-token", key=key)
