from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest
from aerich.utils import decompress_dict

MIGRATION_DIR = Path(__file__).resolve().parents[2] / "app" / "core" / "db" / "migrations" / "models"
NUTRIENT_MIGRATION = MIGRATION_DIR / "6_20260825155701_add_nutrient_standard.py"
OCR_MIGRATION = MIGRATION_DIR / "7_20260825114656_async_medication_ocr.py"


def load_migration(path: Path) -> ModuleType:
    spec = spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_async_ocr_migration_follows_nutrient_standard_and_captures_merged_models() -> None:
    assert NUTRIENT_MIGRATION.is_file()
    assert OCR_MIGRATION.is_file()
    assert not (MIGRATION_DIR / "6_20260825114656_async_medication_ocr.py").exists()

    # Historical snapshots describe this migration's result, not future app models.
    migration_state = decompress_dict(load_migration(OCR_MIGRATION).MODELS_STATE)
    assert "models.NutrientStandard" in migration_state
    job = migration_state["models.OcrJob"]
    assert job["table"] == "ocr_jobs"
    assert job["unique_together"] == [
        ["user", "idempotency_key"],
        ["id", "care_episode"],
    ]
    assert job["indexes"] == [["care_episode", "status"], ["expires_at"]]
    fields = {field["name"]: field for field in job["data_fields"]}
    assert fields["structured_result"]["nullable"] is True
    assert fields["structuring_model"]["nullable"] is False
    assert fields["prompt_version"]["nullable"] is False
    foreign_keys = {field["name"]: field for field in job["fk_fields"]}
    assert foreign_keys["user"]["python_type"] == "models.User"
    assert foreign_keys["user"]["nullable"] is False
    assert foreign_keys["user"]["on_delete"] == "CASCADE"
    assert foreign_keys["care_episode"]["python_type"] == "models.CareEpisode"
    assert foreign_keys["care_episode"]["nullable"] is True
    assert foreign_keys["care_episode"]["on_delete"] == "SET NULL"


@pytest.mark.asyncio
async def test_async_ocr_upgrade_backfills_ownership_before_enforcing_user_constraint() -> None:
    sql = await load_migration(OCR_MIGRATION).upgrade(None)
    assert sql.index("UPDATE `ocr_jobs`") < sql.index("MODIFY COLUMN `user_id` BIGINT NOT NULL")
    assert "ON DELETE CASCADE" in sql
    assert "ON DELETE SET NULL" in sql
    assert "ADD UNIQUE INDEX `uid_ocr_jobs_user_id_825f43` (`user_id`, `idempotency_key`)" in sql
    assert sql.index("WHERE `ranked`.`duplicate_rank` > 1") < sql.index("ADD UNIQUE INDEX")
