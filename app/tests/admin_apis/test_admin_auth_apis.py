from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME
from app.core.jwt.tokens import AccessToken, JwtScope
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.tests.admin_apis.conftest import (
    ADMIN_ACCOUNTS_URL,
    ADMIN_LOGIN_URL,
    ADMIN_LOGOUT_URL,
    ADMIN_PASSWORD,
    ADMIN_REFRESH_URL,
    ADMIN_STATUS_URL,
    auth_header,
    create_admin,
    create_user,
    request,
)


def credentials(email: str, password: str = ADMIN_PASSWORD) -> dict[str, str]:
    return {"email": email, "password": password}


class AdminAuthTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)

    async def login(self, email: str = "eunmi@ozcoding.ai", password: str = ADMIN_PASSWORD):  # type: ignore[no-untyped-def]
        return await request("POST", ADMIN_LOGIN_URL, json=credentials(email, password))


class TestAdminLoginAPI(AdminAuthTestBase):
    async def test_returns_access_token_and_admin_info(self) -> None:
        response = await self.login()

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert set(body) == {"accessToken", "admin", "mustChangePassword"}
        assert body["admin"] == {
            "adminId": self.admin.id,
            "name": "김은미",
            "email": "eunmi@ozcoding.ai",
            "role": "ADMIN",
        }

    async def test_never_returns_password(self) -> None:
        """비밀번호·해시가 응답에 실리지 않아야 한다.

        mustChangePassword 는 정상 필드이므로 값이 아닌 키 이름만 검사한다.
        """
        response = await self.login()

        body = response.json()
        assert set(body) == {"accessToken", "admin", "mustChangePassword"}
        assert not any("password" in key.lower() for key in body["admin"])
        assert ADMIN_PASSWORD not in response.text

    async def test_sets_refresh_token_as_http_only_cookie(self) -> None:
        """리프레시 토큰은 응답 본문이 아니라 http_only 쿠키로 전달한다(NFR-ADMIN-001)."""
        response = await self.login()

        assert REFRESH_COOKIE_NAME in response.cookies
        set_cookie = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "refreshToken" not in response.json()

    async def test_issued_token_carries_admin_scope(self) -> None:
        response = await self.login()

        token = AccessToken(token=response.json()["accessToken"])
        assert token.payload["scope"] == JwtScope.ADMIN
        assert int(token.payload["sub"]) == self.admin.id

    async def test_pending_admin_can_login_with_must_change_password(self) -> None:
        """임시 비밀번호 계정은 로그인만 허용하고 비밀번호 변경으로 유도한다."""
        pending = await create_admin(
            name="한지수", email="jisu@ozcoding.ai", status=AccountStatus.PENDING, created_by_admin_id=self.admin.id
        )

        response = await self.login(email=pending.email)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["mustChangePassword"] is True

    async def test_active_admin_does_not_need_password_change(self) -> None:
        response = await self.login()

        assert response.json()["mustChangePassword"] is False

    async def test_suspended_admin_cannot_login(self) -> None:
        suspended = await create_admin(name="정지됨", email="suspended@ozcoding.ai", status=AccountStatus.SUSPENDED)

        response = await self.login(email=suspended.email)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "ACCOUNT_SUSPENDED"

    async def test_withdrawn_admin_cannot_login(self) -> None:
        withdrawn = await create_admin(name="탈퇴됨", email="withdrawn@ozcoding.ai", status=AccountStatus.WITHDRAWN)

        response = await self.login(email=withdrawn.email)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "ACCOUNT_WITHDRAWN"

    async def test_unknown_email_and_wrong_password_are_indistinguishable(self) -> None:
        """이메일 존재 여부가 새어나가지 않도록 응답을 동일하게 유지한다."""
        unknown = await self.login(email="nobody@ozcoding.ai")
        wrong_password = await self.login(password="WrongPassword1!")

        assert unknown.status_code == wrong_password.status_code == status.HTTP_401_UNAUTHORIZED
        assert unknown.json() == wrong_password.json()
        assert unknown.json()["code"] == "INVALID_CREDENTIALS"

    async def test_rejects_invalid_email_format(self) -> None:
        response = await request("POST", ADMIN_LOGIN_URL, json={"email": "not-an-email", "password": "x"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestAdminRefreshAPI(AdminAuthTestBase):
    async def _login_cookies(self) -> dict[str, str]:
        response = await self.login()
        return {REFRESH_COOKIE_NAME: response.cookies[REFRESH_COOKIE_NAME]}

    async def test_issues_new_access_token(self) -> None:
        response = await request("POST", ADMIN_REFRESH_URL, cookies=await self._login_cookies())

        assert response.status_code == status.HTTP_200_OK
        assert set(response.json()) == {"accessToken"}

    async def test_reissued_token_keeps_admin_scope(self) -> None:
        response = await request("POST", ADMIN_REFRESH_URL, cookies=await self._login_cookies())

        token = AccessToken(token=response.json()["accessToken"])
        assert token.payload["scope"] == JwtScope.ADMIN
        assert int(token.payload["sub"]) == self.admin.id

    async def test_rejects_missing_cookie(self) -> None:
        response = await request("POST", ADMIN_REFRESH_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "INVALID_TOKEN"

    async def test_rejects_malformed_cookie(self) -> None:
        response = await request("POST", ADMIN_REFRESH_URL, cookies={REFRESH_COOKIE_NAME: "not-a-jwt"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "INVALID_TOKEN"

    async def test_rejects_admin_suspended_after_login(self) -> None:
        """로그인 이후 정지된 계정이 갱신만으로 접근을 이어가면 안 된다."""
        cookies = await self._login_cookies()
        await Admin.filter(id=self.admin.id).update(status=AccountStatus.SUSPENDED)

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "ACCOUNT_SUSPENDED"


class TestAdminLogoutAPI(AdminAuthTestBase):
    async def test_deletes_refresh_cookie(self) -> None:
        response = await request("POST", ADMIN_LOGOUT_URL, headers=auth_header(self.admin.id))

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "로그아웃되었습니다."}
        # 삭제는 만료된 Set-Cookie 로 전달된다.
        assert REFRESH_COOKIE_NAME in response.headers["set-cookie"]

    async def test_requires_authentication(self) -> None:
        response = await request("POST", ADMIN_LOGOUT_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminTokenScope(AdminAuthTestBase):
    async def test_rejects_token_without_scope(self) -> None:
        """scope 클레임이 없는 구버전 토큰은 거부한다."""
        legacy = AccessToken()
        legacy["sub"] = str(self.admin.id)

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers={"Authorization": f"Bearer {legacy}"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"

    async def test_rejects_user_scope_token(self) -> None:
        """사용자 토큰으로는 관리자 API 를 호출할 수 없다."""
        user = await create_user(name="홍길동", email="user@mail.com")
        user_token = AccessToken()
        user_token["sub"] = str(user.id)
        user_token["scope"] = JwtScope.USER

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers={"Authorization": f"Bearer {user_token}"})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_rejects_user_scope_token_even_when_id_matches_admin(self) -> None:
        """user 와 admin 은 별도 테이블이라 id 가 겹칠 수 있다. scope 로 구분해야 한다."""
        colliding = AccessToken()
        colliding["sub"] = str(self.admin.id)
        colliding["scope"] = JwtScope.USER

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers={"Authorization": f"Bearer {colliding}"})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_accepts_admin_scope_token(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=auth_header(self.admin.id))

        assert response.status_code == status.HTTP_200_OK


class TestRefreshRechecksAccountStatus(AdminAuthTestBase):
    """세션 무효화 난수를 두지 않으므로, 정지 차단은 갱신 시점의 상태 재확인에만 의존한다."""

    async def _login_cookies(self, email: str, password: str = ADMIN_PASSWORD) -> dict[str, str]:
        response = await request("POST", ADMIN_LOGIN_URL, json=credentials(email, password))
        return {REFRESH_COOKIE_NAME: response.cookies[REFRESH_COOKIE_NAME]}

    async def test_suspension_blocks_refresh(self) -> None:
        """정지되면 리프레시 토큰이 유효해도 갱신이 막힌다."""
        target = await create_admin(name="정지대상", email="target@ozcoding.ai", role=AdminRole.STAFF)
        cookies = await self._login_cookies(target.email)
        assert (await request("POST", ADMIN_REFRESH_URL, cookies=cookies)).status_code == status.HTTP_200_OK

        await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(self.admin.id),
            json={"adminIds": [target.id], "status": "SUSPENDED"},
        )

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "ACCOUNT_SUSPENDED"

    async def test_unsuspension_restores_refresh(self) -> None:
        """상태만 보고 판단하므로 해제하면 같은 토큰으로 다시 갱신된다."""
        target = await create_admin(name="해제대상", email="back@ozcoding.ai", role=AdminRole.STAFF)
        cookies = await self._login_cookies(target.email)

        for new_status in ("SUSPENDED", "ACTIVE"):
            await request(
                "PATCH",
                ADMIN_STATUS_URL,
                headers=auth_header(self.admin.id),
                json={"adminIds": [target.id], "status": new_status},
            )

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)
        assert response.status_code == status.HTTP_200_OK

    async def test_other_admin_session_survives(self) -> None:
        """한 계정을 정지해도 다른 계정 세션까지 끊으면 안 된다."""
        other = await create_admin(name="다른관리자", email="other@ozcoding.ai", role=AdminRole.STAFF)
        other_cookies = await self._login_cookies(other.email)

        target = await create_admin(name="정지대상", email="target@ozcoding.ai", role=AdminRole.STAFF)
        await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(self.admin.id),
            json={"adminIds": [target.id], "status": "SUSPENDED"},
        )

        response = await request("POST", ADMIN_REFRESH_URL, cookies=other_cookies)
        assert response.status_code == status.HTTP_200_OK
