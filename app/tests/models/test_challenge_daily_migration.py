"""Run migration SQL on a fresh MySQL database, never on the configured app database."""

from collections.abc import AsyncIterator
from importlib import import_module
from uuid import uuid4

import pytest
import pytest_asyncio
from aerich.utils import decompress_dict
from tortoise.backends.mysql.client import MySQLClient
from tortoise.exceptions import IntegrityError

from app.core import config

MIGRATION = "app.core.db.migrations.models.39_20260908151829_challenge_daily_verification"


@pytest_asyncio.fixture(loop_scope="function")
async def migration_db() -> AsyncIterator[MySQLClient]:
    database = f"test_challenge303_{uuid4().hex}"
    db = MySQLClient(
        connection_name=database,
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=database,
    )
    await db.db_create()
    try:
        await db.execute_script("""
            CREATE TABLE challenge_verifications (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_challenge_id BIGINT NOT NULL,
                verification_date DATE NOT NULL,
                idempotency_key VARCHAR(64) NOT NULL UNIQUE,
                KEY idx_challenge_verifications_date (user_challenge_id, verification_date)
            );
            CREATE TABLE user_challenges (
                id BIGINT PRIMARY KEY,
                status VARCHAR(9) NOT NULL DEFAULT 'ACTIVE'
            );
            INSERT INTO user_challenges VALUES (101, 'ACTIVE'), (102, 'EXPIRED');
            INSERT INTO challenge_verifications
                (user_challenge_id, verification_date, idempotency_key)
                VALUES (101, '2026-09-10', 'first-request-key');
        """)
        yield db
    finally:
        await db.close()
        await db.db_delete()


async def test_upgrade_blocks_a_second_request_for_same_day_without_removing_history(migration_db) -> None:
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))

    with pytest.raises(IntegrityError):
        await migration_db.execute_query("""
            INSERT INTO challenge_verifications
                (user_challenge_id, verification_date, idempotency_key)
                VALUES (101, '2026-09-10', 'different-request-key')
        """)
    await migration_db.execute_query("""
        INSERT INTO challenge_verifications
            (user_challenge_id, verification_date, idempotency_key)
            VALUES (101, '2026-09-11', 'next-day-key'), (102, '2026-09-10', 'other-participation-key')
    """)
    rows = await migration_db.execute_query_dict("SELECT idempotency_key FROM challenge_verifications ORDER BY id")
    assert [row["idempotency_key"] for row in rows] == ["first-request-key", "next-day-key", "other-participation-key"]
    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM challenge_verifications")
    daily = [row for row in indexes if row["Key_name"] == "uq_challenge_verifications_daily"]
    assert [(row["Column_name"], row["Non_unique"]) for row in daily] == [
        ("user_challenge_id", 0),
        ("verification_date", 0),
    ]


async def test_existing_duplicates_stop_upgrade_and_preserve_all_rows_and_old_index(migration_db) -> None:
    await migration_db.execute_query("""
        INSERT INTO challenge_verifications
            (user_challenge_id, verification_date, idempotency_key)
            VALUES (101, '2026-09-10', 'existing-duplicate-key')
    """)
    before = await migration_db.execute_query_dict("SELECT * FROM challenge_verifications ORDER BY id")

    with pytest.raises(RuntimeError, match="duplicate"):
        await import_module(MIGRATION).upgrade(migration_db)

    assert await migration_db.execute_query_dict("SELECT * FROM challenge_verifications ORDER BY id") == before
    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM challenge_verifications")
    assert any(row["Key_name"] == "idx_challenge_verifications_date" for row in indexes)
    assert not any(row["Key_name"] == "uq_challenge_verifications_daily" for row in indexes)


async def test_duplicate_inserted_after_preflight_does_not_remove_the_old_index(migration_db) -> None:
    sql = await import_module(MIGRATION).upgrade(migration_db)
    await migration_db.execute_query("""
        INSERT INTO challenge_verifications
            (user_challenge_id, verification_date, idempotency_key)
            VALUES (101, '2026-09-10', 'concurrent-duplicate-key')
    """)

    with pytest.raises(IntegrityError):
        await migration_db.execute_script(sql)

    rows = await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM challenge_verifications")
    assert rows[0]["count"] == 2
    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM challenge_verifications")
    assert any(row["Key_name"] == "idx_challenge_verifications_date" for row in indexes)
    assert not any(row["Key_name"] == "uq_challenge_verifications_daily" for row in indexes)


async def test_downgrade_restores_non_unique_index_without_deleting_records_or_expired_status(migration_db) -> None:
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_script(await migration.downgrade(migration_db))
    await migration_db.execute_query("""
        INSERT INTO challenge_verifications
            (user_challenge_id, verification_date, idempotency_key)
            VALUES (101, '2026-09-10', 'allowed-after-downgrade')
    """)

    rows = await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM challenge_verifications")
    assert rows[0]["count"] == 2
    states = await migration_db.execute_query_dict("SELECT status FROM user_challenges ORDER BY id")
    assert [row["status"] for row in states] == ["ACTIVE", "EXPIRED"]
    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM challenge_verifications")
    assert any(row["Key_name"] == "idx_challenge_verifications_date" and row["Non_unique"] == 1 for row in indexes)


async def test_upgrade_accepts_previously_applied_local_constraint_and_preserves_aerich_history(migration_db) -> None:
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_script("""
        CREATE TABLE aerich (version VARCHAR(255) NOT NULL);
        INSERT INTO aerich VALUES ('37_20260908090000_challenge_daily_verification.py');
    """)
    before = await migration_db.execute_query_dict("SELECT * FROM challenge_verifications ORDER BY id")
    await migration_db.execute_script(await migration.upgrade(migration_db))
    assert await migration_db.execute_query_dict("SELECT * FROM challenge_verifications ORDER BY id") == before
    assert await migration_db.execute_query_dict("SELECT version FROM aerich") == [
        {"version": "37_20260908090000_challenge_daily_verification.py"}
    ]


async def test_malformed_existing_unique_index_stops_without_changing_data(migration_db) -> None:
    await migration_db.execute_script("""
        ALTER TABLE challenge_verifications ADD UNIQUE INDEX uq_challenge_verifications_daily (id);
    """)
    with pytest.raises(RuntimeError, match="index"):
        await import_module(MIGRATION).upgrade(migration_db)


async def test_valid_unique_does_not_hide_a_malformed_legacy_index(migration_db) -> None:
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_script("""
        ALTER TABLE challenge_verifications ADD INDEX idx_challenge_verifications_date (id);
    """)
    with pytest.raises(RuntimeError, match="index"):
        await migration.upgrade(migration_db)


def test_migration_state_preserves_unrelated_models_and_records_daily_uniqueness() -> None:
    previous = decompress_dict(
        import_module("app.core.db.migrations.models.38_20260908132414_seed_custom_challenge_defaults").MODELS_STATE
    )
    current = decompress_dict(import_module(MIGRATION).MODELS_STATE)

    assert current.keys() == previous.keys()
    for name in current.keys() - {"models.ChallengeVerification", "models.UserChallenge"}:
        assert current[name] == previous[name], name
    verification = current["models.ChallengeVerification"]
    assert verification["unique_together"] == [["user_challenge", "verification_date"]]
