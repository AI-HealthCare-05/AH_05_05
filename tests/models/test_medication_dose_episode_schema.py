from importlib import import_module

from aerich.utils import decompress_dict
from tortoise import Tortoise, fields

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION_NAME = "29_20260905164657_dose_care_episode"


def test_medication_dose_is_owned_by_an_episode() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    dose = import_module("app.models.medications").MedicationDose

    care_episode = dose._meta.fields_map["care_episode"]
    assert care_episode.null is False
    assert care_episode.on_delete == fields.CASCADE
    assert dose._meta.unique_together == (("user", "dose_date", "slot", "care_episode"),)
    assert ("user", "dose_date") in dose._meta.indexes
    assert ("care_episode", "dose_date") in dose._meta.indexes


async def test_migration_replaces_slot_unique_with_episode_unique_after_deleting_old_rows() -> None:
    migration = import_module(f"app.core.db.migrations.models.{MIGRATION_NAME}")
    upgrade = " ".join((await migration.upgrade(None)).split())
    downgrade = " ".join((await migration.downgrade(None)).split())

    delete_position = upgrade.index("DELETE FROM `medication_doses`")
    column_position = upgrade.index("ADD `care_episode_id` BIGINT NOT NULL")
    old_unique_position = upgrade.index("DROP INDEX `uid_medication__user_dose_slot`")
    new_unique_position = upgrade.index("ADD UNIQUE INDEX `uid_dose_user_date_slot_ep`")
    foreign_key_position = upgrade.index("ADD CONSTRAINT `fk_dose_care_episode`")
    episode_index_position = upgrade.index("ADD INDEX `idx_dose_episode_date`")

    assert delete_position < column_position < old_unique_position < new_unique_position
    assert new_unique_position < foreign_key_position < episode_index_position
    assert "(`user_id`, `dose_date`, `slot`, `care_episode_id`)" in upgrade
    assert "REFERENCES `care_episodes` (`id`) ON DELETE CASCADE" in upgrade
    assert "(`care_episode_id`, `dose_date`)" in upgrade
    assert "DROP COLUMN `care_episode_id`" in downgrade
    assert "ADD UNIQUE" not in downgrade


async def test_downgrade_allows_same_slot_rows_from_multiple_episodes_to_remain() -> None:
    migration = import_module(f"app.core.db.migrations.models.{MIGRATION_NAME}")
    downgrade = " ".join((await migration.downgrade(None)).split())
    rows = [
        (1, "2026-09-05", "MORNING", 10),
        (1, "2026-09-05", "MORNING", 20),
    ]
    projected_slot_keys = [(user_id, dose_date, slot) for user_id, dose_date, slot, _ in rows]

    assert len(projected_slot_keys) > len(set(projected_slot_keys))
    assert "DROP COLUMN `care_episode_id`" in downgrade
    assert "ADD UNIQUE" not in downgrade


def test_migration_state_keeps_episode_relation_required() -> None:
    migration = import_module(f"app.core.db.migrations.models.{MIGRATION_NAME}")
    state = decompress_dict(migration.MODELS_STATE)
    fields_by_name = {field["name"]: field for field in state["models.MedicationDose"]["fk_fields"]}

    assert fields_by_name["care_episode"]["nullable"] is False
    assert fields_by_name["care_episode"]["on_delete"] == "CASCADE"
