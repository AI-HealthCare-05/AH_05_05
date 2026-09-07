from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "core"
    / "db"
    / "migrations"
    / "models"
    / "21_20260901213827_ocr_v3_storage.py"
)


def load_migration():
    spec = spec_from_file_location(MIGRATION_PATH.stem, MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_captures_its_ocr_v3_storage_contract() -> None:
    # Do not rewrite migration 21 to include models introduced by later migrations.
    migration_state = decompress_dict(load_migration().MODELS_STATE)
    job = migration_state["models.OcrJob"]
    assert job["table"] == "ocr_jobs"
    fields = {field["name"]: field for field in job["data_fields"]}
    for name, sql_type in {
        "structuring_model": "VARCHAR(100)",
        "prompt_version": "VARCHAR(100)",
        "stage_results": "JSON",
        "avg_field_confidence": "DECIMAL(5,4)",
        "confidence_field_count": "INT",
        "user_review_match_rate": "DECIMAL(5,4)",
    }.items():
        assert fields[name]["nullable"] is True, name
        assert fields[name]["db_field_types"][""] == sql_type, name
    medication = {field["name"]: field for field in migration_state["models.Medication"]["data_fields"]}
    assert "dose" not in medication
    for name, max_length in (("strength", 100), ("dose_quantity", 50)):
        assert medication[name]["nullable"] is True
        assert medication[name]["constraints"]["max_length"] == max_length


def _storage_contract(model: dict) -> dict:
    """Ignore documentation, declaration order and reverse ORM-only relations."""
    return {
        "table": model["table"],
        "unique_together": sorted(map(tuple, model["unique_together"])),
        "indexes": sorted(map(tuple, model["indexes"])),
        "fields": {
            field["name"]: {key: value for key, value in field.items() if key not in {"description", "docstring"}}
            for field in [model["pk_field"], *model["data_fields"], *model["fk_fields"], *model["o2o_fields"]]
        },
    }


@pytest.mark.parametrize("model_name", ["models.OcrJob", "models.Medication", "models.CareEpisode"])
def test_latest_migration_matches_current_ocr_storage_models(model_name: str) -> None:
    latest = max(
        MIGRATION_PATH.parent.glob("[0-9]*_*.py"), key=lambda path: (int(path.name.split("_", 1)[0]), path.name)
    )
    spec = spec_from_file_location(latest.stem, latest)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    migrated = decompress_dict(module.MODELS_STATE)
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    current = decompress_dict(compress_dict(get_models_describe("models")))

    assert _storage_contract(migrated[model_name]) == _storage_contract(current[model_name])


@pytest.mark.asyncio
async def test_upgrade_preserves_legacy_dose_and_adds_only_ocr_v3_columns() -> None:
    assert MIGRATION_PATH.is_file()

    sql = await load_migration().upgrade(None)

    assert "DROP CHECK `chk_medication_as_needed_note`" in sql
    assert "CHANGE COLUMN `dose` `strength` VARCHAR(100) NULL" in sql
    assert "ADD `dose_quantity` VARCHAR(50) NULL" in sql
    assert "ADD `dose_unit`" not in sql
    assert "ADD `stage_results` JSON NULL" in sql
    assert "ADD `avg_field_confidence` DECIMAL(5,4) NULL" in sql
    assert "ADD `confidence_field_count` INT NULL" in sql
    assert "ADD `user_review_match_rate` DECIMAL(5,4) NULL" in sql
    assert "MODIFY COLUMN `structuring_model` VARCHAR(100) NULL" in sql
    assert "MODIFY COLUMN `prompt_version` VARCHAR(100) NULL" in sql
    assert "chk_medication_dose_quantity" not in sql
    assert "chk_ocr_avg_field_confidence" in sql
    assert "chk_ocr_confidence_field_count" in sql
    assert "chk_ocr_user_review_match_rate" in sql
    assert "target_field_count" not in sql
    assert "DROP COLUMN `dose`" not in sql


@pytest.mark.asyncio
async def test_downgrade_restores_legacy_contract_without_discarding_strength() -> None:
    sql = await load_migration().downgrade(None)

    assert "ADD CONSTRAINT `chk_medication_as_needed_note`" in sql
    assert "CHANGE COLUMN `strength` `dose` VARCHAR(100) NULL" in sql
    assert "DROP COLUMN `dose_quantity`" in sql
    assert "DROP COLUMN `dose_unit`" not in sql
    assert "DROP COLUMN `stage_results`" in sql
    assert "DROP COLUMN `avg_field_confidence`" in sql
    assert "DROP COLUMN `confidence_field_count`" in sql
    assert "DROP COLUMN `user_review_match_rate`" in sql
    assert "MODIFY COLUMN `structuring_model` VARCHAR(100) NOT NULL" in sql
    assert "MODIFY COLUMN `prompt_version` VARCHAR(100) NOT NULL" in sql
