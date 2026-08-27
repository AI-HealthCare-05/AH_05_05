from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StrictBool, StringConstraints, field_validator

from app.core.validators import validate_birthday, validate_password, validate_phone_number
from app.models.enums import Gender


class SignUpRequest(BaseModel):
    email: Annotated[
        EmailStr,
        Field(max_length=255),
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


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8)]


class LoginResponse(BaseModel):
    access_token: str


class TokenRefreshResponse(LoginResponse): ...
