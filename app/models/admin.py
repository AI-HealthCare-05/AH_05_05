from enum import StrEnum

from tortoise import fields, models

from app.models.accounts import Account


class AdminRole(StrEnum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"


class Admin(models.Model):
    """관리자 전용 프로필. 일반 회원가입으로 생성하지 않고 ADMIN이 계정을 생성한다(REQ-ADMIN-008)."""

    id = fields.BigIntField(primary_key=True)
    account: fields.OneToOneRelation[Account] = fields.OneToOneField(
        "models.Account",
        related_name="admin",
        on_delete=fields.CASCADE,
        source_field="account_id",
    )
    role = fields.CharEnumField(enum_type=AdminRole, default=AdminRole.STAFF)
    # ERD에 인덱스만 있고 FK 제약이 없어 그대로 따랐다.
    # NOT NULL이라 최초 ADMIN 1명은 생성자가 없어 넣을 수 없다.
    # 시드 방식(자기 참조 허용 / nullable 전환 중 택일)을 ERD 작성자와 정해야 한다.
    created_by_account_id = fields.BigIntField()
    approved_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "admin"
        indexes = (
            ("role",),
            ("created_by_account_id",),
        )
