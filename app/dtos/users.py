from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, ConfigDict, EmailStr, Field

from app.core.validators import optional_after_validator, validate_name, validate_password, validate_phone_number
from app.dtos.base import CamelModel
from app.models.enums import AccountStatus, Gender


class UserUpdateRequest(CamelModel):
    """마이페이지 「기본정보 수정」이 보내는 값. 보낸 항목만 바뀐다(exclude_none)."""

    # 전 필드가 선택이라 모르는 키를 무시하면 "바꿀 항목 0개"가 되어 200 이 나간다.
    # 오타(phoneNumbr)가 저장 성공으로 보였다.
    #
    # CamelModel 의 설정(alias_generator·populate_by_name)은 부모에서 상속되므로
    # 여기서 extra 만 더해도 별칭 변환은 그대로 살아 있다.
    model_config = ConfigDict(extra="forbid")

    # 상한은 DB 컬럼 폭이 아니라 화면에서 받아야 할 길이 기준이다.
    # 회원가입(SignUpRequest)·프론트 상수와 같은 값을 쓴다.
    # 선택 필드라 optional_after_validator 를 쓴다. 그냥 AfterValidator 를 붙이면
    # 「이름을 안 보낸」 요청이 None 을 검사하다 죽는다(phone_number 와 같은 방식).
    name: Annotated[
        str | None,
        Field(None, min_length=2, max_length=20),
        optional_after_validator(validate_name),
    ]
    email: Annotated[
        EmailStr | None,
        Field(None, max_length=40),
    ]
    phone_number: Annotated[
        str | None,
        Field(None, description="Available Format: +8201011112222, 01011112222, 010-1111-2222"),
        optional_after_validator(validate_phone_number),
    ]
    # 가입 때 받아 저장하던 값들인데 수정 경로가 없었다. 화면의 「기본정보」 네 칸 중
    # 둘이라 여기 없으면 생년월일·성별을 고칠 방법이 아예 없다.
    birth_date: date | None = None
    gender: Gender | None = None


class PasswordChangeRequest(CamelModel):
    """마이페이지 「비밀번호 변경」. 대상은 토큰의 사용자이고 사용자 ID 는 받지 않는다."""

    current_password: Annotated[str, Field(min_length=1)]
    # 관리자 쪽(AdminPasswordChangeRequest)과 같은 검증기를 쓴다.
    # 함수를 공유하면 두 곳의 비밀번호 정책이 어긋날 일이 없다.
    new_password: Annotated[str, AfterValidator(validate_password)]


class PasswordChangeResponse(CamelModel):
    detail: str


class WithdrawRequest(CamelModel):
    """마이페이지 「회원 탈퇴」. 본인 확인용이라 비밀번호 하나만 받는다.

    validate_password 를 붙이지 않는다. 새로 정하는 비밀번호가 아니라 대조용이고,
    정책이 바뀌기 전에 가입한 계정이 자기 비밀번호로 탈퇴하지 못하게 된다.
    """

    password: Annotated[str, Field(min_length=1)]


class UserInfoResponse(CamelModel):
    id: int
    name: str
    masked_name: str = "익명"
    email: str
    # validation_alias 는 입력에만 걸린다. DB 컬럼이 phone 이라 여기서 읽고,
    # 응답 키는 CamelModel 의 별칭 생성기가 phoneNumber 로 만든다. 둘이 충돌하지 않는다.
    phone_number: Annotated[str | None, Field(validation_alias="phone")]
    # 모델에는 있었으나 응답에 싣지 않아, 화면이 폼을 채우지 못했다.
    # 가입 시 선택 항목이라 기존 회원은 null 일 수 있다.
    birth_date: date | None = None
    gender: Gender | None = None
    status: AccountStatus
    created_at: datetime
