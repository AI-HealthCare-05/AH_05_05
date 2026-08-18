from tortoise import fields, models

from app.models.enums import AccountStatus


class User(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.PENDING)
    name = fields.CharField(max_length=100)
    phone = fields.TextField(null=True)
    is_alarm = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user"
        indexes = (("status",), ("created_at",))
