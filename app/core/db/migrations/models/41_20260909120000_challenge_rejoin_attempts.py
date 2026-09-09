"""#304: preserve cancelled attempts and allow a fresh participation on rejoin."""

from copy import deepcopy
from importlib import import_module
from json import loads

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def _check_applied_snapshot(db: BaseDBAsyncClient) -> None:
    tables = await db.execute_query_dict("""
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'aerich';
    """)
    if not tables:
        return
    applied = await db.execute_query_dict("SELECT content FROM `aerich` WHERE app = 'models' ORDER BY id DESC LIMIT 1;")
    if not applied:
        return
    content = applied[0]["content"]
    previous = loads(content) if isinstance(content, str) else content
    if previous not in (_previous_state, _parallel_state, _state):
        raise RuntimeError(
            "Challenge rejoin migration stopped: integrate the previously applied model snapshot "
            "before upgrading. Expected immutable custom/OCR migration 40 or the reconciled migration 41 snapshot; "
            "model fields, relations and indexes must also match. No schema or history was changed."
        )


async def _participation_indexes(db: BaseDBAsyncClient) -> tuple[list[str], bool]:
    rows = await db.execute_query_dict("SHOW INDEX FROM `user_challenges`;")
    unique_names = []
    has_lookup = False
    for name in sorted({row["Key_name"] for row in rows}):
        index = sorted((row for row in rows if row["Key_name"] == name), key=lambda row: row["Seq_in_index"])
        matching_columns = [row["Column_name"] for row in index] == ["user_id", "challenge_id"] and all(
            row.get("Sub_part") is None for row in index
        )
        unique = all(not row["Non_unique"] for row in index)
        if name == "uq_user_challenges_user_challenge" and not (matching_columns and unique):
            raise RuntimeError("Challenge rejoin migration stopped: unexpected participation unique index definition.")
        if name == "idx_user_challenges_user_challenge":
            if not matching_columns or unique:
                raise RuntimeError(
                    "Challenge rejoin migration stopped: unexpected participation lookup index definition."
                )
            has_lookup = True
        if matching_columns and unique:
            unique_names.append(name)
    return unique_names, has_lookup


async def upgrade(db: BaseDBAsyncClient) -> str:
    await _check_applied_snapshot(db)
    unique_names, has_lookup = await _participation_indexes(db)
    changes = []
    if not has_lookup:
        changes.append("ADD INDEX `idx_user_challenges_user_challenge` (`user_id`, `challenge_id`)")
    # Add a replacement in the same ALTER so even the only FK-supporting key can be removed.
    changes.extend("DROP INDEX `" + name.replace("`", "``") + "`" for name in unique_names)
    return "ALTER TABLE `user_challenges` " + ", ".join(changes) + ";" if changes else "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:
    unique_names, has_lookup = await _participation_indexes(db)
    duplicates = await db.execute_query_dict("""
        SELECT 1 AS duplicate_found FROM `user_challenges`
        GROUP BY `user_id`, `challenge_id` HAVING COUNT(*) > 1 LIMIT 1;
    """)
    if duplicates:
        raise RuntimeError(
            "Challenge rejoin rollback stopped: duplicate attempt histories exist. "
            "No records were deleted. Keep this migration until histories can be retained safely."
        )
    # A concurrent rejoin causes ADD UNIQUE to fail without deleting either attempt.
    changes = []
    if not unique_names:
        changes.append("ADD UNIQUE INDEX `uq_user_challenges_user_challenge` (`user_id`, `challenge_id`)")
    if has_lookup:
        changes.append("DROP INDEX `idx_user_challenges_user_challenge`")
    return "ALTER TABLE `user_challenges` " + ", ".join(changes) + ";" if changes else "SELECT 1;"


# Derive from the immutable preceding snapshot, never from runtime application models.
_previous_state = decompress_dict(
    import_module("app.core.db.migrations.models.40_20260908160000_custom_challenge_participations").MODELS_STATE
)
_parallel_state = decompress_dict(
    import_module("app.core.db.migrations.models.41_20260909000001_add_custom_challenge_and_badge_types").MODELS_STATE
)
_state = deepcopy(_previous_state)
_state["models.UserChallenge"]["unique_together"] = []
_state["models.UserChallenge"]["indexes"].append(
    {
        "fields": ["user_id", "challenge_id"],
        "expressions": [],
        "name": "idx_user_challenges_user_challenge",
        "type": "",
        "extra": "",
    }
)
MODELS_STATE = compress_dict(_state)
