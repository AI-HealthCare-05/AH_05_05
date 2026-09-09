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


@pytest.mark.parametrize(
    "previous_migration",
    ["40_20260908160000_custom_challenge_participations", "40_20260909143654_allow_ocr_recapture_error_code"],
)
async def test_newer_applied_model_snapshot_stops_upgrade_before_any_schema_change(migration_db, previous_migration):
    await migration_db.execute_script("""
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
    """)
    state = decompress_dict(import_module("app.core.db.migrations.models." + previous_migration).MODELS_STATE)
    state["models.FutureChallengeModel"] = {"table": "future_challenge_models"}
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


@pytest.mark.parametrize(
    "previous_migration",
    ["40_20260908160000_custom_challenge_participations", "40_20260909143654_allow_ocr_recapture_error_code"],
)
async def test_previous_applied_snapshot_allows_upgrade_and_keeps_aerich_history(migration_db, previous_migration):
    await migration_db.execute_script("""
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
    """)
    state = decompress_dict(import_module("app.core.db.migrations.models." + previous_migration).MODELS_STATE)
    await migration_db.execute_query("INSERT INTO aerich VALUES (40, '40_custom.py', 'models', %s)", [dumps(state)])
    before = await migration_db.execute_query_dict("SELECT * FROM aerich")
    await migration_db.execute_script(await import_module(MIGRATION).upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    assert await migration_db.execute_query_dict("SELECT * FROM aerich") == before


async def test_same_model_keys_with_changed_custom_field_stop_before_schema_or_history_changes(migration_db):
    state = decompress_dict(
        import_module("app.core.db.migrations.models.40_20260908160000_custom_challenge_participations").MODELS_STATE
    )
    fields = state["models.CustomChallengeTarget"]["data_fields"]
    state["models.CustomChallengeTarget"]["data_fields"] = [
        field for field in fields if field["name"] != "target_name_snapshot"
    ]
    await migration_db.execute_script("""
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
    """)
    await migration_db.execute_query("INSERT INTO aerich VALUES (40, '40_custom.py', 'models', %s)", [dumps(state)])
    history_before = await migration_db.execute_query_dict("SELECT * FROM aerich")
    indexes_before = await migration_db.execute_query_dict("SHOW INDEX FROM user_challenges")
    with pytest.raises(RuntimeError, match="snapshot"):
        await import_module(MIGRATION).upgrade(migration_db)
    assert await migration_db.execute_query_dict("SELECT * FROM aerich") == history_before
    assert await migration_db.execute_query_dict("SHOW INDEX FROM user_challenges") == indexes_before


def test_migration_snapshot_preserves_other_models_and_records_attempt_lookup():
    previous = decompress_dict(
        import_module("app.core.db.migrations.models.40_20260908160000_custom_challenge_participations").MODELS_STATE
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


async def test_migration_40_to_41_preserves_custom_schema_data_and_applied_history(migration_db):
    previous = import_module("app.core.db.migrations.models.40_20260908160000_custom_challenge_participations")
    migration = import_module(MIGRATION)
    await migration_db.execute_script("""
        CREATE TABLE `user` (id BIGINT PRIMARY KEY);
        CREATE TABLE custom_challenge_templates (id BIGINT PRIMARY KEY);
        CREATE TABLE care_episodes (id BIGINT PRIMARY KEY);
        CREATE TABLE user_suppl_nutrient (id BIGINT PRIMARY KEY);
        CREATE TABLE follow_up_visits (id BIGINT PRIMARY KEY);
        INSERT INTO `user` VALUES (1);
        INSERT INTO custom_challenge_templates VALUES (1);
        INSERT INTO care_episodes VALUES (1);
        CREATE TABLE aerich (id INT PRIMARY KEY, version VARCHAR(255), app VARCHAR(100), content JSON);
        INSERT INTO aerich VALUES
            (54, '39_20260908000000_align_erd125_care_episodes.py', 'models', '{}'),
            (55, '39_20260908151829_challenge_daily_verification.py', 'models', '{}');
    """)
    await migration_db.execute_script(await previous.upgrade(migration_db))
    await migration_db.execute_query(
        "INSERT INTO aerich VALUES (56, '40_20260908160000_custom_challenge_participations.py', 'models', %s)",
        [dumps(decompress_dict(previous.MODELS_STATE))],
    )
    await migration_db.execute_script("""
        INSERT INTO custom_challenge_participations
            (id, user_id, template_id, challenge_type, challenge_name, idempotency_key, joined_at, end_at, status)
            VALUES (301, 1, 1, 'MEDICATION', 'Preserved custom challenge', 'preserved-request',
                    '2026-09-08 08:00:00', '2026-09-15 08:00:00', 'ACTIVE');
        INSERT INTO custom_challenge_targets
            (id, participation_id, care_episode_id, source_id_snapshot, target_name_snapshot)
            VALUES (401, 301, 1, 1, 'Preserved prescription');
        INSERT INTO custom_challenge_occurrences
            (id, target_id, scheduled_date, slot, scheduled_at)
            VALUES (501, 401, '2026-09-09', 'MORNING', '2026-09-09 08:00:00');
    """)
    custom_tables = ("custom_challenge_participations", "custom_challenge_targets", "custom_challenge_occurrences")
    schema_before = {
        table: await migration_db.execute_query_dict(f"SHOW CREATE TABLE `{table}`") for table in custom_tables
    }
    rows_before = {
        table: await migration_db.execute_query_dict(f"SELECT * FROM `{table}` ORDER BY id") for table in custom_tables
    }
    history_before = await migration_db.execute_query_dict("SELECT * FROM aerich ORDER BY id")
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_query("INSERT INTO user_challenges VALUES (102, 1, 42, 'ACTIVE')")
    for table in custom_tables:
        assert await migration_db.execute_query_dict(f"SHOW CREATE TABLE `{table}`") == schema_before[table]
        assert await migration_db.execute_query_dict(f"SELECT * FROM `{table}` ORDER BY id") == rows_before[table]
    assert await migration_db.execute_query_dict("SELECT * FROM aerich ORDER BY id") == history_before
    assert await migration_db.execute_query_dict("SELECT * FROM challenge_verifications") == [
        {"id": 201, "user_challenge_id": 101}
    ]
    with pytest.raises(RuntimeError, match="duplicate"):
        await migration.downgrade(migration_db)
    assert (await migration_db.execute_query_dict("SELECT COUNT(*) AS count FROM user_challenges"))[0]["count"] == 2
