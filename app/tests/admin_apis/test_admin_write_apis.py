import copy
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status

from app.core.jwt.tokens import AccessToken
from app.main import app
from app.models.enums import AccountStatus, AdminRole
from app.services import admins as admin_service

BASE_URL = "http://test"
ADMIN_ACCOUNTS_URL = "/api/v1/admin/accounts"
ADMIN_STATUS_URL = "/api/v1/admin/accounts/status"

SUPER_ADMIN_ID = 1
STAFF_ID = 2


def auth_header(admin_id: int = SUPER_ADMIN_ID) -> dict[str, str]:
    token = AccessToken()
    token["user_id"] = admin_id
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def restore_mock_admins() -> Iterator[None]:
    """쓰기 API 는 목 리스트를 직접 바꾸므로 테스트마다 원복한다."""
    original = copy.deepcopy(admin_service._MOCK_ADMINS)
    yield
    admin_service._MOCK_ADMINS[:] = original


async def post(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.post(url, json=payload, headers=headers)


async def patch(url: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.patch(url, json=payload, headers=headers)


class TestAdminCreateAPI:
    payload = {"name": "한지수", "email": "jisu@ozcoding.ai", "role": "STAFF", "isActive": True}

    async def test_creates_admin(self) -> None:
        response = await post(ADMIN_ACCOUNTS_URL, self.payload, headers=auth_header())

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["name"] == "한지수"
        assert body["role"] == "STAFF"
        assert body["status"] == "ACTIVE"
        assert body["createdByAdminId"] == SUPER_ADMIN_ID

    async def test_never_returns_password(self) -> None:
        """임시 비밀번호는 이메일로만 전달하며 응답에 포함하지 않는다."""
        response = await post(ADMIN_ACCOUNTS_URL, self.payload, headers=auth_header())

        assert not any("password" in key.lower() for key in response.json())

    async def test_inactive_flag_creates_pending_admin(self) -> None:
        payload = {**self.payload, "isActive": False}

        response = await post(ADMIN_ACCOUNTS_URL, payload, headers=auth_header())

        assert response.json()["status"] == "PENDING"

    async def test_rejects_duplicate_email(self) -> None:
        payload = {**self.payload, "email": "eunmi@ozcoding.ai"}

        response = await post(ADMIN_ACCOUNTS_URL, payload, headers=auth_header())

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "EMAIL_ALREADY_EXISTS"

    async def test_rejects_invalid_email_format(self) -> None:
        payload = {**self.payload, "email": "not-an-email"}

        response = await post(ADMIN_ACCOUNTS_URL, payload, headers=auth_header())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_unknown_role(self) -> None:
        payload = {**self.payload, "role": "SUPER"}

        response = await post(ADMIN_ACCOUNTS_URL, payload, headers=auth_header())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_requires_authentication(self) -> None:
        response = await post(ADMIN_ACCOUNTS_URL, self.payload)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminStatusUpdateAPI:
    async def test_suspends_multiple_admins(self) -> None:
        response = await patch(ADMIN_STATUS_URL, {"adminIds": [STAFF_ID], "status": "SUSPENDED"}, headers=auth_header())

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"updatedCount": 1, "status": "SUSPENDED", "adminIds": [STAFF_ID]}

    async def test_rejects_suspending_self(self) -> None:
        response = await patch(
            ADMIN_STATUS_URL, {"adminIds": [SUPER_ADMIN_ID], "status": "SUSPENDED"}, headers=auth_header()
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_SUSPEND_SELF"

    async def test_rejects_suspending_last_active_admin(self) -> None:
        """활성 ADMIN 이 0명이 되면 아무도 콘솔에 들어올 수 없다."""
        admin_service._MOCK_ADMINS.append(
            {
                "admin_id": 50,
                "name": "부관리자",
                "email": "sub@ozcoding.ai",
                "role": AdminRole.ADMIN,
                "status": AccountStatus.SUSPENDED,
                "created_by_admin_id": SUPER_ADMIN_ID,
                "approved_at": None,
                "created_at": datetime(2026, 1, 1),
            }
        )

        response = await patch(
            ADMIN_STATUS_URL, {"adminIds": [SUPER_ADMIN_ID], "status": "SUSPENDED"}, headers=auth_header(50)
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "LAST_ACTIVE_ADMIN"

    async def test_rollbacks_when_any_id_is_missing(self) -> None:
        """부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다."""
        response = await patch(
            ADMIN_STATUS_URL, {"adminIds": [STAFF_ID, 999999], "status": "SUSPENDED"}, headers=auth_header()
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "ADMIN_NOT_FOUND"
        staff = next(row for row in admin_service._MOCK_ADMINS if row["admin_id"] == STAFF_ID)
        assert staff["status"] != AccountStatus.SUSPENDED

    async def test_reactivation_is_not_blocked_by_invariant(self) -> None:
        response = await patch(ADMIN_STATUS_URL, {"adminIds": [STAFF_ID], "status": "ACTIVE"}, headers=auth_header())

        assert response.status_code == status.HTTP_200_OK

    async def test_rejects_empty_id_list(self) -> None:
        response = await patch(ADMIN_STATUS_URL, {"adminIds": [], "status": "SUSPENDED"}, headers=auth_header())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_rejects_status_other_than_active_or_suspended(self) -> None:
        """계정 삭제 기능은 없으므로 WITHDRAWN 등으로는 바꿀 수 없다."""
        response = await patch(ADMIN_STATUS_URL, {"adminIds": [STAFF_ID], "status": "WITHDRAWN"}, headers=auth_header())

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_requires_authentication(self) -> None:
        response = await patch(ADMIN_STATUS_URL, {"adminIds": [STAFF_ID], "status": "SUSPENDED"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
