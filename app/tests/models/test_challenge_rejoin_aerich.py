"""Exercise real Aerich upgrades in child processes with freshly named test databases."""

import asyncio
import copy
import subprocess
import sys
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest
from aerich import Command
from aerich.models import Aerich
from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise
from tortoise.backends.mysql.client import MySQLClient

from app.core import config
from app.core.db.databases import TORTOISE_ORM

ROOT = Path(__file__).resolve().parents[3]
VERSION_39 = "39_20260908151829_challenge_daily_verification.py"
VERSION_40_CUSTOM = "40_20260908160000_custom_challenge_participations.py"
VERSION_40_RENAME = "40_20260909000000_rename_custom_challenge_check_type_group.py"
VERSION_40_OCR = "40_20260909143654_allow_ocr_recapture_error_code.py"
VERSION_41_TYPES = "41_20260909000001_add_custom_challenge_and_badge_types.py"
VERSION_41 = "41_20260909120000_challenge_rejoin_attempts.py"
VERSION_42 = "42_20260909180000_merge_challenge_schema_heads.py"
VERSION_42_THERAPEUTIC = "42_20260909220000_add_therapeutic_classifications.py"
VERSION_43 = "43_20260909193000_upsert_reference_seed_v1.py"
VERSION_43_CUSTOM = "43_20260910000000_custom_challenge_finalization.py"
VERSION_44 = "44_20260910093000_merge_therapeutic_classification_heads.py"
VERSION_45 = "45_20260910190000_merge_custom_challenge_finalization_heads.py"
VERSION_46_EMAIL = "46_20260914000000_email_background_tasks.py"
VERSION_46_MEDICATION = "46_20260914000000_remove_medication_legacy_fields.py"
VERSION_46_SESSION_REFERENCES = "46_20260914204559_persist_chat_session_references.py"
VERSION_47 = "47_20260914010000_merge_email_and_medication_heads.py"
VERSION_48 = "48_20260914214228_remove_unused_chat_and_reference_fields.py"
CUSTOM_TABLES = ("custom_challenge_participations", "custom_challenge_targets", "custom_challenge_occurrences")


@pytest.mark.parametrize("start_version", [39, 40])
def test_real_aerich_upgrades_preserve_history_and_match_runtime(start_version: int) -> None:
    # A child owns all Tortoise/Aerich globals, so this test cannot replace the normal CI fixture's pool.
    result = subprocess.run(
        [sys.executable, "-m", "app.tests.models.test_challenge_rejoin_aerich", str(start_version)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def _seed_official_attempt():
    from app.models.challenges import Challenge, ChallengeProgress, ChallengeVerification, UserChallenge
    from app.models.common_codes import CommonCode, CommonCodeGroup
    from app.models.users import User

    now = datetime.now(config.TIMEZONE)
    user = await User.create(email="chain@example.com", hashed_password="unused", name="Migration chain")
    group = await CommonCodeGroup.create(category="CHL", group_code="CHAIN", group_name="Chain")
    codes = {
        code: await CommonCode.create(group=group, detail_code=code, detail_name=code)
        for code in ("WALK", "D7", "SELF", "DAILY")
    }
    challenge = await Challenge.create(
        name="Rejoin after migration",
        phrase="Keep every attempt",
        challenge_type=codes["WALK"],
        challenge_period=codes["D7"],
        check_type=codes["SELF"],
        check_frequency=codes["DAILY"],
        recruit_start_at=now - timedelta(days=1),
        recruit_end_at=now + timedelta(days=1),
        is_displayed=True,
    )
    old = await UserChallenge.create(
        user=user,
        challenge=challenge,
        status="CANCELLED",
        started_at=now - timedelta(days=1),
        end_at=now + timedelta(days=6),
        cancelled_at=now,
        target_count=7,
        completed_count=1,
    )
    progress = await ChallengeProgress.create(
        user_challenge=old,
        period_start=now.date(),
        period_end=now.date(),
        target_count=1,
        completed_count=1,
        is_completed=True,
    )
    verification = await ChallengeVerification.create(
        user_challenge=old,
        progress=progress,
        verification_date=now.date(),
        idempotency_key="preserved-chain-verification",
        status="APPROVED",
    )
    return user, challenge, old, verification, codes["SELF"]


async def _seed_custom_history(user, check_type):
    from app.models.care import CareEpisode
    from app.models.challenges import CustomChallengeTemplate
    from app.models.custom_challenges import CustomChallengeTarget

    now = datetime.now(config.TIMEZONE)
    template = await CustomChallengeTemplate.create(name="Preserved template", check_type=check_type)
    # Seed the real historical columns, not the current ORM's post-43 fields.
    db = Tortoise.get_connection("default")
    custom_id = await db.execute_insert(
        "INSERT INTO custom_challenge_participations "
        "(user_id, template_id, challenge_type, challenge_name, idempotency_key, joined_at, end_at, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        [
            user.id,
            template.id,
            "MEDICATION",
            "Preserved custom history",
            "preserved-custom-request",
            now,
            now + timedelta(days=7),
            "ACTIVE",
        ],
    )
    episode = await CareEpisode.create(user=user)
    target = await CustomChallengeTarget.create(
        participation_id=custom_id,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="Preserved source label",
    )
    await db.execute_insert(
        "INSERT INTO custom_challenge_occurrences (target_id, scheduled_date, slot, scheduled_at) "
        "VALUES (%s, %s, %s, %s)",
        [target.id, now.date(), "MORNING", now],
    )


async def _add_historical_ocr_error_code_check(db, migration) -> None:
    """Restore the named pre-recapture CHECK omitted by Tortoise's generated schema."""
    downgrade_sql = await migration.downgrade(db)
    check_definition = downgrade_sql[downgrade_sql.index("ADD CONSTRAINT") :]
    await db.execute_script("ALTER TABLE `ocr_jobs` " + check_definition)


async def _run_chain(start_version: int) -> None:
    from app.models.challenges import ChallengeVerification, UserChallenge
    from app.services.challenge_participation import ChallengeParticipationService

    database = f"test_rejoin_chain_{uuid4().hex}"
    db_admin = MySQLClient(
        connection_name=database,
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=database,
    )
    await db_admin.db_create()
    await db_admin.close()
    try:
        settings = copy.deepcopy(TORTOISE_ORM)
        settings["connections"]["default"]["credentials"]["database"] = database
        command = Command(settings, app="models", location=str(ROOT / "app/core/db/migrations"))
        await command.init()
        await Tortoise.generate_schemas()
        db = Tortoise.get_connection("default")
        previous_39 = import_module("app.core.db.migrations.models." + VERSION_39[:-3])
        previous_40 = import_module("app.core.db.migrations.models." + VERSION_40_CUSTOM[:-3])
        current_40_ocr = import_module("app.core.db.migrations.models." + VERSION_40_OCR[:-3])
        current_42 = import_module("app.core.db.migrations.models." + VERSION_42[:-3])
        current_46_email = import_module("app.core.db.migrations.models." + VERSION_46_EMAIL[:-3])
        current_48 = import_module("app.core.db.migrations.models." + VERSION_48[:-3])
        # Establish a fresh pre-custom schema from the registered parent models, then exercise actual migrations.
        # All tables are still empty here; this disposable database is the only deletion target.
        await db.execute_script(await current_46_email.downgrade(db))
        await db.execute_script("""
            ALTER TABLE medications
                ADD COLUMN efficacy VARCHAR(500) NULL,
                ADD COLUMN administration VARCHAR(500) NULL,
                ADD COLUMN precautions VARCHAR(500) NULL,
                ADD COLUMN note VARCHAR(500) NULL;
        """)
        # The replay starts before migration 46 added this field.
        await db.execute_script("ALTER TABLE chat_messages DROP COLUMN session_reference;")
        # Migration 48 removes these legacy columns. Recreate the pre-48 schema
        # in this disposable database so the real migration can exercise its drops.
        await db.execute_script("""
            ALTER TABLE chat_messages
                ADD COLUMN verification_status VARCHAR(12) NOT NULL DEFAULT 'NOT_REQUIRED',
                ADD COLUMN conflict_status VARCHAR(22) NOT NULL DEFAULT 'NOT_APPLICABLE';
            ALTER TABLE interaction_entity_aliases
                ADD COLUMN is_preferred BOOL NOT NULL DEFAULT 0;
        """)
        # Migration 17 was already applied before this test's replay window.
        # The current runtime schema no longer has this column after migration 48,
        # but reference-seed migration 43 still reads it during the historical replay.
        await db.execute_script("ALTER TABLE medication_product_guides ADD COLUMN item_image_url LONGTEXT NULL;")
        await db.execute_script("DROP TABLE custom_challenge_badge_awards;")
        await db.execute_script(await previous_40.downgrade(db))
        await _add_historical_ocr_error_code_check(db, current_40_ocr)
        await db.execute_script("""
            ALTER TABLE user_challenges
                ADD UNIQUE INDEX uq_user_challenges_user_challenge (user_id, challenge_id),
                DROP INDEX idx_user_challenges_user_challenge;
        """)
        for filename in await command.history():
            if int(filename.split("_", 1)[0]) < 39:
                await Aerich.create(version=filename, app="models", content={})
        await Aerich.create(version="39_20260908000000_align_erd125_care_episodes.py", app="models", content={})
        await Aerich.create(version=VERSION_39, app="models", content=decompress_dict(previous_39.MODELS_STATE))
        if start_version == 40:
            # Set up the already-applied-40 case through Aerich itself, including its ledger content.
            await command._upgrade(db, VERSION_40_CUSTOM)
        user, challenge, old, verification, check_type = await _seed_official_attempt()
        if start_version == 40:
            await _seed_custom_history(user, check_type)
        history_before = await Aerich.all().order_by("id").values()
        schema_before = (
            {table: await db.execute_query_dict(f"SHOW CREATE TABLE `{table}`") for table in CUSTOM_TABLES}
            if start_version == 40
            else {}
        )
        custom_before = (
            {table: await db.execute_query_dict(f"SELECT * FROM `{table}` ORDER BY id") for table in CUSTOM_TABLES}
            if start_version == 40
            else {}
        )
        expected = [
            *([] if start_version == 40 else [VERSION_40_CUSTOM]),
            VERSION_40_RENAME,
            VERSION_40_OCR,
            VERSION_41_TYPES,
            VERSION_41,
            VERSION_42,
            VERSION_42_THERAPEUTIC,
            VERSION_43,
            VERSION_43_CUSTOM,
            VERSION_44,
            VERSION_45,
            VERSION_46_EMAIL,
            VERSION_46_MEDICATION,
            VERSION_46_SESSION_REFERENCES,
            VERSION_47,
            VERSION_48,
        ]
        actual_heads = await command.heads()
        assert actual_heads == expected, (actual_heads, expected)
        assert await command.upgrade(fake=False) == expected
        assert await command.heads() == []
        assert await command.upgrade(fake=False) == []
        after = await Aerich.all().order_by("id").values()
        assert after[: len(history_before)] == history_before
        assert [row["version"] for row in after[len(history_before) :]] == expected
        final_state = decompress_dict(current_48.MODELS_STATE)
        assert after[-1]["content"] == final_state
        runtime_state = decompress_dict(compress_dict(get_models_describe("models")))
        differing_models = {
            model: (final_state.get(model), runtime_state.get(model))
            for model in final_state.keys() | runtime_state.keys()
            if final_state.get(model) != runtime_state.get(model)
        }
        assert after[-1]["content"] == runtime_state, differing_models

        email_columns = await db.execute_query_dict(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'background_jobs' "
            "AND COLUMN_NAME IN ('encrypted_payload', 'next_attempt_at', 'lease_expires_at')"
        )
        assert {row["COLUMN_NAME"] for row in email_columns} == {
            "encrypted_payload",
            "next_attempt_at",
            "lease_expires_at",
        }
        email_indexes = await db.execute_query_dict(
            "SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'background_jobs' "
            "AND INDEX_NAME IN ('idx_email_job_retry_due', 'idx_email_job_lease')"
        )
        assert {row["INDEX_NAME"] for row in email_indexes} == {
            "idx_email_job_retry_due",
            "idx_email_job_lease",
        }
        removed_medication_columns = await db.execute_query_dict(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'medications' "
            "AND COLUMN_NAME IN ('efficacy', 'administration', 'precautions', 'note')"
        )
        assert removed_medication_columns == []

        reference_counts = {
            "groups": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM common_code_groups "
                "WHERE category = 'CHL' AND group_code IN ('BDG_TYPE', 'CST_CHL_TYPE');"
            ),
            "codes": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM common_codes AS code "
                "JOIN common_code_groups AS code_group ON code_group.id = code.group_id "
                "WHERE code_group.category = 'CHL' "
                "AND code_group.group_code IN ('BDG_TYPE', 'CST_CHL_TYPE');"
            ),
            "badges": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM badges "
                "WHERE name IN ('물마시기 배지', '스트레칭 배지', '걷기 배지', '복약', '영양제', '진료준비');"
            ),
            "templates": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM custom_challenge_templates "
                "WHERE name IN ('복약 챌린지', '영양제 챌린지', '다음 진료 챌린지');"
            ),
        }
        await db.execute_script(await current_42.upgrade(db))
        assert reference_counts == {
            "groups": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM common_code_groups "
                "WHERE category = 'CHL' AND group_code IN ('BDG_TYPE', 'CST_CHL_TYPE');"
            ),
            "codes": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM common_codes AS code "
                "JOIN common_code_groups AS code_group ON code_group.id = code.group_id "
                "WHERE code_group.category = 'CHL' "
                "AND code_group.group_code IN ('BDG_TYPE', 'CST_CHL_TYPE');"
            ),
            "badges": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM badges "
                "WHERE name IN ('물마시기 배지', '스트레칭 배지', '걷기 배지', '복약', '영양제', '진료준비');"
            ),
            "templates": await db.execute_query_dict(
                "SELECT COUNT(*) AS count FROM custom_challenge_templates "
                "WHERE name IN ('복약 챌린지', '영양제 챌린지', '다음 진료 챌린지');"
            ),
        }
        for table in CUSTOM_TABLES:
            rows = await db.execute_query_dict(f"SELECT * FROM `{table}` ORDER BY id")
            if start_version == 40:
                original_columns = custom_before[table][0].keys()
                assert [{key: row[key] for key in original_columns} for row in rows] == custom_before[table]
                if table == "custom_challenge_targets":
                    assert await db.execute_query_dict(f"SHOW CREATE TABLE `{table}`") == schema_before[table]
                elif table == "custom_challenge_participations":
                    assert [(row["target_count"], row["completed_count"], row["finalized_at"]) for row in rows] == [
                        (0, 0, None)
                    ]
                else:
                    assert [row["is_completed"] for row in rows] == [0]
            else:
                assert rows == []
        service = ChallengeParticipationService()
        new = await service.join(user, challenge.id)
        assert new.id != old.id and new.completed_count == 0 and new.verified_dates == []
        assert await ChallengeVerification.filter(id=verification.id, user_challenge_id=old.id).exists()
        assert (await service.get(user, old.id)).status == "CANCELLED"
        assert await db.execute_query_dict("SHOW TABLES LIKE 'custom_challenge_badge_awards'")
        assert await command.downgrade(version=-1, delete=False, fake=False) == [VERSION_48]
        assert await command.downgrade(version=-1, delete=False, fake=False) == [VERSION_47]
        assert await command.downgrade(version=-1, delete=False, fake=False) == [VERSION_46_SESSION_REFERENCES]
        with pytest.raises(RuntimeError, match="intentionally irreversible"):
            await command.downgrade(version=-1, delete=False, fake=False)
        expected_restore = [VERSION_46_SESSION_REFERENCES, VERSION_47, VERSION_48]
        assert await command.heads() == expected_restore
        assert await command.upgrade(fake=False) == expected_restore
        restored = await Aerich.all().order_by("id").values()
        restored_count = len(expected_restore)
        assert restored[:-restored_count] == after[:-restored_count]
        assert [row["version"] for row in restored[-restored_count:]] == expected_restore
        assert [row["content"] for row in restored[-restored_count:]] == [
            row["content"] for row in after[-restored_count:]
        ]
        assert restored[-1]["content"] == final_state
        assert await UserChallenge.filter(user_id=user.id, challenge_id=challenge.id).count() == 2
        print(
            f"ACTUAL_AERICH_{start_version}_TO_48_OK: history, schema, rows, runtime snapshot, rejoin and rollback guard"
        )
    finally:
        await Tortoise.close_connections()
        assert database.startswith("test_rejoin_chain_") and len(database) == len("test_rejoin_chain_") + 32
        await db_admin.db_delete()
        await db_admin.close()


if __name__ == "__main__":
    asyncio.run(_run_chain(int(sys.argv[1])))
