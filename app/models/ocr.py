from datetime import datetime

from tortoise import fields, models

from app.models.enums import OcrJobStatus


class OcrJob(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="ocr_jobs",
        on_delete=fields.CASCADE,
    )
    care_episode: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="ocr_jobs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    status = fields.CharEnumField(OcrJobStatus, default=OcrJobStatus.QUEUED)
    idempotency_key = fields.CharField(max_length=100)
    input_manifest: dict[str, object] | list[object] = fields.JSONField()
    structured_result: dict[str, object] | list[object] | None = fields.JSONField(null=True)
    ocr_model = fields.CharField(max_length=100)
    structuring_model = fields.CharField(max_length=100)
    prompt_version = fields.CharField(max_length=100)
    schema_version = fields.CharField(max_length=50)
    error_code: str | None = fields.CharField(max_length=100, null=True)  # type: ignore[assignment]
    started_at: datetime | None = fields.DatetimeField(null=True)
    ready_at: datetime | None = fields.DatetimeField(null=True)
    expires_at: datetime | None = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at: datetime | None = fields.DatetimeField(null=True)
    completed_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        table = "ocr_jobs"
        indexes = (("care_episode", "status"), ("expires_at",))
        unique_together = (
            ("user", "idempotency_key"),
            ("id", "care_episode"),
        )
