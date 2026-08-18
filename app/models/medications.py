from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator


class Medication(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="medications",
        on_delete=fields.CASCADE,
    )
    name = fields.CharField(max_length=255)
    dose = fields.CharField(max_length=100, null=True)
    times_per_day = fields.IntField(
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
    )
    note = fields.CharField(max_length=255, null=True)
    days = fields.IntField(null=True, validators=[MinValueValidator(1)])
    prescribed_at = fields.DateField(null=True)
    source_ocr_job = fields.ForeignKeyField(
        "models.OcrJob",
        related_name="medications",
        null=True,
        on_delete=fields.SET_NULL,
    )
    source_extracted_field = fields.ForeignKeyField(
        "models.OcrExtractedField",
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


class MedicationTime(models.Model):
    id = fields.BigIntField(primary_key=True)
    medication = fields.ForeignKeyField(
        "models.Medication",
        related_name="times",
        on_delete=fields.CASCADE,
    )
    time_of_day = fields.TimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "medication_times"
        indexes = (("time_of_day",),)
        unique_together = (("medication", "time_of_day"),)

