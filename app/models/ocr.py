from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import OcrDocumentType, OcrJobStatus, OcrMaskingStatus, OcrReviewStatus


class OcrJob(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="ocr_jobs",
        on_delete=fields.CASCADE,
    )
    document_type = fields.CharEnumField(OcrDocumentType)
    status = fields.CharEnumField(OcrJobStatus, default=OcrJobStatus.QUEUED)
    masking_status = fields.CharEnumField(OcrMaskingStatus, default=OcrMaskingStatus.PENDING)
    idempotency_key = fields.CharField(max_length=100, unique=True)
    content_hash = fields.CharField(max_length=71)
    page_count = fields.IntField(default=1, validators=[MinValueValidator(1)])
    pipeline_version = fields.CharField(max_length=50)
    error_code = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    completed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "ocr_jobs"
        indexes = (("care_episode", "status"), ("content_hash",))


class OcrExtractedField(models.Model):
    id = fields.BigIntField(primary_key=True)
    ocr_job = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="extracted_fields",
        on_delete=fields.CASCADE,
    )
    entity_key = fields.CharField(max_length=100)
    field_type = fields.CharField(max_length=100)
    raw_value = fields.TextField(null=True)
    normalized_value = fields.JSONField(null=True)
    reviewed_value = fields.JSONField(null=True)
    confidence = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    review_status = fields.CharEnumField(OcrReviewStatus, default=OcrReviewStatus.UNREVIEWED)
    source_page = fields.IntField(null=True, validators=[MinValueValidator(1)])
    created_at = fields.DatetimeField(auto_now_add=True)
    corrected_at = fields.DatetimeField(null=True)
    reviewed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "ocr_extracted_fields"
        indexes = (("ocr_job", "review_status"),)
        unique_together = (("ocr_job", "entity_key", "field_type"),)

