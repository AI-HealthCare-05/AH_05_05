from datetime import date
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    EmailStr,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
)

from app.core.validators import (
    validate_ascii_email,
    validate_birthday,
    validate_name,
    validate_password,
    validate_phone_number,
)
from app.models.enums import Gender


class SignUpRequest(BaseModel):
    # BeforeValidator 라야 EmailStr 의 영문 메시지보다 우리 안내가 먼저 나간다.
    # 상한은 DB 컬럼 폭(varchar 255)이 아니라 화면에서 받아야 할 길이 기준이다.
    # 프론트 EMAIL_MAX_LENGTH 와 같은 값이며, maxLength 는 개발자도구로 지울 수 있고
    # API 직접 호출은 거치지도 않으므로 여기서도 막는다.
    email: Annotated[
        EmailStr,
        Field(max_length=40),
        BeforeValidator(validate_ascii_email),
    ]
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password)]
    # 상한은 DB 컬럼 폭(varchar 100)이 아니라 화면 기준이다. 프론트 NAME_MAX_LENGTH 와 같은 값.
    # strip_whitespace 가 먼저 돌아 앞뒤 공백은 잘린 값이 validate_name 으로 간다.
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=2, max_length=20),
        AfterValidator(validate_name),
    ]
    phone_number: Annotated[str, AfterValidator(validate_phone_number)]
    birth_date: Annotated[date, AfterValidator(validate_birthday)]
    gender: Gender
    is_terms_agreed: StrictBool

    @field_validator("is_terms_agreed")
    @classmethod
    def require_terms_agreement(cls, value: bool) -> bool:
        if not value:
            raise ValueError("필수 약관에 동의해야 합니다.")
        return value


class SignUpResponse(BaseModel):
    detail: str


class AuthErrorResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]


class LoginResponse(BaseModel):
    access_token: str


class TokenRefreshResponse(LoginResponse): ...
