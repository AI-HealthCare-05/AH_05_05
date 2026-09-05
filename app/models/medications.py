from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import MealSlot


class Medication(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="medications",
        on_delete=fields.CASCADE,
    )
    name = fields.CharField(max_length=255)
    strength = fields.CharField(max_length=100, null=True)
    dose_quantity = fields.CharField(max_length=50, null=True)
    efficacy = fields.CharField(max_length=500, null=True)
    administration = fields.CharField(max_length=500, null=True)
    precautions = fields.CharField(max_length=500, null=True)
    times_per_day = fields.IntField(
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
    )
    note = fields.CharField(max_length=500, null=True)
    days = fields.IntField(
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )
    prescribed_at = fields.DateField(null=True)
    source_ocr_job: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="medications",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "medications"
        indexes = (
            ("care_episode",),
            ("care_episode", "name"),
            ("care_episode", "source_ocr_job"),
        )


class MedicationSlot(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.Medication",
        related_name="slots",
        on_delete=fields.CASCADE,
    )
    slot = fields.CharEnumField(MealSlot)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_slots"
        indexes = (("slot",),)
        unique_together = (("medication", "slot"),)


class MedicationDose(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="medication_doses",
        on_delete=fields.CASCADE,
    )
    dose_date = fields.DateField()
    slot = fields.CharEnumField(MealSlot)
    taken_at = fields.DatetimeField(auto_now_add=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_doses"
        unique_together = (("user", "dose_date", "slot"),)
        indexes = (("user", "dose_date"),)


class MedicationNote(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="medication_notes",
        on_delete=fields.CASCADE,
    )
    care_episode: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="medication_notes",
        on_delete=fields.CASCADE,
    )
    medication: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Medication",
        related_name="medication_notes",
        null=True,
        on_delete=fields.SET_NULL,
    )
    dosed_at = fields.DatetimeField()
    body = fields.CharField(max_length=500)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "medication_notes"
        indexes = (("user", "dosed_at"), ("care_episode",))
