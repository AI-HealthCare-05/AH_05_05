from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.core.validators import optional_after_validator, validate_password, validate_phone_number
from app.dtos.base import BaseSerializerModel
from app.models.enums import AccountStatus, Gender


class UserUpdateRequest(BaseModel):
    """마이페이지 「기본정보 수정」이 보내는 값. 보낸 항목만 바뀐다(exclude_none)."""

    name: Annotated[str | None, Field(None, min_length=2, max_length=100)]
    email: Annotated[
        EmailStr | None,
        Field(None, max_length=255),
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


class PasswordChangeRequest(BaseModel):
    """마이페이지 「비밀번호 변경」. 대상은 토큰의 사용자이고 사용자 ID 는 받지 않는다."""

    current_password: Annotated[str, Field(min_length=1)]
    # 관리자 쪽(AdminPasswordChangeRequest)과 같은 검증기를 쓴다.
    # 함수를 공유하면 두 곳의 비밀번호 정책이 어긋날 일이 없다.
    new_password: Annotated[str, AfterValidator(validate_password)]


class PasswordChangeResponse(BaseModel):
    detail: str


class UserInfoResponse(BaseSerializerModel):
    id: int
    name: str
    email: str
    phone_number: Annotated[str | None, Field(validation_alias="phone")]
    # 모델에는 있었으나 응답에 싣지 않아, 화면이 폼을 채우지 못했다.
    # 가입 시 선택 항목이라 기존 회원은 null 일 수 있다.
    birth_date: date | None = None
    gender: Gender | None = None
    status: AccountStatus
    created_at: datetime
