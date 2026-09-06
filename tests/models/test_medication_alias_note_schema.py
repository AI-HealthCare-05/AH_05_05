from importlib import import_module
from pathlib import Path

from aerich.utils import decompress_dict
from tortoise import Tortoise, fields

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "app" / "core" / "db" / "migrations" / "models"
ALIAS_MIGRATION_NAME = "27_20260904230000_add_care_episode_alias"
NOTES_MIGRATION_NAME = "28_20260904230001_add_medication_notes"


def initialize_models() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")


def load_migration(name: str):
    path = MIGRATION_DIR / f"{name}.py"
    assert path.is_file(), f"expected migration file is missing: {path.name}"
    return import_module(f"app.core.db.migrations.models.{name}")


def normalize_sql(sql: str) -> str:
    return " ".join(sql.split())


def load_migration_state(name: str) -> dict:
    return decompress_dict(load_migration(name).MODELS_STATE)


def state_field(state: dict, model_name: str, field_name: str) -> dict:
    fields_by_name = {field["name"]: field for field in state[f"models.{model_name}"]["data_fields"]}
    return fields_by_name[field_name]


def test_care_episode_exposes_an_optional_alias_without_changing_title() -> None:
    initialize_models()

    care_episode = import_module("app.models.care").CareEpisode
    alias = care_episode._meta.fields_map.get("alias")

    assert isinstance(alias, fields.CharField)
    assert alias.max_length == 50
    assert alias.null is True
    assert care_episode._meta.fields_map["title"].null is False


def test_medication_note_model_uses_dosed_at_and_no_ambiguous_slot() -> None:
    initialize_models()

    medications = import_module("app.models.medications")
    assert hasattr(medications, "MedicationNote")

    note = medications.MedicationNote
    assert note._meta.db_table == "medication_notes"
    assert note._meta.fields_map["user"].on_delete == fields.CASCADE
    assert note._meta.fields_map["care_episode"].on_delete == fields.CASCADE
    assert note._meta.fields_map["medication"].on_delete == fields.SET_NULL
    assert note._meta.fields_map["medication"].null is True
    assert note._meta.fields_map["dosed_at"].null is False
    assert note._meta.fields_map["body"].max_length == 500
    assert ("user", "dosed_at") in note._meta.indexes
    assert ("care_episode",) in note._meta.indexes
    assert "slot" not in note._meta.fields_map


async def test_alias_migration_adds_and_removes_only_the_nullable_alias_column() -> None:
    migration = load_migration(ALIAS_MIGRATION_NAME)

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    normalized_upgrade = normalize_sql(upgrade_sql)
    normalized_downgrade = normalize_sql(downgrade_sql)

    assert "ALTER TABLE `care_episodes` ADD `alias` VARCHAR(50) COMMENT '복약 별칭'" in normalized_upgrade
    assert "DROP COLUMN `alias`" in normalized_downgrade
    assert "title" not in normalized_upgrade
    assert "INSERT" not in normalized_upgrade


async def test_medication_notes_migration_keeps_the_explicit_non_slot_contract() -> None:
    migration = load_migration(NOTES_MIGRATION_NAME)

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    normalized_upgrade = normalize_sql(upgrade_sql)
    normalized_downgrade = normalize_sql(downgrade_sql)

    assert "CREATE TABLE IF NOT EXISTS `medication_notes`" in normalized_upgrade
    assert "`body` VARCHAR(500) NOT NULL" in normalized_upgrade
    assert "`dosed_at` DATETIME(6) NOT NULL" in normalized_upgrade
    assert "REFERENCES `user` (`id`) ON DELETE CASCADE" in normalized_upgrade
    assert "REFERENCES `care_episodes` (`id`) ON DELETE CASCADE" in normalized_upgrade
    assert "REFERENCES `medications` (`id`) ON DELETE SET NULL" in normalized_upgrade
    assert "slot" not in normalized_upgrade
    assert "DROP TABLE IF EXISTS `medication_notes`" in normalized_downgrade


def test_migration_states_preserve_model_nullability_contract() -> None:
    alias_state = load_migration_state(ALIAS_MIGRATION_NAME)
    notes_state = load_migration_state(NOTES_MIGRATION_NAME)

    assert state_field(alias_state, "CareEpisode", "alias")["nullable"] is True
    assert state_field(notes_state, "CareEpisode", "alias")["nullable"] is True
    assert state_field(notes_state, "MedicationNote", "dosed_at")["nullable"] is False
