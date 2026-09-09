import re
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION = "app.core.db.migrations.models.40_20260908160000_custom_challenge_participations"
NEW_MODELS = {
    "models.CustomChallengeParticipation",
    "models.CustomChallengeTarget",
    "models.CustomChallengeOccurrence",
}


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS `{table}` \((.*?)\) CHARACTER SET utf8mb4;",
        sql,
        flags=re.DOTALL,
    )
    assert match is not None, table
    return match.group(1)


def _columns(sql: str, table: str) -> list[str]:
    return re.findall(r"^\s*`([^`]+)`\s", _table_body(sql, table), flags=re.MULTILINE)


async def test_upgrade_creates_only_the_three_approved_tables_with_exact_columns() -> None:
    upgrade_sql = await import_module(MIGRATION).upgrade(None)

    assert re.findall(r"CREATE TABLE IF NOT EXISTS `([^`]+)`", upgrade_sql) == [
        "custom_challenge_participations",
        "custom_challenge_targets",
        "custom_challenge_occurrences",
    ]
    assert _columns(upgrade_sql, "custom_challenge_participations") == [
        "id",
        "user_id",
        "template_id",
        "challenge_type",
        "challenge_name",
        "idempotency_key",
        "joined_at",
        "end_at",
        "status",
    ]
    assert _columns(upgrade_sql, "custom_challenge_targets") == [
        "id",
        "participation_id",
        "care_episode_id",
        "supplement_registration_id",
        "follow_up_visit_id",
        "source_id_snapshot",
        "target_name_snapshot",
    ]
    assert _columns(upgrade_sql, "custom_challenge_occurrences") == [
        "id",
        "target_id",
        "scheduled_date",
        "slot",
        "scheduled_at",
    ]
    assert "ALTER TABLE" not in upgrade_sql
    assert "DROP TABLE" not in upgrade_sql


async def test_upgrade_declares_required_indexes_checks_and_fk_delete_policies() -> None:
    upgrade_sql = await import_module(MIGRATION).upgrade(None)

    for clause in (
        "UNIQUE KEY `uq_custom_participation_request` (`user_id`, `idempotency_key`)",
        "UNIQUE KEY `uq_custom_target_source` (`participation_id`, `source_id_snapshot`)",
        "UNIQUE KEY `uq_custom_occurrence_slot` (`target_id`, `scheduled_date`, `slot`)",
        "KEY `idx_custom_participation_user_status` (`user_id`, `status`, `joined_at`)",
        "KEY `idx_custom_participation_template` (`template_id`)",
        "KEY `idx_custom_participation_end_at` (`end_at`)",
        "KEY `idx_custom_target_care_episode` (`care_episode_id`)",
        "KEY `idx_custom_target_supplement_registration` (`supplement_registration_id`)",
        "KEY `idx_custom_target_follow_up_visit` (`follow_up_visit_id`)",
        "KEY `idx_custom_occurrence_schedule` (`target_id`, `scheduled_at`)",
        "CHECK (`end_at` > `joined_at`)",
        "FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE",
        "FOREIGN KEY (`template_id`) REFERENCES `custom_challenge_templates` (`id`) ON DELETE RESTRICT",
        "FOREIGN KEY (`participation_id`) REFERENCES `custom_challenge_participations` (`id`) ON DELETE CASCADE",
        "FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE SET NULL",
        "FOREIGN KEY (`supplement_registration_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE SET NULL",
        "FOREIGN KEY (`follow_up_visit_id`) REFERENCES `follow_up_visits` (`id`) ON DELETE SET NULL",
        "FOREIGN KEY (`target_id`) REFERENCES `custom_challenge_targets` (`id`) ON DELETE CASCADE",
    ):
        assert clause in upgrade_sql


async def test_migration_excludes_superseded_draft_fields_and_downgrades_child_first() -> None:
    migration = import_module(MIGRATION)
    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    for old_field in (
        "target_type",
        "window_end_at",
        "completed_at",
        "cancelled_at",
        "target_count",
        "completed_count",
        "progress_rate",
        "dose_id",
        "is_taken",
        "created_at",
        "updated_at",
    ):
        assert f"`{old_field}`" not in upgrade_sql
    assert re.findall(r"DROP TABLE IF EXISTS `([^`]+)`", downgrade_sql) == [
        "custom_challenge_occurrences",
        "custom_challenge_targets",
        "custom_challenge_participations",
    ]


def test_merge_migration_42_preserves_custom_models_and_matches_registered_metadata() -> None:
    current = decompress_dict(
        import_module("app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads").MODELS_STATE
    )

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    live = decompress_dict(compress_dict(get_models_describe("models")))

    assert len(current) == 54
    assert current == live
    assert {
        "models.CareAdvice",
        "models.RecoveryGuide",
        "models.RecoveryGuideSource",
    }.isdisjoint(current)

    expected_columns = {
        "models.CustomChallengeParticipation": {
            "id",
            "user_id",
            "template_id",
            "challenge_type",
            "challenge_name",
            "idempotency_key",
            "joined_at",
            "end_at",
            "status",
        },
        "models.CustomChallengeTarget": {
            "id",
            "participation_id",
            "care_episode_id",
            "supplement_registration_id",
            "follow_up_visit_id",
            "source_id_snapshot",
            "target_name_snapshot",
        },
        "models.CustomChallengeOccurrence": {
            "id",
            "target_id",
            "scheduled_date",
            "slot",
            "scheduled_at",
        },
    }
    for model_name, columns in expected_columns.items():
        model = current[model_name]
        state_columns = {model["pk_field"]["db_column"]}
        state_columns.update(field["db_column"] for field in model["data_fields"])
        assert state_columns == columns
