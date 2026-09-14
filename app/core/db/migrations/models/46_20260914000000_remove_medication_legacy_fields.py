"""Permanently remove four legacy columns without creating a backup.

Stop API/workers before applying. Removed values cannot be recovered by this
migration. MySQL DDL is non-transactional; inspect partial failures before retry.
See docs/ocr/medication-legacy-fields-removal-20260914.md for rollout details.
"""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = False


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `medications` DROP COLUMN `efficacy`;
        ALTER TABLE `medications` DROP COLUMN `administration`;
        ALTER TABLE `medications` DROP COLUMN `precautions`;
        ALTER TABLE `medications` DROP COLUMN `note`;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    raise RuntimeError(
        "Migration 46 is intentionally irreversible: removed values are permanently deleted without a backup. "
        "See "
        "docs/ocr/medication-legacy-fields-removal-20260914.md."
    )


_state = deepcopy(
    decompress_dict(
        import_module(
            "app.core.db.migrations.models.45_20260910190000_merge_custom_challenge_finalization_heads"
        ).MODELS_STATE
    )
)
_state["models.Medication"]["data_fields"] = [
    field
    for field in _state["models.Medication"]["data_fields"]
    if field["name"] not in {"efficacy", "administration", "precautions", "note"}
]
MODELS_STATE = compress_dict(_state)
