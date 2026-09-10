"""Merge therapeutic-classification schema state with the reference-seed head."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    """The parent migrations already create tables and seed reference rows."""
    return "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    """Keep the merge migration reversible without changing parent schema."""
    return "SELECT 1;"


_state = deepcopy(
    decompress_dict(
        import_module("app.core.db.migrations.models.43_20260909193000_upsert_reference_seed_v1").MODELS_STATE
    )
)
_therapeutic_state = decompress_dict(
    import_module("app.core.db.migrations.models.42_20260909220000_add_therapeutic_classifications").MODELS_STATE
)

for _model_name in (
    "models.TherapeuticClass",
    "models.TherapeuticClassAlias",
    "models.InteractionEntityTherapeuticClass",
):
    _state[_model_name] = deepcopy(_therapeutic_state[_model_name])

_existing_relations = {
    relation["name"]: deepcopy(relation) for relation in _state["models.InteractionEntity"]["backward_fk_fields"]
}
_therapeutic_relation = next(
    relation
    for relation in _therapeutic_state["models.InteractionEntity"]["backward_fk_fields"]
    if relation["name"] == "therapeutic_classifications"
)
_existing_relations["therapeutic_classifications"] = deepcopy(_therapeutic_relation)
_state["models.InteractionEntity"]["backward_fk_fields"] = [
    _existing_relations[name]
    for name in (
        "aliases",
        "identifiers",
        "therapeutic_classifications",
        "left_rules",
        "right_rules",
        "medication_mappings",
        "medication_safety_rules",
        "supplement_mappings",
    )
]
_therapeutic_class_relations = {
    relation["name"]: deepcopy(relation) for relation in _state["models.TherapeuticClass"]["backward_fk_fields"]
}
_state["models.TherapeuticClass"]["backward_fk_fields"] = [
    _therapeutic_class_relations[name] for name in ("entity_classifications", "aliases")
]

MODELS_STATE = compress_dict(_state)
