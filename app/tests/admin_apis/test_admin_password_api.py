from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME
from app.core.utils.security import verify_password
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.tests.admin_apis.conftest import (
    ADMIN_LOGIN_URL,
    ADMIN_PASSWORD,
    ADMIN_REFRESH_URL,
    auth_header,
    create_admin,
    request,
)

ADMIN_PASSWORD_URL = "/api/v1/admin/accounts/password"
NEW_PASSWORD = "newSecure123!"


def change_payload(current: str = ADMIN_PASSWORD, new: str = NEW_PASSWORD) -> dict[str, str]:
    return {"currentPassword": current, "newPassword": new}


class AdminPasswordTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)


class TestAdminPasswordChangeAPI(AdminPasswordTestBase):
    async def test_active_admin_changes_password(self) -> None:
        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"message": "비밀번호가 변경되었습니다.", "status": "ACTIVE"}

    async def test_active_admin_status_is_unchanged(self) -> None:
        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        await self.admin.refresh_from_db()
        assert self.admin.status == AccountStatus.ACTIVE
        # ACTIVE 계정은 승인 시각을 새로 찍지 않는다.
        assert self.admin.approved_at is None

    async def test_stores_new_password_as_hash(self) -> None:
        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        await self.admin.refresh_from_db()
        assert self.admin.hashed_password.startswith("$2")
        assert NEW_PASSWORD not in self.admin.hashed_password
        assert verify_password(NEW_PASSWORD, self.admin.hashed_password)

    async def test_never_returns_password(self) -> None:
        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        body = response.json()
        assert not any("password" in key.lower() for key in body)
        assert NEW_PASSWORD not in response.text
        assert ADMIN_PASSWORD not in response.text

    async def test_pending_admin_becomes_active(self) -> None:
        """임시 비밀번호를 바꾸면 계정이 활성화된다(REQ-ADMIN-009)."""
        pending = await create_admin(
            name="한지수",
            email="jisu@ozcoding.ai",
            status=AccountStatus.PENDING,
            created_by_admin_id=self.admin.id,
        )

        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(pending.id), json=change_payload())

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "ACTIVE"
        await pending.refresh_from_db()
        assert pending.status == AccountStatus.ACTIVE
        assert pending.approved_at is not None

    async def test_pending_admin_can_use_other_apis_after_change(self) -> None:
        """변경 전에는 다른 관리자 API 가 막혀 있어야 하고, 변경 후에는 열려야 한다."""
        pending = await create_admin(
            name="한지수",
            email="jisu@ozcoding.ai",
            status=AccountStatus.PENDING,
            created_by_admin_id=self.admin.id,
        )
        headers = auth_header(pending.id)

        before = await request("GET", "/api/v1/admin/accounts", headers=headers)
        assert before.status_code == status.HTTP_403_FORBIDDEN

        await request("PATCH", ADMIN_PASSWORD_URL, headers=headers, json=change_payload())

        after = await request("GET", "/api/v1/admin/accounts", headers=headers)
        assert after.status_code == status.HTTP_200_OK

    async def test_suspended_admin_cannot_change_password(self) -> None:
        """정지된 계정이 비밀번호 변경으로 되살아나면 안 된다."""
        suspended = await create_admin(name="정지됨", email="suspended@ozcoding.ai", status=AccountStatus.SUSPENDED)

        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(suspended.id), json=change_payload())

        assert response.status_code == status.HTTP_403_FORBIDDEN
        await suspended.refresh_from_db()
        assert suspended.status == AccountStatus.SUSPENDED
        assert verify_password(ADMIN_PASSWORD, suspended.hashed_password)

    async def test_withdrawn_admin_cannot_change_password(self) -> None:
        withdrawn = await create_admin(name="탈퇴됨", email="withdrawn@ozcoding.ai", status=AccountStatus.WITHDRAWN)

        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(withdrawn.id), json=change_payload())

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_rejects_wrong_current_password(self) -> None:
        response = await request(
            "PATCH",
            ADMIN_PASSWORD_URL,
            headers=auth_header(self.admin.id),
            json=change_payload(current="WrongPassword1!"),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_PASSWORD"
        await self.admin.refresh_from_db()
        assert verify_password(ADMIN_PASSWORD, self.admin.hashed_password)

    async def test_rejects_new_password_same_as_current(self) -> None:
        response = await request(
            "PATCH",
            ADMIN_PASSWORD_URL,
            headers=auth_header(self.admin.id),
            json=change_payload(new=ADMIN_PASSWORD),
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "SAME_AS_CURRENT"

    async def test_rejects_short_new_password(self) -> None:
        response = await request(
            "PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload(new="short1!")
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["field"] == "newPassword"
        assert body["message"] == "비밀번호는 8자 이상이어야 합니다."

    async def test_requires_authentication(self) -> None:
        response = await request("PATCH", ADMIN_PASSWORD_URL, json=change_payload())

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_does_not_accept_target_admin_id(self) -> None:
        """대상은 토큰의 sub 로만 정한다. 본문에 다른 ID 를 넣어도 무시된다."""
        other = await create_admin(name="다른관리자", email="other@ozcoding.ai")
        payload = {**change_payload(), "adminId": other.id}

        response = await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=payload)

        assert response.status_code == status.HTTP_200_OK
        await other.refresh_from_db()
        assert verify_password(ADMIN_PASSWORD, other.hashed_password)


class TestPasswordChangeInvalidatesSessions(AdminPasswordTestBase):
    async def _login_cookies(self) -> dict[str, str]:
        response = await request("POST", ADMIN_LOGIN_URL, json={"email": self.admin.email, "password": ADMIN_PASSWORD})
        return {REFRESH_COOKIE_NAME: response.cookies[REFRESH_COOKIE_NAME]}

    async def test_old_refresh_token_stops_working(self) -> None:
        """계정 노출이 의심돼 비밀번호를 바꾸는 경우라, 다른 기기 세션도 끊겨야 한다."""
        cookies = await self._login_cookies()
        assert (await request("POST", ADMIN_REFRESH_URL, cookies=cookies)).status_code == status.HTTP_200_OK

        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "INVALID_TOKEN"

    async def test_new_login_works_with_new_password(self) -> None:
        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        response = await request("POST", ADMIN_LOGIN_URL, json={"email": self.admin.email, "password": NEW_PASSWORD})

        assert response.status_code == status.HTTP_200_OK

    async def test_old_password_no_longer_works(self) -> None:
        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        response = await request("POST", ADMIN_LOGIN_URL, json={"email": self.admin.email, "password": ADMIN_PASSWORD})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_other_admin_session_is_not_affected(self) -> None:
        """본인 비밀번호 변경이 다른 관리자의 세션까지 끊으면 안 된다."""
        other = await create_admin(name="다른관리자", email="other@ozcoding.ai", role=AdminRole.ADMIN)
        login = await request("POST", ADMIN_LOGIN_URL, json={"email": other.email, "password": ADMIN_PASSWORD})
        other_cookies = {REFRESH_COOKIE_NAME: login.cookies[REFRESH_COOKIE_NAME]}

        await request("PATCH", ADMIN_PASSWORD_URL, headers=auth_header(self.admin.id), json=change_payload())

        response = await request("POST", ADMIN_REFRESH_URL, cookies=other_cookies)
        assert response.status_code == status.HTTP_200_OK
        assert await Admin.filter(id=other.id).exists()
