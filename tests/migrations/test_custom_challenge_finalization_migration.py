"""#315 finalization migration tests use only UUID-named disposable MySQL databases."""

from collections.abc import AsyncIterator
from copy import deepcopy
from importlib import import_module
from os import getenv
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from aerich import Command
from aerich.models import Aerich
from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise
from tortoise.backends.mysql.client import MySQLClient
from tortoise.exceptions import IntegrityError

from app.core.db.databases import TORTOISE_APP_MODELS, TORTOISE_ORM

MIGRATION = "app.core.db.migrations.models.43_20260910000000_custom_challenge_finalization"
VERSION_42 = "42_20260909180000_merge_challenge_schema_heads.py"
VERSION_43 = "43_20260910000000_custom_challenge_finalization.py"
ROOT = Path(__file__).resolve().parents[2]
MYSQL_OPT_IN = getenv("MIGRATION315_RUN_MYSQL") == "1"
MYSQL_OPT_IN_REASON = "set MIGRATION315_RUN_MYSQL=1 to run disposable MySQL migration tests"


@pytest_asyncio.fixture(loop_scope="function")
async def migration_db() -> AsyncIterator[MySQLClient]:
    if not MYSQL_OPT_IN:
        pytest.skip(MYSQL_OPT_IN_REASON)
    database = f"test_challenge315_migration_{uuid4().hex}"
    db = MySQLClient(
        connection_name=database,
        host=getenv("MIGRATION315_MYSQL_HOST", "127.0.0.1"),
        port=int(getenv("MIGRATION315_MYSQL_PORT", "3315")),
        user=getenv("MIGRATION315_MYSQL_USER", "root"),
        password=getenv("MIGRATION315_MYSQL_PASSWORD", "migration315"),
        database=database,
    )
    await db.db_create()
    try:
        await db.execute_script("""
            CREATE TABLE `user` (`id` BIGINT NOT NULL PRIMARY KEY);
            CREATE TABLE `badges` (
                `id` BIGINT NOT NULL PRIMARY KEY,
                `name` VARCHAR(100) NOT NULL,
                `image_path` VARCHAR(500) NOT NULL
            );
            CREATE TABLE `custom_challenge_templates` (
                `id` BIGINT NOT NULL PRIMARY KEY,
                `reward_badge_id` BIGINT NULL,
                CONSTRAINT `fk_test_template_badge`
                    FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT
            );
            CREATE TABLE `custom_challenge_participations` (
                `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                `user_id` BIGINT NOT NULL,
                `template_id` BIGINT NOT NULL,
                `challenge_type` VARCHAR(10) NOT NULL,
                `challenge_name` VARCHAR(100) NOT NULL,
                `idempotency_key` VARCHAR(64) NOT NULL,
                `joined_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
                `end_at` DATETIME(6) NOT NULL,
                `status` VARCHAR(9) NOT NULL DEFAULT 'ACTIVE',
                CONSTRAINT `fk_custom_participations_user`
                    FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
                CONSTRAINT `fk_custom_participations_template`
                    FOREIGN KEY (`template_id`) REFERENCES `custom_challenge_templates` (`id`) ON DELETE RESTRICT,
                UNIQUE KEY `uq_custom_participation_request` (`user_id`, `idempotency_key`),
                KEY `idx_custom_participation_user_status` (`user_id`, `status`, `joined_at`),
                KEY `idx_custom_participation_template` (`template_id`),
                KEY `idx_custom_participation_end_at` (`end_at`)
            );
            CREATE TABLE `custom_challenge_targets` (
                `id` BIGINT NOT NULL PRIMARY KEY,
                `participation_id` BIGINT NOT NULL,
                `source_id_snapshot` BIGINT NOT NULL,
                `target_name_snapshot` LONGTEXT NOT NULL,
                CONSTRAINT `fk_custom_targets_participation`
                    FOREIGN KEY (`participation_id`) REFERENCES `custom_challenge_participations` (`id`) ON DELETE CASCADE
            );
            CREATE TABLE `custom_challenge_occurrences` (
                `id` BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
                `target_id` BIGINT NOT NULL,
                `scheduled_date` DATE NOT NULL,
                `slot` VARCHAR(7) NOT NULL,
                `scheduled_at` DATETIME(6) NOT NULL,
                CONSTRAINT `fk_custom_occurrences_target`
                    FOREIGN KEY (`target_id`) REFERENCES `custom_challenge_targets` (`id`) ON DELETE CASCADE,
                UNIQUE KEY `uq_custom_occurrence_slot` (`target_id`, `scheduled_date`, `slot`),
                KEY `idx_custom_occurrence_schedule` (`target_id`, `scheduled_at`)
            );

            INSERT INTO `user` VALUES (1), (2);
            INSERT INTO `badges` VALUES
                (10, '복약', 'media/badges/medication.webp'),
                (11, '영양제', 'media/badges/supplement.webp');
            INSERT INTO `custom_challenge_templates` VALUES (20, 10), (21, NULL);
            INSERT INTO `custom_challenge_participations`
                (`id`, `user_id`, `template_id`, `challenge_type`, `challenge_name`, `idempotency_key`,
                 `joined_at`, `end_at`, `status`)
            VALUES
                (30, 1, 20, 'MEDICATION', '보존할 복약 챌린지', 'active-request',
                 '2026-09-01 08:00:00', '2026-09-08 08:00:00', 'ACTIVE'),
                (31, 2, 21, 'SUPPLEMENT', '배지 없는 챌린지', 'cancelled-request',
                 '2026-09-02 09:00:00', '2026-09-09 09:00:00', 'CANCELLED');
            INSERT INTO `custom_challenge_targets` VALUES
                (40, 30, 100, '처방 A'),
                (41, 31, 200, '영양제 B');
            INSERT INTO `custom_challenge_occurrences`
                (`id`, `target_id`, `scheduled_date`, `slot`, `scheduled_at`)
            VALUES
                (50, 40, '2026-09-03', 'MORNING', '2026-09-03 08:00:00'),
                (51, 41, '2026-09-04', 'EVENING', '2026-09-04 19:00:00');
        """)
        yield db
    finally:
        await db.close()
        await db.db_delete()


async def test_upgrade_preserves_rows_backfills_reward_snapshot_and_adds_terminal_defaults(migration_db):
    before_participations = await migration_db.execute_query_dict(
        "SELECT * FROM `custom_challenge_participations` ORDER BY `id`"
    )
    before_occurrences = await migration_db.execute_query_dict(
        "SELECT * FROM `custom_challenge_occurrences` ORDER BY `id`"
    )

    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))

    participations = await migration_db.execute_query_dict(
        "SELECT * FROM `custom_challenge_participations` ORDER BY `id`"
    )
    occurrences = await migration_db.execute_query_dict("SELECT * FROM `custom_challenge_occurrences` ORDER BY `id`")
    assert [{key: row[key] for key in before_participations[0]} for row in participations] == before_participations
    assert [{key: row[key] for key in before_occurrences[0]} for row in occurrences] == before_occurrences
    assert [row["reward_badge_id"] for row in participations] == [10, None]
    assert [row["target_count"] for row in participations] == [0, 0]
    assert [row["completed_count"] for row in participations] == [0, 0]
    assert [str(row["progress_rate"]) for row in participations] == ["0.00", "0.00"]
    assert [row["completed_at"] for row in participations] == [None, None]
    assert [row["finalized_at"] for row in participations] == [None, None]
    assert [row["is_completed"] for row in occurrences] == [0, 0]


async def test_upgrade_creates_separate_award_history_with_uniqueness_and_restrict_fks(migration_db):
    migration = import_module(MIGRATION)
    await migration_db.execute_script(await migration.upgrade(migration_db))
    await migration_db.execute_query(
        """
        INSERT INTO `custom_challenge_badge_awards`
            (`id`, `user_id`, `badge_id`, `participation_id`, `badge_name`, `badge_image_path`)
        VALUES (60, 1, 10, 30, '복약', 'media/badges/medication.webp');
        """
    )

    with pytest.raises(IntegrityError):
        await migration_db.execute_query(
            """
            INSERT INTO `custom_challenge_badge_awards`
                (`id`, `user_id`, `badge_id`, `participation_id`, `badge_name`, `badge_image_path`)
            VALUES (61, 1, 10, 30, '복약', 'media/badges/medication.webp');
            """
        )
    with pytest.raises(IntegrityError):
        await migration_db.execute_query("DELETE FROM `badges` WHERE `id` = 10")
    with pytest.raises(IntegrityError):
        await migration_db.execute_query("DELETE FROM `custom_challenge_participations` WHERE `id` = 30")

    indexes = await migration_db.execute_query_dict("SHOW INDEX FROM `custom_challenge_badge_awards`")
    index_columns = {}
    for row in indexes:
        index_columns.setdefault(row["Key_name"], []).append(row["Column_name"])
    assert index_columns["uq_custom_badge_award_participation_badge"] == ["participation_id", "badge_id"]
    assert index_columns["idx_custom_badge_award_user_awarded"] == ["user_id", "awarded_at"]
    assert index_columns["idx_custom_badge_award_badge"] == ["badge_id"]


async def test_upgrade_is_additive_and_downgrade_removes_only_migration_43_schema() -> None:
    migration = import_module(MIGRATION)
    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert "DROP TABLE" not in upgrade_sql.upper()
    assert "DROP COLUMN" not in upgrade_sql.upper()
    assert "DELETE FROM" not in upgrade_sql.upper()
    assert "`user_badges`" not in upgrade_sql
    assert "DROP TABLE IF EXISTS `custom_challenge_badge_awards`" in downgrade_sql
    assert "DROP COLUMN `reward_badge_id`" in downgrade_sql
    assert "DROP COLUMN `is_completed`" in downgrade_sql


def test_migration_43_snapshot_is_frozen_at_the_registered_runtime_models() -> None:
    current = decompress_dict(import_module(MIGRATION).MODELS_STATE)
    previous = decompress_dict(
        import_module("app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads").MODELS_STATE
    )

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    live = decompress_dict(compress_dict(get_models_describe("models")))

    assert current == live
    assert len(current) == len(previous) + 1
    assert "models.CustomChallengeBadgeAward" in current
    assert "models.UserBadge" in current
    assert current["models.UserBadge"] == previous["models.UserBadge"]


@pytest.mark.skipif(not MYSQL_OPT_IN, reason=MYSQL_OPT_IN_REASON)
async def test_real_aerich_upgrades_a_generated_head_42_schema_to_43() -> None:
    database = f"test_challenge315_aerich_{uuid4().hex}"
    db_admin = MySQLClient(
        connection_name=database,
        host=getenv("MIGRATION315_MYSQL_HOST", "127.0.0.1"),
        port=int(getenv("MIGRATION315_MYSQL_PORT", "3315")),
        user=getenv("MIGRATION315_MYSQL_USER", "root"),
        password=getenv("MIGRATION315_MYSQL_PASSWORD", "migration315"),
        database=database,
    )
    await db_admin.db_create()
    await db_admin.close()
    try:
        settings = deepcopy(TORTOISE_ORM)
        credentials = settings["connections"]["default"]["credentials"]
        credentials.update(
            host=getenv("MIGRATION315_MYSQL_HOST", "127.0.0.1"),
            port=int(getenv("MIGRATION315_MYSQL_PORT", "3315")),
            user=getenv("MIGRATION315_MYSQL_USER", "root"),
            password=getenv("MIGRATION315_MYSQL_PASSWORD", "migration315"),
            database=database,
        )
        command = Command(settings, app="models", location=str(ROOT / "app/core/db/migrations"))
        await command.init()
        await Tortoise.generate_schemas()
        db = Tortoise.get_connection("default")

        migration = import_module(MIGRATION)
        previous = decompress_dict(
            import_module("app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads").MODELS_STATE
        )
        generated_fks = await db.execute_query_dict("""
            SELECT CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'custom_challenge_participations'
              AND COLUMN_NAME = 'reward_badge_id'
              AND REFERENCED_TABLE_NAME = 'badges';
        """)
        assert len(generated_fks) == 1
        generated_fk = str(generated_fks[0]["CONSTRAINT_NAME"]).replace("`", "``")
        await db.execute_script(
            "ALTER TABLE `custom_challenge_participations` "
            f"DROP FOREIGN KEY `{generated_fk}`, "
            "ADD CONSTRAINT `fk_custom_participations_reward_badge` "
            "FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT;"
        )
        await db.execute_script(await migration.downgrade(db))
        await Aerich.all().delete()
        applied_versions = [version for version in await command.history() if version != VERSION_43]
        for version in applied_versions:
            await Aerich.create(
                version=version,
                app="models",
                content=previous if version == VERSION_42 else {},
            )

        assert await command.heads() == [VERSION_43]
        assert await command.upgrade(fake=False) == [VERSION_43]
        assert await command.heads() == []
        history = await Aerich.all().order_by("id").values("version", "content")
        assert [row["version"] for row in history] == [*applied_versions, VERSION_43]
        assert history[-1]["content"] == decompress_dict(migration.MODELS_STATE)

        columns = await db.execute_query_dict("""
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND (
                (TABLE_NAME = 'custom_challenge_participations'
                 AND COLUMN_NAME IN ('reward_badge_id', 'target_count', 'completed_count',
                                     'progress_rate', 'completed_at', 'finalized_at'))
                OR (TABLE_NAME = 'custom_challenge_occurrences' AND COLUMN_NAME = 'is_completed')
              );
        """)
        assert {(row["TABLE_NAME"], row["COLUMN_NAME"]) for row in columns} == {
            ("custom_challenge_participations", "reward_badge_id"),
            ("custom_challenge_participations", "target_count"),
            ("custom_challenge_participations", "completed_count"),
            ("custom_challenge_participations", "progress_rate"),
            ("custom_challenge_participations", "completed_at"),
            ("custom_challenge_participations", "finalized_at"),
            ("custom_challenge_occurrences", "is_completed"),
        }
        assert await db.execute_query_dict("SHOW TABLES LIKE 'custom_challenge_badge_awards'")
    finally:
        await Tortoise.close_connections()
        assert database.startswith("test_challenge315_aerich_") and len(database) == 57
        await db_admin.db_delete()
        await db_admin.close()
