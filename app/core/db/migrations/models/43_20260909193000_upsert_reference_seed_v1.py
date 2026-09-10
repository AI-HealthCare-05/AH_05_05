"""Upsert the immutable active reference-data snapshot v1."""

from importlib import import_module
from pathlib import Path

from tortoise import BaseDBAsyncClient

from app.core.db.reference_seed import apply_reference_seed

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    seed_dir = Path(__file__).resolve().parents[5] / "data" / "reference_seed" / "v1"
    await apply_reference_seed(db, seed_dir)
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Reference rows may already be used by application data, so downgrade is non-destructive.
    return "SELECT 1;"


MODELS_STATE = import_module(
    "app.core.db.migrations.models.42_20260909180000_merge_challenge_schema_heads"
).MODELS_STATE
