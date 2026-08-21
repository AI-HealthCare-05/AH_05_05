from datetime import datetime

from tortoise import fields, models

from app.models.enums import AccountStatus, AdminRole


class Admin(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    hashed_password = fields.CharField(max_length=255)
    status = fields.CharEnumField(AccountStatus, default=AccountStatus.PENDING)
    name = fields.CharField(max_length=100)
    role = fields.CharEnumField(AdminRole, default=AdminRole.STAFF)
    created_by_admin: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.Admin",
        related_name="created_admins",
        null=True,
        on_delete=fields.SET_NULL,
    )
    # null=True 인데 타입 주석이 없으면 정적 분석이 datetime 으로 좁혀 None 대입을 막는다.
    approved_at: datetime | None = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "admin"
        indexes = (("role",), ("status",), ("created_by_admin",), ("created_at",))
