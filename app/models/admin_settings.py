from tortoise import fields, models

from app.models.admins import Admin


class AdminSetting(models.Model):
    id = fields.BigIntField(primary_key=True, description="관리자 설정 식별자")
    setting_key = fields.CharField(max_length=50, unique=True, description="관리자 설정 구분 키")
    smtp_host = fields.CharField(max_length=255, description="SMTP 서버 주소")
    smtp_port = fields.IntField(description="SMTP 서버 포트")
    smtp_user = fields.CharField(max_length=255, description="SMTP 인증 계정")
    smtp_password_enc = fields.CharField(max_length=500, description="암호화된 SMTP 인증 비밀번호")
    smtp_from_email = fields.CharField(max_length=255, description="SMTP 발신 이메일 주소")
    updated_by_admin: fields.ForeignKeyRelation[Admin] = fields.ForeignKeyField(
        "models.Admin",
        related_name="updated_settings",
        on_delete=fields.RESTRICT,
        source_field="updated_by_admin_id",
        description="설정을 마지막으로 변경한 관리자 식별자",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="설정 생성 일시")
    updated_at = fields.DatetimeField(auto_now=True, description="설정 최종 수정 일시")

    class Meta:
        table = "admin_settings"
        indexes = (("updated_by_admin",), ("updated_at",))
