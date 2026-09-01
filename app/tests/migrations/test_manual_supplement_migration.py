from importlib import import_module

MIGRATION = import_module("app.core.db.migrations.models.17_20260901143841_allow_manual_user_supplements")


async def test_downgrade_removes_only_manual_chat_sources_before_registrations() -> None:
    sql = await MIGRATION.downgrade(None)
    source_delete = """DELETE FROM `chat_message_sources`
        WHERE `user_suppl_nutrient_id` IN (
          SELECT `id` FROM `user_suppl_nutrient`
          WHERE `supplement_nutrient_id` IS NULL
        );"""
    registration_delete = "DELETE FROM `user_suppl_nutrient` WHERE `supplement_nutrient_id` IS NULL;"

    assert source_delete in sql
    assert registration_delete in sql
    assert sql.index(source_delete) < sql.index(registration_delete)
