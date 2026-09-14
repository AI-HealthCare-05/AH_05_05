import importlib

from aerich.utils import decompress_dict

from app.models.background_jobs import BackgroundJob


def test_background_job_exposes_email_recovery_fields_and_indexes() -> None:
    fields = BackgroundJob._meta.fields_map

    assert fields["encrypted_payload"].null is True
    assert fields["next_attempt_at"].null is True
    assert fields["lease_expires_at"].null is True
    assert {index.name for index in BackgroundJob._meta.indexes if hasattr(index, "name")} >= {
        "idx_email_job_retry_due",
        "idx_email_job_lease",
    }


async def test_email_background_task_migration_adds_recovery_schema() -> None:
    migration = importlib.import_module("app.core.db.migrations.models.46_20260914000000_email_background_tasks")

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert "`encrypted_payload` LONGTEXT" in upgrade_sql
    assert "`next_attempt_at` DATETIME(6)" in upgrade_sql
    assert "`lease_expires_at` DATETIME(6)" in upgrade_sql
    assert "`idx_email_job_retry_due`" in upgrade_sql
    assert "`idx_email_job_lease`" in upgrade_sql
    assert "EMAIL_PAYLOAD_UNAVAILABLE" in upgrade_sql
    assert "DROP INDEX `idx_email_job_lease`" in downgrade_sql
    assert "DROP INDEX `idx_email_job_retry_due`" in downgrade_sql
    assert "DROP COLUMN `encrypted_payload`" in downgrade_sql


def test_email_background_task_migration_state_matches_runtime_model() -> None:
    migration = importlib.import_module("app.core.db.migrations.models.46_20260914000000_email_background_tasks")
    state = decompress_dict(migration.MODELS_STATE)
    background_job = state["models.BackgroundJob"]

    assert {field["name"] for field in background_job["data_fields"]} >= {
        "encrypted_payload",
        "next_attempt_at",
        "lease_expires_at",
    }
    assert {index["name"] for index in background_job["indexes"] if isinstance(index, dict)} >= {
        "idx_email_job_retry_due",
        "idx_email_job_lease",
    }
