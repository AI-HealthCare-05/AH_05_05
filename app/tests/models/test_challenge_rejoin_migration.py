"""Migration SQL is exercised only on a uniquely named disposable MySQL database."""

from collections.abc import AsyncIterator
from importlib import import_module
from json import dumps
from uuid import uuid4

import pytest
import pytest_asyncio
from aerich.utils import decompress_dict
from tortoise.backends.mysql.client import MySQLClient
from tortoise.exceptions import IntegrityError

from app.core import config

MIGRATION = "app.core.db.migrations.models.41_20260909120000_challenge_rejoin_attempts"


@pytest_asyncio.fixture(loop_scope="function")
async def migration_db() -> AsyncIterator[MySQLClient]:
    database = f"test_challenge304_{uuid4().hex}"
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
            CREATE TABLE users (id BIGINT PRIMARY KEY);
            INSERT INTO users VALUES (1);
            CREATE TABLE user_challenges (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                challenge_id BIGINT NOT NULL,
                status VARCHAR(9) NOT NULL,
                UNIQUE KEY uq_user_challenges_user_challenge (user_id, challenge_id),
                KEY idx_user_challenges_user_status (user_id, status),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
            );
            CREATE TABLE challenge_verifications (
                id BIGINT PRIMARY KEY,
                user_challenge_id BIGINT NOT NULL,
                FOREIGN KEY (user_challenge_id) REFERENCES user_challenges(id) ON DELETE RESTRICT
            );
            INSERT INTO user_challenges VALUES (101, 1, 42, 'CANCELLED');
            INSERT INTO challenge_verifications VALUES (201, 101);
        """)
        yield db
    finally:
        await db.close()
        await db.db_delete()


async def test_upgrade_allows_new_attempt_and_preserves_old_attempt_and_verification(migration_db):
    migration = import_module(MIGRATION)
    before = await migration_db.execute_query_dict("SELECT * FROM user_challenges")
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    assert await migration_db.execute_query_dict("SELECT * FROM user_challenges WHERE id=101") == before
    assert await migration_db.execute_query_dict("SELECT * FROM challenge_verifications") == [
        {"id": 201, "user_challenge_id": 101}
    ]
    await migration_db.execute_script(await migration.upgrade(migration_db))
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 2


async def test_downgrade_refuses_duplicate_histories_without_deleting_records(migration_db):
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    before = await migration_db.execute_query_dict("SELECT * FROM user_challenges ORDER BY id")
    with pytest.raises(RuntimeError, match="duplicate"):
        await migration.downgrade(migration_db)
    assert await migration_db.execute_query_dict("SELECT * FROM user_challenges ORDER BY id") == before
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM challenge_verifications"))[0][
        "count"
    ] == 1


async def test_downgrade_restores_uniqueness_when_no_rejoin_exists(migration_db):
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_script(await migration.downgrade(migration_db))
    with pytest.raises(IntegrityError):
        await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 1


async def test_concurrent_rejoin_after_downgrade_preflight_is_preserved(migration_db):
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    sql = await migration.downgrade(migration_db)
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    with pytest.raises(IntegrityError):
        await migration_db.execute_script(sql)
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 2


async def test_unexpected_legacy_index_stops_before_changing_history(migration_db):
    await migration_db.execute_script("""
        ALTER TABLE user_challenges DROP INDEX uq_user_challenges_user_challenge,
            ADD UNIQUE INDEX uq_user_challenges_user_challenge (id);
    """)
    with pytest.raises(RuntimeError, match="index"):
        await import_module(MIGRATION).upgrade(migration_db)
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 1


async def test_upgrade_accepts_generated_unique_name_and_preserves_foreign_key_support(migration_db):
    await migration_db.execute_script("""
        ALTER TABLE user_challenges RENAME INDEX uq_user_challenges_user_challenge TO uid_user_chall_generated;
        ALTER TABLE user_challenges DROP INDEX idx_user_challenges_user_status;
    """)
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM user_challenges")
    lookup = [row for row in indexes if row["Key_name"] == "idx_user_challenges_user_challenge"]
    assert [(row["Column_name"], row["Non_unique"]) for row in lookup] == [("user_id", 1), ("challenge_id", 1)]
    with pytest.raises(IntegrityError):
        await migration_db.execute_query("DELETE FROM users WHERE id=1")


async def test_newer_applied_model_snapshot_stops_upgrade_before_any_schema_change(migration_db):
    await migration_db.execute_script("""
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
    """)
    state = decompress_dict(
        import_module("app.core.db.migrations.models.39_20260908151829_challenge_daily_verification").MODELS_STATE
    )
    state["models.CustomChallengeParticipation"] = {"table": "custom_challenge_participations"}
    await migration_db.execute_query(
        "INSERT INTO aerich VALUES (40, %s, 'models', %s)",
        ["40_custom_challenge.py", dumps(state)],
    )
    before = await migration_db.execute_query_dict("SELECT * FROM aerich")
    indexes_before = await migration_db.execute_query_dict("SHOW INDEX FROM user_challenges")
    with pytest.raises(RuntimeError, match="integrate"):
        await import_module(MIGRATION).upgrade(migration_db)
    assert await migration_db.execute_query_dict("SELECT * FROM aerich") == before
    assert await migration_db.execute_query_dict("SHOW INDEX FROM user_challenges") == indexes_before
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 1


async def test_previous_applied_snapshot_allows_upgrade_and_keeps_aerich_history(migration_db):
    await migration_db.execute_script("""
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
    """)
    state = decompress_dict(
        import_module("app.core.db.migrations.models.39_20260908151829_challenge_daily_verification").MODELS_STATE
    )
    await migration_db.execute_query("INSERT INTO aerich VALUES (39, '39_daily.py', 'models', %s)", [dumps(state)])
    before = await migration_db.execute_query_dict("SELECT * FROM aerich")
    await migration_db.execute_script(await import_module(MIGRATION).upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    assert await migration_db.execute_query_dict("SELECT * FROM aerich") == before


def test_migration_snapshot_preserves_other_models_and_records_attempt_lookup():
    previous = decompress_dict(
        import_module("app.core.db.migrations.models.39_20260908151829_challenge_daily_verification").MODELS_STATE
    )
    current = decompress_dict(import_module(MIGRATION).MODELS_STATE)
    previous["models.UserChallenge"]["unique_together"] = []
    previous["models.UserChallenge"]["indexes"].append(
        {
            "fields": ["user_id", "challenge_id"],
            "expressions": [],
            "name": "idx_user_challenges_user_challenge",
            "type": "",
            "extra": "",
        }
    )
    assert current == previous
