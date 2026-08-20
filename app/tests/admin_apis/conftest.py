from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response

from app.core.jwt.tokens import AccessToken
from app.core.utils.security import hash_password
from app.main import app
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.models.users import User, UserSettings

BASE_URL = "http://test"
ADMIN_ACCOUNTS_URL = "/api/v1/admin/accounts"
ADMIN_STATUS_URL = "/api/v1/admin/accounts/status"
ADMIN_USERS_URL = "/api/v1/admin/users"
ADMIN_LOGIN_URL = "/api/v1/admin/auth/login"
ADMIN_REFRESH_URL = "/api/v1/admin/auth/refresh"
ADMIN_LOGOUT_URL = "/api/v1/admin/auth/logout"

ADMIN_PASSWORD = "Password123!"


def auth_header(admin_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {AccessToken.for_admin(admin_id)}"}


async def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    cookies: dict[str, str] | None = None,
) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL, cookies=cookies) as client:
        return await client.request(method, url, headers=headers, params=params, json=json)


async def create_admin(
    *,
    name: str,
    email: str,
    role: AdminRole = AdminRole.STAFF,
    status: AccountStatus = AccountStatus.ACTIVE,
    created_by_admin_id: int | None = None,
) -> Admin:
    return await Admin.create(
        name=name,
        email=email,
        hashed_password=hash_password(ADMIN_PASSWORD),
        role=role,
        status=status,
        created_by_admin_id=created_by_admin_id,
    )


async def create_user(
    *,
    name: str,
    email: str,
    status: AccountStatus = AccountStatus.ACTIVE,
    phone: str | None = None,
    is_terms_agreed: bool | None = None,
) -> User:
    user = await User.create(
        name=name,
        email=email,
        hashed_password=hash_password("Password123!"),
        status=status,
        phone=phone,
    )
    # is_terms_agreed 를 넘기지 않으면 설정 행 자체를 만들지 않는다.
    # 가입 직후 사용자를 재현해 미동의(false) 처리가 되는지 확인하기 위함이다.
    if is_terms_agreed is not None:
        await UserSettings.create(user=user, is_terms_agreed=is_terms_agreed)
    return user


@pytest_asyncio.fixture
async def super_admin() -> Admin:
    """요청 주체로 쓰는 활성 ADMIN. 마지막 활성 ADMIN 이기도 하다."""
    return await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)


@pytest_asyncio.fixture
async def staff(super_admin: Admin) -> Admin:
    return await create_admin(
        name="김진형",
        email="jinhyeong@ozcoding.ai",
        role=AdminRole.STAFF,
        created_by_admin_id=super_admin.id,
    )
