from tortoise import fields, models
from tortoise.validators import MinValueValidator

from app.models.enums import CareEpisodeStatus


class CareEpisode(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User", related_name="care_episodes", on_delete=fields.CASCADE
    )
    title = fields.CharField(max_length=150)
    status = fields.CharEnumField(CareEpisodeStatus, default=CareEpisodeStatus.ACTIVE)
    started_at = fields.DatetimeField(auto_now_add=True)
    default_end_at = fields.DatetimeField(null=True)
    planned_end_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "care_episodes"
        indexes = (("user", "status"), ("user", "planned_end_at"))


class CareAdvice(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="care_advices",
        on_delete=fields.CASCADE,
    )
    text = fields.CharField(max_length=500)
    display_order = fields.IntField(validators=[MinValueValidator(1)])
    source_extracted_field: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.OcrExtractedField",
        related_name="care_advices",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "care_advices"
        unique_together = (("care_episode", "display_order"),)


class FollowUpVisit(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="follow_up_visits",
        on_delete=fields.CASCADE,
    )
    visit_at = fields.DatetimeField()
    department = fields.CharField(max_length=100, null=True)
    doctor_name = fields.CharField(max_length=100, null=True)
    place = fields.CharField(max_length=255, null=True)
    purpose = fields.CharField(max_length=255, null=True)
    source_extracted_field: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.OcrExtractedField",
        related_name="follow_up_visits",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "follow_up_visits"
        indexes = (("care_episode",), ("visit_at",))
