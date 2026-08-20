from tortoise import fields, models

from app.core.utils.security import generate_session_salt
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
    # 세션 무효화용 난수. 리프레시 토큰의 sid 클레임과 대조한다.
    # 이 값을 새로 발급하면 기기와 무관하게 기존 리프레시 토큰이 모두 무효가 된다.
    # 갱신 시점은 app/services/admin_session.py 의 rotate_session_salt 참고.
    # 기본값은 DB 가 아니라 코드에서 만든다(계정마다 서로 다른 값이어야 한다).
    session_salt = fields.CharField(max_length=32, default=generate_session_salt)
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "admin"
        indexes = (("role",), ("status",), ("created_by_admin",), ("created_at",))
