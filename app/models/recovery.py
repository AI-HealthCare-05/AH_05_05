from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import (
    CareEpisodeSourceField,
    ChatSafetyStatus,
    GuideSourceType,
    PatientSourceKind,
    RecoveryGuideStatus,
)


class RecoveryGuide(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="recovery_guides",
        on_delete=fields.CASCADE,
    )
    status = fields.CharEnumField(RecoveryGuideStatus, default=RecoveryGuideStatus.COMPLETED)
    guide_content: fields.JSONField[dict[str, object] | list[object]] = fields.JSONField()
    patient_context_hash = fields.CharField(max_length=64)
    model_name = fields.CharField(max_length=100)
    model_version = fields.CharField(max_length=100, null=True)
    prompt_version = fields.CharField(max_length=100)
    schema_version = fields.CharField(max_length=50)
    langsmith_trace_id = fields.CharField(max_length=100, null=True)
    safety_status = fields.CharEnumField(ChatSafetyStatus)
    safety_reason_codes: fields.JSONField[list[str]] = fields.JSONField()
    error_code = fields.CharField(max_length=100, null=True)
    completed_at = fields.DatetimeField()
    superseded_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "recovery_guides"
        indexes = (
            ("care_episode", "status"),
            ("patient_context_hash",),
            ("langsmith_trace_id",),
            ("created_at",),
        )


class RecoveryGuideSource(models.Model):
    id = fields.BigIntField(primary_key=True)
    recovery_guide: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.RecoveryGuide",
        related_name="sources",
        on_delete=fields.CASCADE,
    )
    source_type = fields.CharEnumField(GuideSourceType)
    patient_source_kind = fields.CharEnumField(PatientSourceKind, null=True)
    patient_field = fields.CharEnumField(CareEpisodeSourceField, null=True)
    medication: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Medication",
        related_name="recovery_guide_sources",
        null=True,
        on_delete=fields.RESTRICT,
    )
    care_advice: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.CareAdvice",
        related_name="recovery_guide_sources",
        null=True,
        on_delete=fields.RESTRICT,
    )
    follow_up_visit: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.FollowUpVisit",
        related_name="recovery_guide_sources",
        null=True,
        on_delete=fields.RESTRICT,
    )
    public_dataset_key = fields.CharField(max_length=100, null=True)
    dataset_version = fields.CharField(max_length=100, null=True)
    vector_chunk_id = fields.CharField(max_length=255, null=True)
    source_record_key = fields.CharField(max_length=100, null=True)
    source_field = fields.CharField(max_length=100, null=True)
    chunk_type = fields.CharField(max_length=100, null=True)
    source_title = fields.CharField(max_length=255, null=True)
    source_organization = fields.CharField(max_length=255, null=True)
    source_url = fields.TextField(null=True)
    source_page_number = fields.IntField(null=True, validators=[MinValueValidator(1)])
    source_license = fields.CharField(max_length=255, null=True)
    similarity_score = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    citation_order = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "recovery_guide_sources"
        indexes = (
            ("recovery_guide",),
            ("medication",),
            ("care_advice",),
            ("follow_up_visit",),
            ("public_dataset_key", "source_record_key"),
            ("vector_chunk_id",),
        )
        unique_together = (("recovery_guide", "citation_order"),)
