from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS

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

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    current_state = decompress_dict(compress_dict(get_models_describe("models")))
    migration_state = decompress_dict(load_migration(OCR_MIGRATION).MODELS_STATE)

    assert migration_state == current_state
    assert "models.NutrientStandard" in migration_state
    assert migration_state["models.OcrJob"]["unique_together"] == [
        ["user", "idempotency_key"],
        ["id", "care_episode"],
    ]
