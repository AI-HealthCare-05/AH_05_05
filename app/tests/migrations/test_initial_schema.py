"""Contracts retained after historical migrations were consolidated into the baseline."""

from importlib import import_module

import pytest

MIGRATION = import_module("app.core.db.migrations.models.0_20260915104023_init")


@pytest.fixture
async def schema_sql() -> str:
    return await MIGRATION.upgrade(None)


def table_sql(schema_sql: str, table: str) -> str:
    return schema_sql.split(f"CREATE TABLE IF NOT EXISTS `{table}` (", 1)[1].split(") CHARACTER SET", 1)[0]


def test_manual_supplements_allow_missing_catalog_entry(schema_sql: str) -> None:
    registration = table_sql(schema_sql, "user_suppl_nutrient")

    assert "`custom_name` VARCHAR(255)," in registration
    assert "`supplement_nutrient_id` BIGINT," in registration
    assert (
        "FOREIGN KEY (`supplement_nutrient_id`) REFERENCES `supplement_nutrients` (`id`) ON DELETE RESTRICT"
        in registration
    )
    sources = table_sql(schema_sql, "chat_message_sources")
    assert (
        "FOREIGN KEY (`user_suppl_nutrient_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE RESTRICT" in sources
    )


@pytest.mark.parametrize("setting", ["medication", "supplement", "schedule", "guide"])
def test_notification_settings_default_to_disabled(schema_sql: str, setting: str) -> None:
    assert f"`is_notify_{setting}` BOOL NOT NULL DEFAULT 0," in table_sql(schema_sql, "user_settings")


def test_alarms_support_independent_types_and_optional_meal_slot(schema_sql: str) -> None:
    alarms = table_sql(schema_sql, "alarms")

    for alarm_type in ("MEDICATION", "NUTRIENT", "FOLLOW_UP_VISIT", "GUIDE_CHECK"):
        assert f"{alarm_type}: {alarm_type}" in alarms
    assert "`meal_slot` VARCHAR(7) COMMENT" in alarms
    assert "(`user_id`, `alarm_type`, `meal_slot`)" in alarms


def test_phone_column_can_store_optional_encrypted_values(schema_sql: str) -> None:
    assert "`phone` LONGTEXT," in table_sql(schema_sql, "user")
