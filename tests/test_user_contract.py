from datetime import date, datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import config
from app.core.utils.security import hash_password
from app.main import app
from app.models.enums import AccountStatus


def load_user_contract():
    try:
        auth_dtos = import_module("app.dtos.auth")
        user_dtos = import_module("app.dtos.users")
        auth_services = import_module("app.services.auth")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"user contract cannot be imported: {exc}")
    return auth_dtos, user_dtos, auth_services


def signup_payload(**overrides):
    payload = {
        "email": "user@example.com",
        "password": "Password123!",
        "name": "테스터",
        "phone_number": "01012345678",
        "birth_date": "1990-01-01",
        "gender": "FEMALE",
        "is_terms_agreed": True,
    }
    payload.update(overrides)
    return payload


def test_signup_contract_requires_profile_and_terms_fields() -> None:
    auth_dtos, _, _ = load_user_contract()

    request = auth_dtos.SignUpRequest.model_validate(signup_payload())

    assert request.model_dump() == {
        "email": "user@example.com",
        "password": "Password123!",
        "name": "테스터",
        "phone_number": "01012345678",
        "birth_date": request.birth_date,
        "gender": request.gender,
        "is_terms_agreed": True,
    }


def test_signup_contract_rejects_missing_email() -> None:
    auth_dtos, _, _ = load_user_contract()

    with pytest.raises(ValidationError):
        auth_dtos.SignUpRequest.model_validate(
            {
                "password": "Password123!",
                "name": "테스터",
                "phone_number": "01012345678",
                "birth_date": "1990-01-01",
                "gender": "FEMALE",
                "is_terms_agreed": True,
            }
        )


def test_signup_contract_trims_name() -> None:
    auth_dtos, _, _ = load_user_contract()

    request = auth_dtos.SignUpRequest.model_validate(signup_payload(name="  테스터  "))

    assert request.name == "테스터"


def test_signup_contract_rejects_name_shorter_than_two_characters_after_trim() -> None:
    auth_dtos, _, _ = load_user_contract()

    with pytest.raises(ValidationError):
        auth_dtos.SignUpRequest.model_validate(signup_payload(name=" 김 "))


def test_signup_contract_accepts_exact_fourteenth_birthday() -> None:
    auth_dtos, _, _ = load_user_contract()
    exact_fourteenth_birthday = datetime.now(tz=config.TIMEZONE).date() - relativedelta(years=14)

    request = auth_dtos.SignUpRequest.model_validate(signup_payload(birth_date=exact_fourteenth_birthday.isoformat()))

    assert request.birth_date == exact_fourteenth_birthday


@pytest.mark.parametrize(
    "birth_date",
    [
        date(1899, 12, 31),
        datetime.now(tz=config.TIMEZONE).date() + timedelta(days=1),
        datetime.now(tz=config.TIMEZONE).date() - relativedelta(years=14) + timedelta(days=1),
    ],
)
def test_signup_contract_rejects_out_of_range_birth_date(birth_date: date) -> None:
    auth_dtos, _, _ = load_user_contract()

    with pytest.raises(ValidationError):
        auth_dtos.SignUpRequest.model_validate(signup_payload(birth_date=birth_date.isoformat()))


def test_user_response_maps_database_phone_to_existing_api_name() -> None:
    _, user_dtos, _ = load_user_contract()
    user = SimpleNamespace(
        id=1,
        email="user@example.com",
        name="테스터",
        phone="01012345678",
        status=AccountStatus.ACTIVE,
        created_at="2026-08-18T12:00:00+09:00",
    )

    response = user_dtos.UserInfoResponse.model_validate(user)

    assert response.phone_number == "01012345678"
    assert response.status == AccountStatus.ACTIVE
    assert not hasattr(response, "is_alarm")


@pytest.mark.asyncio
async def test_suspended_user_is_indistinguishable_from_wrong_credentials() -> None:
    """정지 계정도 자격증명 오류와 같은 응답이어야 한다.

    예전에는 423 으로 갈라져 상태 코드만으로 그 이메일의 가입 여부를 알 수 있었다(#196).
    """
    auth_dtos, _, auth_services = load_user_contract()
    user = SimpleNamespace(
        id=1,
        email="user@example.com",
        hashed_password=hash_password("Password123!"),
        status=AccountStatus.SUSPENDED,
    )

    class UserRepositoryStub:
        async def get_user_by_email(self, email: str):
            return user

    service = auth_services.AuthService()
    service.user_repo = UserRepositoryStub()

    with pytest.raises(HTTPException) as exc_info:
        await service.authenticate(auth_dtos.LoginRequest(email="user@example.com", password="Password123!"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "이메일 또는 비밀번호가 올바르지 않습니다."


def test_signup_openapi_documents_response_schemas() -> None:
    openapi = app.openapi()
    responses = openapi["paths"]["/api/v1/auth/signup"]["post"]["responses"]

    assert responses["201"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/SignUpResponse"}
    assert responses["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AuthErrorResponse"
    }
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AuthErrorResponse"
    }

    schemas = openapi["components"]["schemas"]
    assert schemas["SignUpResponse"]["required"] == ["detail"]
    assert schemas["AuthErrorResponse"]["required"] == ["code", "message"]


def test_signup_openapi_documents_error_examples() -> None:
    responses = app.openapi()["paths"]["/api/v1/auth/signup"]["post"]["responses"]

    assert responses["409"]["content"]["application/json"]["example"] == {
        "code": "EMAIL_ALREADY_EXISTS",
        "message": "이미 사용중인 이메일입니다.",
        "field": "email",
    }
    assert responses["422"]["content"]["application/json"]["example"] == {
        "code": "VALIDATION_ERROR",
        "message": "입력값이 올바르지 않습니다.",
        "field": "email",
    }
