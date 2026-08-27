from datetime import time

from tortoise import fields, models

from app.models.enums import AccountStatus, Gender, NotifySettingKey


class User(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.PENDING)
    name = fields.CharField(max_length=100)
    phone = fields.TextField(null=True)
    birth_date = fields.DateField(null=True)
    gender = fields.CharEnumField(Gender, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user"
        indexes = (("status",), ("created_at",))


class UserSettings(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.OneToOneRelation[User] = fields.OneToOneField(
        "models.User",
        related_name="settings",
        on_delete=fields.CASCADE,
    )
    is_notify_medication = fields.BooleanField(default=False)
    is_notify_supplement = fields.BooleanField(default=False)
    is_notify_schedule = fields.BooleanField(default=False)
    is_notify_guide = fields.BooleanField(default=False)
    is_terms_agreed = fields.BooleanField(default=False)
    terms_agreed_at = fields.DatetimeField(null=True)
    notify_consented_at = fields.DatetimeField(null=True)
    morning_medication_time = fields.TimeField(default=time(8, 0))
    lunch_medication_time = fields.TimeField(default=time(13, 0))
    evening_medication_time = fields.TimeField(default=time(19, 0))
    bedtime_medication_time = fields.TimeField(default=time(22, 0))

    class Meta:
        table = "user_settings"


class UserNotifyHistory(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "models.User",
        related_name="notify_histories",
        on_delete=fields.CASCADE,
    )
    setting_key = fields.CharEnumField(NotifySettingKey)
    new_value = fields.BooleanField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_notify_histories"
        indexes = (("user", "setting_key", "created_at"), ("created_at",))
