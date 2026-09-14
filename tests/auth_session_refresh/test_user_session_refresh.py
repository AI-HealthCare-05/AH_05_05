import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.apis.v1.auth_routers import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH, auth_router
from app.core import config
from app.core.jwt.tokens import AccessToken, JwtScope, RefreshToken
from app.models.enums import AccountStatus
from app.repositories.user_repository import UserRepository
from app.services.auth import AuthService
from app.services.jwt import JwtService


def _user(user_id: int, *, status: AccountStatus = AccountStatus.ACTIVE) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, status=status)


def _refresh_token(user_id: int) -> str:
    return str(RefreshToken.for_user(_user(user_id)))


def _access_token(user_id: int, *, expired: bool = False) -> str:
    token = AccessToken.for_user(_user(user_id))
    if expired:
        token.set_exp(from_time=token.current_time - timedelta(hours=1), lifetime=timedelta(seconds=1))
    return str(token)


def _token_pair(user_id: int, *, expired_access: bool = False) -> tuple[str, str]:
    refresh = RefreshToken.for_user(_user(user_id))
    access = refresh.access_token
    if expired_access:
        access.set_exp(from_time=access.current_time - timedelta(hours=1), lifetime=timedelta(seconds=1))
    return str(refresh), str(access)


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(config, "USER_REFRESH_ENABLED", True)
    api = FastAPI()
    api.include_router(auth_router, prefix="/api/v1")
    return api


async def _request(
    app: FastAPI,
    *,
    refresh_token: str | None,
    access_token: str | None = None,
    method: str = "GET",
    path: str = "/api/v1/auth/token/refresh",
):
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        if refresh_token is not None:
            client.cookies.set(REFRESH_COOKIE_NAME, refresh_token, path=REFRESH_COOKIE_PATH)
        headers = {"Authorization": f"Bearer {access_token}"} if access_token is not None else {}
        return await client.request(method, path, headers=headers)


@pytest.mark.asyncio
async def test_refresh_rejects_an_access_token_in_the_refresh_cookie(app: FastAPI) -> None:
    response = await _request(app, refresh_token=_access_token(7))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_an_admin_refresh_token(app: FastAPI) -> None:
    response = await _request(app, refresh_token=str(RefreshToken.for_admin(7)))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_checks_the_user_is_still_active(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_user(_repo: UserRepository, user_id: int):
        return _user(user_id, status=AccountStatus.SUSPENDED)

    monkeypatch.setattr(UserRepository, "get_user", get_user)
    response = await _request(app, refresh_token=_refresh_token(7))

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_rejects_a_deleted_user(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_user(_repo: UserRepository, _user_id: int):
        return None

    monkeypatch.setattr(UserRepository, "get_user", get_user)
    response = await _request(app, refresh_token=_refresh_token(7))

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_accepts_a_matching_expired_bearer_and_disables_caching(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def get_user(_repo: UserRepository, user_id: int):
        return _user(user_id)

    monkeypatch.setattr(UserRepository, "get_user", get_user)
    refresh_token, access_token = _token_pair(7, expired_access=True)
    response = await _request(app, refresh_token=refresh_token, access_token=access_token)

    assert response.status_code == 200
    issued = AccessToken(token=response.json()["access_token"])
    assert issued.payload["sub"] == "7"
    assert issued.payload["scope"] == JwtScope.USER
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_refresh_rejects_a_different_user_bearer(app: FastAPI) -> None:
    refresh_token, _access_token_7 = _token_pair(7)
    _refresh_token_8, access_token = _token_pair(8)
    response = await _request(app, refresh_token=refresh_token, access_token=access_token)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_refresh_rejects_a_missing_cookie(app: FastAPI) -> None:
    response = await _request(app, refresh_token=None, access_token=_access_token(7))

    assert response.status_code == 401


def test_generic_jwt_verifier_keeps_its_existing_invalid_token_status() -> None:
    with pytest.raises(HTTPException) as caught:
        JwtService().verify_jwt("not-a-jwt", "access")

    assert caught.value.status_code == 400


def test_access_token_carries_the_refresh_session_id() -> None:
    refresh = RefreshToken.for_user(_user(7))

    access = refresh.access_token

    assert access.payload["session_id"] == refresh.payload["jti"]


@pytest.mark.asyncio
async def test_logout_deletes_the_user_refresh_cookie(app: FastAPI) -> None:
    refresh_token, access_token = _token_pair(7)
    response = await _request(
        app,
        refresh_token=refresh_token,
        access_token=access_token,
        method="POST",
        path="/api/v1/auth/logout",
    )

    assert response.status_code == 200
    assert f'{REFRESH_COOKIE_NAME}=""' in response.headers["set-cookie"]
    assert f"Path={REFRESH_COOKIE_PATH}" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_stale_tab_logout_does_not_delete_a_different_users_cookie(app: FastAPI) -> None:
    refresh_token, _access_token_8 = _token_pair(8)
    _refresh_token_7, access_token = _token_pair(7, expired_access=True)
    response = await _request(
        app,
        refresh_token=refresh_token,
        access_token=access_token,
        method="POST",
        path="/api/v1/auth/logout",
    )

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_refresh_rejects_an_older_session_for_the_same_user(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def get_user(_repo: UserRepository, user_id: int):
        return _user(user_id)

    monkeypatch.setattr(UserRepository, "get_user", get_user)
    new_refresh, _new_access = _token_pair(7)
    _old_refresh, old_access = _token_pair(7)

    response = await _request(app, refresh_token=new_refresh, access_token=old_access)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_stale_same_user_logout_does_not_delete_the_new_session_cookie(app: FastAPI) -> None:
    new_refresh, _new_access = _token_pair(7)
    _old_refresh, old_access = _token_pair(7, expired_access=True)

    response = await _request(
        app,
        refresh_token=new_refresh,
        access_token=old_access,
        method="POST",
        path="/api/v1/auth/logout",
    )

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_same_user_login_reuses_refresh_session_without_extending_its_expiry(app: FastAPI) -> None:
    user = _user(7)

    class FakeAuthService:
        async def authenticate(self, _request):
            return user

        async def login(self, authenticated_user):
            return JwtService().issue_jwt_pair(authenticated_user)

    app.dependency_overrides[AuthService] = FakeAuthService
    existing = RefreshToken.for_user(user)
    existing.set_exp(lifetime=timedelta(minutes=5))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(REFRESH_COOKIE_NAME, str(existing), path=REFRESH_COOKIE_PATH)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "same-user@example.com", "password": "Password123!"},
        )

    returned = RefreshToken(token=response.cookies[REFRESH_COOKIE_NAME])
    assert returned.payload["jti"] == existing.payload["jti"]
    max_age = re.search(r"Max-Age=(\d+)", response.headers["set-cookie"])
    assert max_age is not None
    assert 1 <= int(max_age.group(1)) <= 300


@pytest.mark.asyncio
async def test_different_user_login_rotates_the_refresh_session(app: FastAPI) -> None:
    user = _user(7)

    class FakeAuthService:
        async def authenticate(self, _request):
            return user

    app.dependency_overrides[AuthService] = FakeAuthService
    other_users_refresh = RefreshToken.for_user(_user(8))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(REFRESH_COOKIE_NAME, str(other_users_refresh), path=REFRESH_COOKIE_PATH)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "new-user@example.com", "password": "Password123!"},
        )

    returned_refresh = RefreshToken(token=response.cookies[REFRESH_COOKIE_NAME])
    returned_access = AccessToken(token=response.json()["access_token"])
    assert returned_refresh.payload["jti"] != other_users_refresh.payload["jti"]
    assert returned_access.payload["session_id"] == returned_refresh.payload["jti"]
