import importlib

import pytest

TEST_PHONE_ENCRYPTION_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _phone_encryption_module():
    return importlib.import_module("app.core.phone_encryption")


def test_phone_number_is_encrypted_at_rest_and_can_be_decrypted():
    module = _phone_encryption_module()

    encrypted = module.encrypt_phone_number(
        "01012345678",
        key=TEST_PHONE_ENCRYPTION_KEY,
    )

    assert encrypted != "01012345678"
    assert encrypted.startswith("gAAAAA")
    assert module.decrypt_phone_number(encrypted, key=TEST_PHONE_ENCRYPTION_KEY) == "01012345678"


@pytest.mark.parametrize("key", [None, "", "not-a-fernet-key"])
def test_phone_encryption_rejects_missing_or_invalid_key(key):
    module = _phone_encryption_module()

    with pytest.raises(module.PhoneEncryptionConfigurationError):
        module.encrypt_phone_number("01012345678", key=key)


def test_phone_decryption_rejects_tampered_ciphertext():
    module = _phone_encryption_module()

    with pytest.raises(module.PhoneDecryptionError):
        module.decrypt_phone_number(
            "gAAAAA-invalid-ciphertext",
            key=TEST_PHONE_ENCRYPTION_KEY,
        )


def test_optional_phone_helpers_preserve_none():
    module = _phone_encryption_module()

    assert module.encrypt_phone_number(None, key=TEST_PHONE_ENCRYPTION_KEY) is None
    assert module.decrypt_phone_number(None, key=TEST_PHONE_ENCRYPTION_KEY) is None
