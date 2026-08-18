from tortoise import fields, models

from app.models.accounts import Account


class User(models.Model):
    """실제 서비스 이용자의 프로필. 전화번호 등 직접식별정보는 애플리케이션 계층에서 암호화한다."""

    id = fields.BigIntField(primary_key=True)
    account: fields.OneToOneRelation[Account] = fields.OneToOneField(
        "models.Account",
        related_name="user",
        on_delete=fields.CASCADE,
        source_field="account_id",
    )
    name = fields.CharField(max_length=100)
    # ERD 기준 text·nullable. 암호화 저장 시 평문 비교가 불가능해
    # REQ-USER-004/005의 "휴대폰 번호 중복불가"를 이 컬럼만으로는 검증할 수 없다.
    # 별도 phone_hash 컬럼이 필요한지 ERD 작성자 확인이 필요하다.
    phone = fields.TextField(null=True)
    is_alarm = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user"
