"""Converge the immutable classification and custom-challenge schema heads."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """Both parent branches already applied their schema; only merge ledger state."""
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Keep all parent tables and data intact when reverting this state merge."""
    return "SELECT 1;"


_state = deepcopy(
    decompress_dict(
        import_module(
            "app.core.db.migrations.models.44_20260910093000_merge_therapeutic_classification_heads"
        ).MODELS_STATE
    )
)
_custom_state = decompress_dict(
    import_module("app.core.db.migrations.models.43_20260910000000_custom_challenge_finalization").MODELS_STATE
)
for _model_name in (
    "models.User",
    "models.Badge",
    "models.CustomChallengeParticipation",
    "models.CustomChallengeOccurrence",
    "models.CustomChallengeBadgeAward",
):
    _state[_model_name] = deepcopy(_custom_state[_model_name])

MODELS_STATE = compress_dict(_state)
