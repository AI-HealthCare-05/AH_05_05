"""Tests for applying the unused-column migration to partially updated databases."""

from importlib import import_module

import pytest

MIGRATION = "app.core.db.migrations.models.48_20260914214228_remove_unused_chat_and_reference_fields"


class _SchemaClient:
    def __init__(self, columns_by_table: dict[str, set[str]]) -> None:
        self.columns_by_table = columns_by_table

    async def execute_query_dict(self, query: str, values: list[str]) -> list[dict[str, str]]:
        assert "information_schema.COLUMNS" in query
        (table,) = values
        return [{"COLUMN_NAME": column} for column in self.columns_by_table.get(table, set())]


@pytest.mark.asyncio
async def test_upgrade_skips_legacy_column_already_removed_from_database():
    migration = import_module(MIGRATION)
    db = _SchemaClient(
        {
            "chat_messages": {"conflict_status"},
            "interaction_entity_aliases": {"is_preferred"},
            "medication_product_guides": {"item_image_url"},
        }
    )

    sql = await migration.upgrade(db)

    assert "DROP COLUMN `verification_status`" not in sql
    assert "DROP COLUMN `conflict_status`" in sql
    assert "DROP COLUMN `is_preferred`" in sql
    assert "DROP COLUMN `item_image_url`" in sql


@pytest.mark.asyncio
async def test_upgrade_is_a_noop_when_all_legacy_columns_are_already_removed():
    migration = import_module(MIGRATION)
    db = _SchemaClient({})

    sql = await migration.upgrade(db)

    assert sql.strip() == "SELECT 1;"
