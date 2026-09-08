"""Opt-in MySQL DDL verification on a disposable localhost:43316 container only."""

import os
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import asyncmy
import pytest
import pytest_asyncio
from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise
from tortoise.exceptions import OperationalError

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION_NAME = "39_20260908000000_align_erd125_care_episodes"
MIGRATION_DIR = Path(__file__).resolve().parents[2] / "app/core/db/migrations/models"
migration = import_module(f"app.core.db.migrations.models.{MIGRATION_NAME}")


def test_migration_snapshot_matches_current_models():
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    expected = decompress_dict(compress_dict(get_models_describe("models")))
    assert decompress_dict(migration.MODELS_STATE) == expected


async def test_downgrade_refuses_before_touching_a_database():
    with pytest.raises(RuntimeError, match="intentionally irreversible"):
        await migration.downgrade(None)


@pytest_asyncio.fixture(loop_scope="function")
async def legacy_mysql():
    if os.environ.get("ERD125_DISPOSABLE_MYSQL") != "1":
        pytest.skip("requires explicit ERD125_DISPOSABLE_MYSQL=1 and the disposable localhost:43316 MySQL")
    # Never consume the application DB configuration or accept an arbitrary URL.
    database = "erd125_verify_" + uuid4().hex
    admin = await asyncmy.connect(host="127.0.0.1", port=43316, user="root", password="erd125-test-only")
    async with admin.cursor() as cursor:
        await cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
    try:
        await Tortoise.init(
            db_url=f"mysql://root:erd125-test-only@127.0.0.1:43316/{database}",
            modules={"models": TORTOISE_APP_MODELS},
            timezone="Asia/Seoul",
        )
        db = Tortoise.get_connection("default")
        for path in sorted(MIGRATION_DIR.glob("[0-9]*.py"), key=lambda item: (int(item.name.split("_")[0]), item.name)):
            if int(path.name.split("_")[0]) >= 39:
                break
            previous = import_module(f"app.core.db.migrations.models.{path.stem}")
            sql = await previous.upgrade(db)
            if sql.strip():
                await db.execute_script(sql)
            await db.execute_query(
                "INSERT INTO aerich (version, app, content) VALUES (%s, 'models', '{}')", [path.name]
            )
        yield db
    finally:
        await Tortoise.close_connections()
        # Name is generated locally above; this cannot target the service DB.
        assert database.startswith("erd125_verify_") and len(database) == len("erd125_verify_") + 32
        async with admin.cursor() as cursor:
            await cursor.execute(f"DROP DATABASE `{database}`")
        admin.close()


async def test_upgrade_archives_removed_rows_and_enforces_the_new_contract(legacy_mysql):
    db = legacy_mysql
    long_hospital = "가" * 253 + "병원"
    await db.execute_script("""
        INSERT INTO `user` (`id`, `email`, `hashed_password`, `name`) VALUES (1, 'migration@example.test', 'test-only', '테스트');
        INSERT INTO `care_episodes` (`id`, `user_id`, `title`, `started_at`, `completed_at`, `status`, `diagnosis`, `surgery`, `discharge_date`)
        VALUES (1, 1, '원래 제목', '2026-09-08 09:00:00', '2026-09-08 11:00:00', 'COMPLETED', '진단 테스트', '수술 테스트', '2026-09-08');
        INSERT INTO `care_episodes` (`id`, `user_id`, `title`, `alias`, `hospital_name`) VALUES
          (2, 1, '자동 생성 제목', '  사용자 별칭  ', '원문 병원'),
          (3, 1, '자동 생성 제목', '   ', '기본 병원'),
          (4, 1, '자동 생성 제목', NULL, NULL),
          (5, 1, '자동 생성 제목', '   ', '   ');
        INSERT INTO `care_advices` (`id`, `care_episode_id`, `text`, `display_order`, `category`)
        VALUES (1, 1, '삭제 전 테스트 안내', 1, 'OTHER');
        INSERT INTO `recovery_guides` (`id`, `care_episode_id`, `guide_content`, `patient_context_hash`, `model_name`, `prompt_version`, `schema_version`, `safety_status`, `safety_reason_codes`, `completed_at`)
        VALUES (1, 1, '{"test":true}', 'test', 'test', 'test', 'test', 'SAFE', '[]', '2026-09-08 11:00:00');
        INSERT INTO `recovery_guide_sources` (`id`, `recovery_guide_id`, `source_type`, `patient_source_kind`, `care_advice_id`, `citation_order`)
        VALUES (1, 1, 'PATIENT_SAVED_FIELD', 'CARE_ADVICE', 1, 1);
        INSERT INTO `chat_sessions` (`id`, `user_id`, `care_episode_id`) VALUES (1, 1, 1);
        INSERT INTO `chat_messages` (`id`, `chat_session_id`, `guide_id`, `sequence_no`, `role`, `content`, `started_at`)
        VALUES (1, 1, 1, 1, 'ASSISTANT', '테스트 답변', '2026-09-08 10:00:00');
        INSERT INTO `chat_message_sources` (`id`, `chat_message_id`, `source_type`, `patient_source_kind`, `care_advice_id`, `citation_order`)
        VALUES (1, 1, 'PATIENT_SAVED_FIELD', 'CARE_ADVICE', 1, 1);
        INSERT INTO `chat_message_sources` (`id`, `chat_message_id`, `source_type`, `patient_source_kind`, `patient_field`, `care_episode_id`, `citation_order`) VALUES
          (2, 1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', 'DIAGNOSIS', 1, 2),
          (3, 1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', 'SURGERY', 1, 3),
          (4, 1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', 'DISCHARGE_DATE', 1, 4),
          (5, 1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', 'MEDICATION_DAYS', 1, 5);
        INSERT INTO `alarms` (`id`, `user_id`, `care_episode_id`, `source_guide_id`, `alarm_type`, `title`, `scheduled_at`, `next_trigger_at`)
        VALUES (1, 1, 1, 1, 'GUIDE_CHECK', '알람 제목 보존', '2026-09-08 10:00:00', '2026-09-08 10:00:00');
    """)
    await db.execute_query("UPDATE care_episodes SET hospital_name = %s WHERE id = 1", [long_hospital])
    before_episodes = await db.execute_query_dict(
        "SELECT id, completed_at, hospital_name FROM care_episodes ORDER BY id"
    )
    before_sources = await db.execute_query_dict("SELECT * FROM chat_message_sources WHERE id <= 4 ORDER BY id")

    # A stale backup must prevent writes to application tables, not be overwritten.
    await db.execute_script("CREATE TABLE _m39_backup_care_episode_removed (id BIGINT PRIMARY KEY)")
    with pytest.raises(OperationalError):
        await db.execute_script(await migration.upgrade(db))
    assert (
        await db.execute_query_dict("SELECT id, completed_at, hospital_name FROM care_episodes ORDER BY id")
        == before_episodes
    )
    assert len(await db.execute_query_dict("SELECT * FROM care_advices")) == 1
    await db.execute_script("DROP TABLE _m39_backup_care_episode_removed")

    await db.execute_script(await migration.upgrade(db))
    await db.execute_query(
        "INSERT INTO aerich (version, app, content) VALUES (%s, 'models', '{}')", [MIGRATION_NAME + ".py"]
    )
    aliases = await db.execute_query_dict("SELECT alias FROM care_episodes ORDER BY id")
    assert [row["alias"] for row in aliases] == [long_hospital, "사용자 별칭", "기본 병원", None, None]
    assert (
        await db.execute_query_dict("SELECT id, completed_at, hospital_name FROM care_episodes ORDER BY id")
        == before_episodes
    )
    assert (
        await db.execute_query_dict("SELECT * FROM _m39_backup_chat_message_sources_removed ORDER BY id")
        == before_sources
    )
    assert [row["id"] for row in await db.execute_query_dict("SELECT id FROM chat_message_sources")] == [5]
    expected_counts = {
        "care_episode_removed": 5,
        "care_advices": 1,
        "recovery_guides": 1,
        "recovery_guide_sources": 1,
        "chat_message_sources_removed": 4,
        "chat_message_guide": 1,
        "alarm_source_guide": 1,
    }
    for table, expected in expected_counts.items():
        assert (await db.execute_query_dict(f"SELECT COUNT(*) AS n FROM `_m39_backup_{table}`"))[0]["n"] == expected
    assert (await db.execute_query_dict("SELECT alias FROM _m39_backup_care_episode_removed WHERE id=2"))[0][
        "alias"
    ] == "  사용자 별칭  "
    assert (await db.execute_query_dict("SELECT guide_id FROM _m39_backup_chat_message_guide"))[0]["guide_id"] == 1
    assert (await db.execute_query_dict("SELECT source_guide_id FROM _m39_backup_alarm_source_guide"))[0][
        "source_guide_id"
    ] == 1
    assert (await db.execute_query_dict("SELECT title FROM alarms"))[0]["title"] == "알람 제목 보존"
    assert (await db.execute_query_dict("SELECT started_at FROM chat_messages"))[0]["started_at"] is not None

    tables = {
        row["TABLE_NAME"]
        for row in await db.execute_query_dict(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()"
        )
    }
    assert {"care_advices", "recovery_guides", "recovery_guide_sources"}.isdisjoint(tables)
    columns = {
        row["COLUMN_NAME"]
        for row in await db.execute_query_dict(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='care_episodes'"
        )
    }
    assert {
        "title",
        "diagnosis",
        "surgery",
        "discharge_date",
        "started_at",
        "default_end_at",
        "planned_end_at",
    }.isdisjoint(columns)
    assert {"completed_at", "created_at", "updated_at", "medication_start_date", "medication_start_slot"} <= columns
    for patient_field in ("DIAGNOSIS", "SURGERY", "DISCHARGE_DATE", None):
        with pytest.raises(OperationalError):
            await db.execute_query(
                "INSERT INTO chat_message_sources (chat_message_id, source_type, patient_source_kind, patient_field, care_episode_id, citation_order) VALUES (1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', %s, 1, 6)",
                [patient_field],
            )
    await db.execute_script(
        "INSERT INTO chat_message_sources (chat_message_id, source_type, patient_source_kind, patient_field, care_episode_id, citation_order) VALUES (1, 'PATIENT_SAVED_FIELD', 'CARE_EPISODE_FIELD', 'MEDICATION_DAYS', 1, 6)"
    )
    before_history = await db.execute_query_dict("SELECT id, version FROM aerich ORDER BY id")
    with pytest.raises(RuntimeError, match="intentionally irreversible"):
        await migration.downgrade(db)
    assert await db.execute_query_dict("SELECT id, version FROM aerich ORDER BY id") == before_history
    assert await db.execute_query_dict("SELECT alias FROM care_episodes ORDER BY id") == aliases
