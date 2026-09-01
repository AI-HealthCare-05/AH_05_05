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

from app.core.validators import validate_ascii_email, validate_birthday, validate_password, validate_phone_number
from app.models.enums import Gender


class SignUpRequest(BaseModel):
    # BeforeValidator 라야 EmailStr 의 영문 메시지보다 우리 안내가 먼저 나간다.
    email: Annotated[
        EmailStr,
        Field(max_length=255),
        BeforeValidator(validate_ascii_email),
    ]
    password: Annotated[str, Field(min_length=8), AfterValidator(validate_password)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
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
