"""USER_REFRESH_ENABLED 가 꺼졌을 때(기본값)의 사용자 인증 동작.

자동 로그인을 쓰지 않기로 해 기본값이 False 다. 액세스 토큰이 만료되면 다시 로그인한다.
켠 상태의 동작은 test_token_api.py 가 검증한다.

관리자 리프레시는 이 플래그와 무관하게 항상 동작해야 하므로 여기서 함께 고정한다.
"""

from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME as ADMIN_COOKIE
from app.apis.v1.auth_routers import REFRESH_COOKIE_NAME as USER_COOKIE
from app.core import config
from app.core.utils.security import hash_password
from app.main import app
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.models.users import User

PASSWORD = "Password123!"


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def create_active_user(email: str = "norefresh@example.com") -> User:
    return await User.create(
        email=email, hashed_password=hash_password(PASSWORD), name="회원", status=AccountStatus.ACTIVE
    )


class TestUserRefreshDisabled(TestCase):
    """기본값(꺼짐)에서는 리프레시 쿠키도, 갱신 엔드포인트도 없다."""

    async def test_login_does_not_set_refresh_cookie(self) -> None:
        user = await create_active_user()

        async with client() as http:
            response = await http.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

        assert response.status_code == status.HTTP_200_OK
        assert USER_COOKIE not in response.cookies
        assert USER_COOKIE not in response.headers.get("set-cookie", "")

    async def test_login_still_returns_access_token(self) -> None:
        """리프레시만 빠질 뿐 로그인 자체는 그대로 동작해야 한다."""
        user = await create_active_user("norefresh2@example.com")

        async with client() as http:
            response = await http.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

        assert response.json()["access_token"]

    async def test_refresh_endpoint_returns_404(self) -> None:
        async with client() as http:
            response = await http.get("/api/v1/auth/token/refresh")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_refresh_returns_404_even_with_cookie(self) -> None:
        """쿠키를 손으로 넣어도 열리면 안 된다. 401 이 아니라 404 여야 한다."""
        async with client() as http:
            http.cookies[USER_COOKIE] = "any.jwt.value"
            response = await http.get("/api/v1/auth/token/refresh")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestAdminRefreshUnaffected(TestCase):
    """관리자 콘솔은 30분마다 재로그인하면 운영이 불가능하다. 플래그와 무관하게 동작해야 한다."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await Admin.create(
            email="admin-refresh@ozcoding.ai",
            hashed_password=hash_password(PASSWORD),
            name="관리자",
            role=AdminRole.ADMIN,
            status=AccountStatus.ACTIVE,
        )

    async def _login_and_refresh(self) -> tuple[int, str]:
        async with client() as http:
            login = await http.post("/api/v1/admin/auth/login", json={"email": self.admin.email, "password": PASSWORD})
            set_cookie = login.headers.get("set-cookie", "")
            refreshed = await http.post("/api/v1/admin/auth/refresh")
        return refreshed.status_code, set_cookie

    async def test_admin_refresh_works_while_user_refresh_is_off(self) -> None:
        assert config.USER_REFRESH_ENABLED is False

        code, set_cookie = await self._login_and_refresh()

        assert ADMIN_COOKIE in set_cookie
        assert code == status.HTTP_200_OK

    async def test_admin_refresh_works_while_user_refresh_is_on(self) -> None:
        with patch.object(config, "USER_REFRESH_ENABLED", True):
            code, set_cookie = await self._login_and_refresh()

        assert ADMIN_COOKIE in set_cookie
        assert code == status.HTTP_200_OK
