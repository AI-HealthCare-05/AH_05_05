"""Persist recoverable FastAPI email background task state."""

from copy import deepcopy
from importlib import import_module

from aerich.utils import compress_dict, decompress_dict
from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `background_jobs`
            ADD COLUMN `encrypted_payload` LONGTEXT NULL,
            ADD COLUMN `next_attempt_at` DATETIME(6) NULL,
            ADD COLUMN `lease_expires_at` DATETIME(6) NULL,
            ADD INDEX `idx_email_job_retry_due` (`job_type`, `status`, `next_attempt_at`),
            ADD INDEX `idx_email_job_lease` (`job_type`, `status`, `lease_expires_at`);

        UPDATE `background_jobs`
        SET `status` = 'FAILED',
            `completed_at` = CURRENT_TIMESTAMP(6),
            `updated_at` = CURRENT_TIMESTAMP(6),
            `error_code` = 'EMAIL_PAYLOAD_UNAVAILABLE',
            `error_message` = 'EMAIL_PAYLOAD_UNAVAILABLE'
        WHERE `job_type` = 'EMAIL'
          AND `status` IN ('QUEUED', 'PROCESSING', 'RETRY_WAITING')
          AND `encrypted_payload` IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE `background_jobs`
            DROP INDEX `idx_email_job_lease`,
            DROP INDEX `idx_email_job_retry_due`,
            DROP COLUMN `lease_expires_at`,
            DROP COLUMN `next_attempt_at`,
            DROP COLUMN `encrypted_payload`;
    """


_state = deepcopy(
    decompress_dict(
        import_module(
            "app.core.db.migrations.models.45_20260910190000_merge_custom_challenge_finalization_heads"
        ).MODELS_STATE
    )
)
_background_job = _state["models.BackgroundJob"]

_text_field = deepcopy(next(field for field in _background_job["data_fields"] if field["name"] == "error_message"))
_text_field.update(name="encrypted_payload", db_column="encrypted_payload")

_datetime_field = deepcopy(next(field for field in _background_job["data_fields"] if field["name"] == "updated_at"))
_next_attempt_field = deepcopy(_datetime_field)
_next_attempt_field.update(name="next_attempt_at", db_column="next_attempt_at")
_lease_field = deepcopy(_datetime_field)
_lease_field.update(name="lease_expires_at", db_column="lease_expires_at")

_created_at_index = next(
    index for index, field in enumerate(_background_job["data_fields"]) if field["name"] == "created_at"
)
_background_job["data_fields"][_created_at_index:_created_at_index] = (
    _text_field,
    _next_attempt_field,
    _lease_field,
)
_background_job["indexes"].extend(
    (
        {
            "fields": ["job_type", "status", "next_attempt_at"],
            "expressions": [],
            "name": "idx_email_job_retry_due",
            "type": "",
            "extra": "",
        },
        {
            "fields": ["job_type", "status", "lease_expires_at"],
            "expressions": [],
            "name": "idx_email_job_lease",
            "type": "",
            "extra": "",
        },
    )
)

MODELS_STATE = compress_dict(_state)
