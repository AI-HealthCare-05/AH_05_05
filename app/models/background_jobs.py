from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.validators import MinValueValidator

from app.models.enums import BackgroundJobStatus, BackgroundJobType


class BackgroundJob(models.Model):
    id = fields.BigIntField(primary_key=True)
    idempotency_key = fields.CharField(max_length=150, unique=True)
    job_type = fields.CharEnumField(BackgroundJobType)
    status = fields.CharEnumField(BackgroundJobStatus, default=BackgroundJobStatus.QUEUED)
    user: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="background_jobs",
        null=True,
        on_delete=fields.CASCADE,
    )
    reference_table = fields.CharField(max_length=50, null=True)
    reference_id = fields.BigIntField(null=True)
    requested_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    duration_ms = fields.IntField(null=True)
    retry_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    max_retry_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    parent_job: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.BackgroundJob",
        related_name="retry_jobs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    error_code = fields.CharField(max_length=100, null=True)
    error_message = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "background_jobs"
        indexes = (
            ("job_type", "status"),
            ("requested_at",),
            ("user",),
            Index(fields=("status", "requested_at"), name="idx_queue_stats"),
        )
