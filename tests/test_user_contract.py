from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.utils.security import hash_password
from app.models.enums import AccountStatus


def load_user_contract():
    try:
        auth_dtos = import_module("app.dtos.auth")
        user_dtos = import_module("app.dtos.users")
        auth_services = import_module("app.services.auth")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.fail(f"user contract cannot be imported: {exc}")
    return auth_dtos, user_dtos, auth_services


def test_signup_contract_does_not_require_removed_profile_fields() -> None:
    auth_dtos, _, _ = load_user_contract()

    request = auth_dtos.SignUpRequest.model_validate(
        {
            "email": "user@example.com",
            "password": "Password123!",
            "name": "테스터",
            "phone_number": "01012345678",
        }
    )

    assert request.model_dump() == {
        "email": "user@example.com",
        "password": "Password123!",
        "name": "테스터",
        "phone_number": "01012345678",
    }


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
async def test_suspended_user_cannot_authenticate() -> None:
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
        await service.authenticate(
            auth_dtos.LoginRequest(email="user@example.com", password="Password123!")
        )

    assert exc_info.value.status_code == 423
