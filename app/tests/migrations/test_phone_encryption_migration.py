import importlib.util
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.phone_encryption import PhoneDecryptionError
from app.tests.conftest import TEST_PHONE_ENCRYPTION_KEY

MIGRATION = (
    Path(__file__).resolve().parents[2] / "core/db/migrations/models/11_20260828142722_encrypt_user_phone_numbers.py"
)


def _load_migration():
    assert MIGRATION.is_file()
    spec = importlib.util.spec_from_file_location("phone_encryption_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMigrationDB:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    async def execute_query_dict(self, query):
        return self.rows

    async def execute_many(self, query, values):
        self.updates.append((query, values))


@pytest.mark.asyncio
async def test_upgrade_encrypts_plaintext_and_skips_existing_ciphertext():
    migration = _load_migration()
    existing_ciphertext = Fernet(TEST_PHONE_ENCRYPTION_KEY).encrypt(b"01099998888").decode()
    db = FakeMigrationDB(
        [
            {"id": 1, "phone": "01012345678"},
            {"id": 2, "phone": existing_ciphertext},
        ]
    )

    await migration.upgrade(db)

    assert len(db.updates) == 1
    _, values = db.updates[0]
    assert len(values) == 1
    encrypted_phone, user_id = values[0]
    assert user_id == 1
    assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(encrypted_phone.encode()).decode() == "01012345678"


@pytest.mark.asyncio
async def test_upgrade_rejects_ciphertext_created_with_another_key():
    migration = _load_migration()
    other_key = Fernet.generate_key()
    foreign_ciphertext = Fernet(other_key).encrypt(b"01012345678").decode()
    db = FakeMigrationDB([{"id": 1, "phone": foreign_ciphertext}])

    with pytest.raises(PhoneDecryptionError):
        await migration.upgrade(db)

    assert db.updates == []


@pytest.mark.asyncio
async def test_downgrade_restores_plaintext_phone_numbers():
    migration = _load_migration()
    encrypted_phone = Fernet(TEST_PHONE_ENCRYPTION_KEY).encrypt(b"01012345678").decode()
    db = FakeMigrationDB([{"id": 1, "phone": encrypted_phone}])

    await migration.downgrade(db)

    assert db.updates[0][1] == [("01012345678", 1)]
