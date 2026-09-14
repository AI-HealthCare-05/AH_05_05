"""Merge concurrent email-task and medication-cleanup migration heads."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Both parent migrations already applied their schema changes."""
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Revert only the ledger merge while preserving both parent schemas."""
    return "SELECT 1;"


_state = deepcopy(
    decompress_dict(
        import_module("app.core.db.migrations.models.46_20260914000000_email_background_tasks").MODELS_STATE
    )
)
_medication_state = decompress_dict(
    import_module("app.core.db.migrations.models.46_20260914000000_remove_medication_legacy_fields").MODELS_STATE
)
_state["models.Medication"] = deepcopy(_medication_state["models.Medication"])

MODELS_STATE = compress_dict(_state)
