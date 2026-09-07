import importlib


async def test_email_verification_migration_creates_constraints_and_indexes() -> None:
    migration = importlib.import_module("app.core.db.migrations.models.31_20260907131651_add_email_verifications")

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert "CREATE TABLE IF NOT EXISTS `email_verifications`" in upgrade_sql
    assert "`code_digest` CHAR(64) NOT NULL" in upgrade_sql
    assert "CONSTRAINT `chk_email_verification_attempt_count`" in upgrade_sql
    assert "CHECK (`attempt_count` BETWEEN 0 AND 5)" in upgrade_sql
    assert "idx_email_verification_lookup" in upgrade_sql
    assert "idx_email_verification_expiry" in upgrade_sql
    assert "idx_email_verification_state" in upgrade_sql
    assert "DROP TABLE IF EXISTS `email_verifications`" in downgrade_sql
