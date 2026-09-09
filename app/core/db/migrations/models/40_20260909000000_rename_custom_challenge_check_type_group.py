"""Rename the custom challenge check-type common-code group without changing its ID."""

from importlib import import_module

from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `common_code_groups`
        SET `group_code` = 'CST_CHK_TYPE'
        WHERE `category` = 'CHL'
          AND `group_code` = 'CHK_TYPE2';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `common_code_groups`
        SET `group_code` = 'CHK_TYPE2'
        WHERE `category` = 'CHL'
          AND `group_code` = 'CST_CHK_TYPE';"""


# This data-only migration keeps the schema state produced by the preceding migration.
MODELS_STATE = import_module(
    "app.core.db.migrations.models.39_20260908151829_challenge_daily_verification"
).MODELS_STATE
