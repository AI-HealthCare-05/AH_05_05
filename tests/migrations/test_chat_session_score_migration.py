from importlib import import_module

MIGRATION = import_module("app.core.db.migrations.models.21_20260902132849_add_chat_session_score")


async def test_upgrade_adds_only_validated_chat_session_score() -> None:
    sql = await MIGRATION.upgrade(None)

    assert "ALTER TABLE `chat_sessions` ADD `score` INT COMMENT '채팅 별점'" in sql
    assert "chk_chat_session_score" in sql
    assert "`score` BETWEEN 1 AND 5" in sql
    assert "user_suppl_nutrient" not in sql


async def test_downgrade_removes_score_constraint_and_column() -> None:
    sql = await MIGRATION.downgrade(None)

    assert "DROP CHECK `chk_chat_session_score`" in sql
    assert "DROP COLUMN `score`" in sql
    assert "user_suppl_nutrient" not in sql
