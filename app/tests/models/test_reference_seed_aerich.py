from importlib import import_module
from pathlib import Path

import pytest
from aerich.utils import decompress_dict

from app.core.db.reference_seed import validate_seed_artifacts

MIGRATION = "app.core.db.migrations.models.43_20260909193000_upsert_reference_seed_v1"
PREVIOUS = "app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads"
ROOT = Path(__file__).resolve().parents[3]


def test_reference_seed_migration_keeps_model_state_and_safe_downgrade() -> None:
    migration = import_module(MIGRATION)
    previous = import_module(PREVIOUS)

    assert decompress_dict(migration.MODELS_STATE) == decompress_dict(previous.MODELS_STATE)


@pytest.mark.asyncio
async def test_reference_seed_migration_downgrade_does_not_delete_data() -> None:
    migration = import_module(MIGRATION)

    assert await migration.downgrade(None) == "SELECT 1;"


def test_reference_seed_v1_matches_migration_contract() -> None:
    manifest = validate_seed_artifacts(ROOT / "data" / "reference_seed" / "v1")

    assert manifest.version == "v1"
    assert manifest.schema_head == "42_20260909180000_merge_challenge_schema_heads.py"
    assert len(manifest.tables) == 19
