import importlib
from pathlib import Path

from app.models.challenges import CustomChallengeTemplate

MIGRATION_ROOT = Path(__file__).resolve().parents[2] / "core/db/migrations/models"


async def test_challenge_migration_creates_six_tables_and_integrity_constraints() -> None:
    migration = importlib.import_module("app.core.db.migrations.models.32_20260907185920_add_challenge_domain")

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    for table in (
        "badges",
        "challenges",
        "user_challenges",
        "challenge_progress",
        "challenge_verifications",
        "user_badges",
    ):
        assert f"CREATE TABLE IF NOT EXISTS `{table}`" in upgrade_sql
        assert f"DROP TABLE IF EXISTS `{table}`" in downgrade_sql

    assert "uq_user_challenges_user_challenge" in upgrade_sql
    assert "uq_challenge_progress_period" in upgrade_sql
    assert "uq_user_badges_participation_badge" in upgrade_sql
    assert "chk_challenges_recruit_period" in upgrade_sql
    assert "chk_user_challenges_progress_rate" in upgrade_sql
    assert "chk_challenge_progress_progress_rate" in upgrade_sql


def test_challenge_common_code_seed_migration_contains_required_codes() -> None:
    migrations = list(MIGRATION_ROOT.glob("33_*_seed_challenge_common_codes.py"))
    assert len(migrations) == 1
    source = migrations[0].read_text(encoding="utf-8")

    for group_code in ("CHL_TYPE", "CHL_PERIOD", "CHK_TYPE", "CHK_FREQ"):
        assert group_code in source
    assert "'CHL'" in source
    for detail_code in (
        "T01",
        "T02",
        "T03",
        "D7",
        "D14",
        "D30",
        "SELF",
        "MANUAL",
        "DAILY",
        "WEEKLY_3",
        "TOTAL_10",
    ):
        assert detail_code in source


def test_custom_challenge_default_seed_migration_contains_required_defaults() -> None:
    migrations = list(MIGRATION_ROOT.glob("38_*_seed_custom_challenge_defaults.py"))
    assert len(migrations) == 1
    source = migrations[0].read_text(encoding="utf-8")

    for token in (
        "CHK_TYPE2",
        "AUTO",
        "복약 챌린지",
        "영양제 챌린지",
        "다음 진료 챌린지",
        "물마시기 배지",
        "스트레칭 배지",
        "걷기 배지",
        "media/badges/walking-badge.png",
        "_migration_38_custom_challenge_default_seed",
        "MODELS_STATE",
    ):
        assert token in source


async def test_challenge_metadata_migration_uses_mysql_safe_noop() -> None:
    migration = importlib.import_module(
        "app.core.db.migrations.models.34_20260907193837_sync_challenge_common_code_metadata"
    )

    assert "SELECT 1;" in await migration.upgrade(None)
    assert "SELECT 1;" in await migration.downgrade(None)


async def test_custom_challenge_check_type_group_rename_migration_is_reversible() -> None:
    migrations = list(MIGRATION_ROOT.glob("40_*_rename_custom_challenge_check_type_group.py"))
    assert len(migrations) == 1
    migration = importlib.import_module(f"app.core.db.migrations.models.{migrations[0].stem}")

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert "`group_code` = 'CST_CHK_TYPE'" in upgrade_sql
    assert "`group_code` = 'CHK_TYPE2'" in downgrade_sql


def test_custom_challenge_template_references_the_custom_check_type_group() -> None:
    description = CustomChallengeTemplate._meta.fields_map["check_type"].description

    assert description == "인증 방식 공통코드 ID(CHL/CST_CHK_TYPE)"


async def test_custom_challenge_and_badge_type_migration_adds_reversible_foreign_keys() -> None:
    migrations = list(MIGRATION_ROOT.glob("41_*_add_custom_challenge_and_badge_types.py"))
    assert len(migrations) == 1
    migration = importlib.import_module(f"app.core.db.migrations.models.{migrations[0].stem}")

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    for column in ("`challenge_type`", "`reward_badge_id`", "`type`"):
        assert column in upgrade_sql
        assert column in downgrade_sql
    assert "REFERENCES `common_codes` (`id`)" in upgrade_sql
    assert "REFERENCES `badges` (`id`)" in upgrade_sql
