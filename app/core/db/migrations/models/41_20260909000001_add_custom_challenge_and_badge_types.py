"""Add common-code types and a reward badge to custom challenge templates."""

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def _schema_names(
    db: BaseDBAsyncClient,
    table: str,
    schema_table: str,
    name_column: str,
) -> set[str]:
    rows = await db.execute_query_dict(
        f"SELECT `{name_column}` AS `name` FROM information_schema.`{schema_table}` "
        f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{table}';"
    )
    return {str(row["name"]) for row in rows}


def _alter(table: str, changes: list[str]) -> str:
    return f"ALTER TABLE `{table}` " + ", ".join(changes) + ";" if changes else ""


async def upgrade(db: BaseDBAsyncClient) -> str:  # noqa: C901 - idempotent DDL needs per-object checks
    if db is None:
        badge_columns = badge_indexes = badge_constraints = set()
        template_columns = template_indexes = template_constraints = set()
    else:
        badge_columns = await _schema_names(db, "badges", "COLUMNS", "COLUMN_NAME")
        badge_indexes = await _schema_names(db, "badges", "STATISTICS", "INDEX_NAME")
        badge_constraints = await _schema_names(db, "badges", "TABLE_CONSTRAINTS", "CONSTRAINT_NAME")
        template_columns = await _schema_names(db, "custom_challenge_templates", "COLUMNS", "COLUMN_NAME")
        template_indexes = await _schema_names(db, "custom_challenge_templates", "STATISTICS", "INDEX_NAME")
        template_constraints = await _schema_names(
            db,
            "custom_challenge_templates",
            "TABLE_CONSTRAINTS",
            "CONSTRAINT_NAME",
        )

    badge_changes = []
    if "type" not in badge_columns:
        badge_changes.append("ADD COLUMN `type` BIGINT NULL COMMENT '배지 유형 공통코드 ID(CHL/BDG_TYPE)'")
    if "idx_badges_type" not in badge_indexes:
        badge_changes.append("ADD INDEX `idx_badges_type` (`type`)")
    if "fk_badges_type_common_code" not in badge_constraints:
        badge_changes.append(
            "ADD CONSTRAINT `fk_badges_type_common_code` "
            "FOREIGN KEY (`type`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT"
        )

    template_changes = []
    if "challenge_type" not in template_columns:
        template_changes.append(
            "ADD COLUMN `challenge_type` BIGINT NULL COMMENT '맞춤 챌린지 유형 공통코드 ID(CHL/CST_CHL_TYPE)'"
        )
    if "reward_badge_id" not in template_columns:
        template_changes.append("ADD COLUMN `reward_badge_id` BIGINT NULL COMMENT '맞춤 챌린지 완료 시 지급할 배지 ID'")
    if "idx_custom_challenge_templates_challenge_type" not in template_indexes:
        template_changes.append("ADD INDEX `idx_custom_challenge_templates_challenge_type` (`challenge_type`)")
    if "idx_custom_challenge_templates_reward_badge" not in template_indexes:
        template_changes.append("ADD INDEX `idx_custom_challenge_templates_reward_badge` (`reward_badge_id`)")
    if "fk_custom_templates_challenge_type" not in template_constraints:
        template_changes.append(
            "ADD CONSTRAINT `fk_custom_templates_challenge_type` "
            "FOREIGN KEY (`challenge_type`) REFERENCES `common_codes` (`id`) ON DELETE RESTRICT"
        )
    if "fk_custom_templates_reward_badge" not in template_constraints:
        template_changes.append(
            "ADD CONSTRAINT `fk_custom_templates_reward_badge` "
            "FOREIGN KEY (`reward_badge_id`) REFERENCES `badges` (`id`) ON DELETE RESTRICT"
        )

    statements = [
        statement
        for statement in (
            _alter("badges", badge_changes),
            _alter("custom_challenge_templates", template_changes),
        )
        if statement
    ]
    return "\n".join(statements) or "SELECT 1;"


async def downgrade(db: BaseDBAsyncClient) -> str:  # noqa: C901 - idempotent DDL needs per-object checks
    if db is None:
        badge_columns = {"type"}
        badge_indexes = {"idx_badges_type"}
        badge_constraints = {"fk_badges_type_common_code"}
        template_columns = {"challenge_type", "reward_badge_id"}
        template_indexes = {
            "idx_custom_challenge_templates_challenge_type",
            "idx_custom_challenge_templates_reward_badge",
        }
        template_constraints = {
            "fk_custom_templates_challenge_type",
            "fk_custom_templates_reward_badge",
        }
    else:
        badge_columns = await _schema_names(db, "badges", "COLUMNS", "COLUMN_NAME")
        badge_indexes = await _schema_names(db, "badges", "STATISTICS", "INDEX_NAME")
        badge_constraints = await _schema_names(db, "badges", "TABLE_CONSTRAINTS", "CONSTRAINT_NAME")
        template_columns = await _schema_names(db, "custom_challenge_templates", "COLUMNS", "COLUMN_NAME")
        template_indexes = await _schema_names(db, "custom_challenge_templates", "STATISTICS", "INDEX_NAME")
        template_constraints = await _schema_names(
            db,
            "custom_challenge_templates",
            "TABLE_CONSTRAINTS",
            "CONSTRAINT_NAME",
        )

    template_changes = []
    if "fk_custom_templates_reward_badge" in template_constraints:
        template_changes.append("DROP FOREIGN KEY `fk_custom_templates_reward_badge`")
    if "fk_custom_templates_challenge_type" in template_constraints:
        template_changes.append("DROP FOREIGN KEY `fk_custom_templates_challenge_type`")
    if "idx_custom_challenge_templates_reward_badge" in template_indexes:
        template_changes.append("DROP INDEX `idx_custom_challenge_templates_reward_badge`")
    if "idx_custom_challenge_templates_challenge_type" in template_indexes:
        template_changes.append("DROP INDEX `idx_custom_challenge_templates_challenge_type`")
    if "reward_badge_id" in template_columns:
        template_changes.append("DROP COLUMN `reward_badge_id`")
    if "challenge_type" in template_columns:
        template_changes.append("DROP COLUMN `challenge_type`")

    badge_changes = []
    if "fk_badges_type_common_code" in badge_constraints:
        badge_changes.append("DROP FOREIGN KEY `fk_badges_type_common_code`")
    if "idx_badges_type" in badge_indexes:
        badge_changes.append("DROP INDEX `idx_badges_type`")
    if "type" in badge_columns:
        badge_changes.append("DROP COLUMN `type`")

    statements = [
        statement
        for statement in (
            _alter("custom_challenge_templates", template_changes),
            _alter("badges", badge_changes),
        )
        if statement
    ]
    return "\n".join(statements) or "SELECT 1;"


MODELS_STATE = (
    "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"
    "ZmgUHZY0FaqzZ+svETHtkqkMvfZfDf/w8esQz6"
)
