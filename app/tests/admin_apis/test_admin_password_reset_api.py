from unittest.mock import patch

from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME
from app.core.email.backends import EmailMessage, EmailSendError
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


def reset_url(admin_id: int) -> str:
    return f"/api/v1/admin/accounts/{admin_id}/password/reset"


def read_temporary_password(message: EmailMessage) -> str:
    return next(line.split(":", 1)[1].strip() for line in message.body.splitlines() if "임시 비밀번호" in line)


class AdminPasswordResetTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.actor = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.target = await create_admin(
            name="한지수",
            email="jisu@ozcoding.ai",
            role=AdminRole.STAFF,
            created_by_admin_id=self.actor.id,
        )
        self.headers = auth_header(self.actor.id)


class TestAdminPasswordResetAPI(AdminPasswordResetTestBase):
    async def test_resets_password_and_reports_email_sent(self) -> None:
        response = await request("POST", reset_url(self.target.id), headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "adminId": self.target.id,
            "email": "jisu@ozcoding.ai",
            "status": "PENDING",
            "emailSent": True,
        }

    async def test_active_admin_returns_to_pending(self) -> None:
        """임시 비밀번호를 다시 받았으므로 활성 계정도 PENDING 으로 돌아간다."""
        assert self.target.status == AccountStatus.ACTIVE

        await request("POST", reset_url(self.target.id), headers=self.headers)

        await self.target.refresh_from_db()
        assert self.target.status == AccountStatus.PENDING

    async def test_clears_approved_at(self) -> None:
        """PENDING 으로 돌아갔는데 승인 시각이 남아 있으면 목록에서 모순으로 보인다."""
        await Admin.filter(id=self.target.id).update(approved_at="2026-01-01 00:00:00")

        await request("POST", reset_url(self.target.id), headers=self.headers)

        await self.target.refresh_from_db()
        assert self.target.approved_at is None

    async def test_changes_stored_password(self) -> None:
        await request("POST", reset_url(self.target.id), headers=self.headers)

        await self.target.refresh_from_db()
        assert not verify_password(ADMIN_PASSWORD, self.target.hashed_password)
        assert self.target.hashed_password.startswith("$2")

    async def test_response_never_contains_plain_password(self) -> None:
        sent: list[EmailMessage] = []

        with patch("app.services.admin_email.email_backend") as backend:
            backend.send.side_effect = sent.append
            response = await request("POST", reset_url(self.target.id), headers=self.headers)

        temporary_password = read_temporary_password(sent[0])
        assert temporary_password not in response.text
        assert not any("password" in key.lower() for key in response.json())

    async def test_new_temporary_password_can_login(self) -> None:
        sent: list[EmailMessage] = []

        with patch("app.services.admin_email.email_backend") as backend:
            backend.send.side_effect = sent.append
            await request("POST", reset_url(self.target.id), headers=self.headers)

        login = await request(
            "POST",
            ADMIN_LOGIN_URL,
            json={"email": self.target.email, "password": read_temporary_password(sent[0])},
        )

        assert login.status_code == status.HTTP_200_OK
        assert login.json()["mustChangePassword"] is True

    async def test_keeps_new_password_when_sending_fails(self) -> None:
        """메일만 실패한 경우 비밀번호 변경은 되돌리지 않는다(등록 API 와 같은 정책)."""
        with patch("app.services.admin_email.email_backend") as backend:
            backend.send.side_effect = EmailSendError("smtp down")

            response = await request("POST", reset_url(self.target.id), headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["emailSent"] is False
        await self.target.refresh_from_db()
        assert not verify_password(ADMIN_PASSWORD, self.target.hashed_password)
        assert self.target.status == AccountStatus.PENDING

    async def test_returns_404_for_unknown_admin(self) -> None:
        response = await request("POST", reset_url(999999), headers=self.headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "ADMIN_NOT_FOUND"

    async def test_rejects_suspended_admin(self) -> None:
        """정지를 풀지 않고 비밀번호만 새로 주면 정지가 무의미해진다."""
        await Admin.filter(id=self.target.id).update(status=AccountStatus.SUSPENDED)

        response = await request("POST", reset_url(self.target.id), headers=self.headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_RESET_SUSPENDED"
        await self.target.refresh_from_db()
        assert verify_password(ADMIN_PASSWORD, self.target.hashed_password)

    async def test_rejects_withdrawn_admin(self) -> None:
        await Admin.filter(id=self.target.id).update(status=AccountStatus.WITHDRAWN)

        response = await request("POST", reset_url(self.target.id), headers=self.headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_RESET_WITHDRAWN"

    async def test_staff_cannot_reset(self) -> None:
        """재발송은 ADMIN 전용이다(권한 매트릭스)."""
        staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request("POST", reset_url(self.target.id), headers=auth_header(staff.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"

    async def test_requires_authentication(self) -> None:
        response = await request("POST", reset_url(self.target.id))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPasswordResetInvalidatesSessions(AdminPasswordResetTestBase):
    async def test_existing_refresh_token_stops_working(self) -> None:
        """재발송은 계정을 넘겨받는 상황이라 이전 세션이 살아 있으면 안 된다."""
        login = await request("POST", ADMIN_LOGIN_URL, json={"email": self.target.email, "password": ADMIN_PASSWORD})
        cookies = {REFRESH_COOKIE_NAME: login.cookies[REFRESH_COOKIE_NAME]}
        assert (await request("POST", ADMIN_REFRESH_URL, cookies=cookies)).status_code == status.HTTP_200_OK

        await request("POST", reset_url(self.target.id), headers=self.headers)

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)
        assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}

    async def test_actor_session_is_not_affected(self) -> None:
        login = await request("POST", ADMIN_LOGIN_URL, json={"email": self.actor.email, "password": ADMIN_PASSWORD})
        cookies = {REFRESH_COOKIE_NAME: login.cookies[REFRESH_COOKIE_NAME]}

        await request("POST", reset_url(self.target.id), headers=self.headers)

        response = await request("POST", ADMIN_REFRESH_URL, cookies=cookies)
        assert response.status_code == status.HTTP_200_OK
