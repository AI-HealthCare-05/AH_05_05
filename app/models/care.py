from tortoise import fields, models

from app.models.enums import CareEpisodeStatus, MealSlot


class CareEpisode(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User", related_name="care_episodes", on_delete=fields.CASCADE
    )
    alias = fields.CharField(max_length=255, null=True)
    hospital_name = fields.CharField(max_length=255, null=True)
    status = fields.CharEnumField(CareEpisodeStatus, default=CareEpisodeStatus.ACTIVE)
    medication_days = fields.IntField(null=True)
    source_ocr_job_id = fields.BigIntField(null=True)
    confirmation_hash = fields.CharField(max_length=64, null=True)
    confirmed_at = fields.DatetimeField(null=True)
    medication_start_date = fields.DateField(null=True)
    medication_start_slot = fields.CharEnumField(MealSlot, null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "care_episodes"
        indexes = (("user", "status"),)


class FollowUpVisit(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="follow_up_visits",
        on_delete=fields.CASCADE,
    )
    visit_date = fields.DateField()
    visit_time = fields.TimeField(null=True)
    hospital = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "follow_up_visits"
        indexes = (("user",), ("visit_date", "visit_time", "id"))
