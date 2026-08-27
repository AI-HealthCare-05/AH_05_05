from importlib import import_module

MIGRATION = import_module("app.core.db.migrations.models.10_20260827045958_add_notification_settings")


async def test_upgrade_changes_only_notification_settings_and_alarm_shape() -> None:
    sql = await MIGRATION.upgrade(None)

    assert "ADD `is_notify_supplement` BOOL NOT NULL DEFAULT 0" in sql
    assert "NUTRIENT: NUTRIENT" in sql
    assert "`alarm_type` IN ('MEDICATION', 'NUTRIENT')" in sql
    assert "`alarm_type` NOT IN ('MEDICATION', 'NUTRIENT')" in sql
    assert "ocr_jobs" not in sql
    assert "is_notify_schedule` SET DEFAULT" not in sql
    assert "is_notify_guide` SET DEFAULT" not in sql


async def test_downgrade_restores_medication_only_slot_constraint() -> None:
    sql = await MIGRATION.downgrade(None)

    assert "`alarm_type` = 'MEDICATION' AND `meal_slot` IS NOT NULL" in sql
    assert "`alarm_type` <> 'MEDICATION' AND `meal_slot` IS NULL" in sql
    assert "DROP COLUMN `is_notify_supplement`" in sql
