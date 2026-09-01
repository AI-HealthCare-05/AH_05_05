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


def test_migration_captures_current_ocr_v3_model_state() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")

    current_state = decompress_dict(compress_dict(get_models_describe("models")))
    migration_state = decompress_dict(load_migration().MODELS_STATE)

    assert migration_state == current_state


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
