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
VERSION_40_OCR = "40_20260909143654_allow_ocr_recapture_error_code.py"
VERSION_41 = "41_20260909120000_challenge_rejoin_attempts.py"
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
    from app.models.custom_challenges import (
        CustomChallengeOccurrence,
        CustomChallengeParticipation,
        CustomChallengeTarget,
    )

    now = datetime.now(config.TIMEZONE)
    template = await CustomChallengeTemplate.create(name="Preserved template", check_type=check_type)
    custom = await CustomChallengeParticipation.create(
        user=user,
        template=template,
        challenge_type="MEDICATION",
        challenge_name="Preserved custom history",
        idempotency_key="preserved-custom-request",
        end_at=now + timedelta(days=7),
    )
    episode = await CareEpisode.create(user=user)
    target = await CustomChallengeTarget.create(
        participation=custom,
        care_episode=episode,
        source_id_snapshot=episode.id,
        target_name_snapshot="Preserved source label",
    )
    await CustomChallengeOccurrence.create(target=target, scheduled_date=now.date(), slot="MORNING", scheduled_at=now)


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
        current_41 = import_module("app.core.db.migrations.models." + VERSION_41[:-3])
        # Establish a fresh pre-custom schema from the registered parent models, then exercise actual migrations.
        # All tables are still empty here; this disposable database is the only deletion target.
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
        expected = (
            [VERSION_40_OCR, VERSION_41] if start_version == 40 else [VERSION_40_CUSTOM, VERSION_40_OCR, VERSION_41]
        )
        assert await command.heads() == expected
        assert await command.upgrade(fake=False) == expected
        assert await command.heads() == []
        assert await command.upgrade(fake=False) == []
        assert await current_41.upgrade(db) == "SELECT 1;"
        after = await Aerich.all().order_by("id").values()
        assert after[: len(history_before)] == history_before
        assert [row["version"] for row in after[len(history_before) :]] == expected
        final_state = decompress_dict(current_41.MODELS_STATE)
        assert after[-1]["content"] == final_state
        assert after[-1]["content"] == decompress_dict(compress_dict(get_models_describe("models")))
        for table in CUSTOM_TABLES:
            rows = await db.execute_query_dict(f"SELECT * FROM `{table}` ORDER BY id")
            if start_version == 40:
                assert rows == custom_before[table]
                assert await db.execute_query_dict(f"SHOW CREATE TABLE `{table}`") == schema_before[table]
            else:
                assert rows == []
        service = ChallengeParticipationService()
        new = await service.join(user, challenge.id)
        assert new.id != old.id and new.completed_count == 0 and new.verified_dates == []
        assert await ChallengeVerification.filter(id=verification.id, user_challenge_id=old.id).exists()
        assert (await service.get(user, old.id)).status == "CANCELLED"
        with pytest.raises(RuntimeError, match="duplicate"):
            await command.downgrade(version=-1, delete=False, fake=False)
        assert await Aerich.all().order_by("id").values() == after
        assert await UserChallenge.filter(user_id=user.id, challenge_id=challenge.id).count() == 2
        print(
            f"ACTUAL_AERICH_{start_version}_TO_41_OK: history, schema, rows, runtime snapshot, rejoin and rollback guard"
        )
    finally:
        await Tortoise.close_connections()
        assert database.startswith("test_rejoin_chain_") and len(database) == len("test_rejoin_chain_") + 32
        await db_admin.db_delete()
        await db_admin.close()


if __name__ == "__main__":
    asyncio.run(_run_chain(int(sys.argv[1])))
