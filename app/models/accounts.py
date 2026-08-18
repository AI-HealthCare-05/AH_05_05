from enum import StrEnum

from tortoise import fields, models


class AccountType(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    # PENDING = 임시 비밀번호 상태 (은미님 확인 필요)
    # ERD에는 관리자 전용 TEMP 상태가 없어 PENDING을 그 용도로 함께 쓴다.
    # REQ-ADMIN-008로 생성된 관리자는 PENDING으로 시작하고,
    # REQ-ADMIN-009 비밀번호 변경을 마쳐야 ACTIVE가 된다.
    # 일반 사용자의 PENDING(최초 문서 업로드 전)과 의미가 겹치므로,
    # 두 상태를 분리해야 하는지 ERD 작성자 확인이 필요하다.
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    WITHDRAWN = "WITHDRAWN"


class Account(models.Model):
    """일반 사용자와 관리자의 공통 인증 계정. account_type에 따라 user 또는 admin과 연결한다."""

    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255, unique=True)
    # 소셜 로그인 계정은 비밀번호가 없으므로 null을 허용한다.
    hashed_password = fields.CharField(max_length=255, null=True)
    account_type = fields.CharEnumField(enum_type=AccountType)
    status = fields.CharEnumField(enum_type=AccountStatus, default=AccountStatus.PENDING)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "accounts"
        indexes = (
            ("account_type", "status"),
            ("created_at",),
        )
