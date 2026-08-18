from typing import Any

from httpx import ASGITransport, AsyncClient
from starlette import status

from app.core.jwt.tokens import AccessToken
from app.main import app

BASE_URL = "http://test"
ADMIN_ACCOUNTS_URL = "/api/v1/admin/accounts"
ADMIN_USERS_URL = "/api/v1/admin/users"


def auth_header() -> dict[str, str]:
    token = AccessToken()
    token["user_id"] = 1
    return {"Authorization": f"Bearer {token}"}


async def get(url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL) as client:
        return await client.get(url, headers=headers, params=params)


class TestAdminListAPI:
    async def test_returns_paginated_admins(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers=auth_header())

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["totalCount"] == len(body["items"])
        assert body["page"] == 1
        assert body["size"] == 20

    async def test_item_uses_camel_case_and_upper_case_enum(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers=auth_header())

        item = response.json()["items"][0]
        assert set(item) == {"adminId", "name", "email", "role", "status"}
        assert item["role"] in {"ADMIN", "STAFF"}
        assert item["status"] in {"PENDING", "ACTIVE", "SUSPENDED", "WITHDRAWN"}

    async def test_filters_by_role(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers=auth_header(), params={"role": "STAFF"})

        body = response.json()
        assert body["totalCount"] >= 1
        assert all(item["role"] == "STAFF" for item in body["items"])

    async def test_filters_by_keyword(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers=auth_header(), params={"keyword": "eunmi@"})

        body = response.json()
        assert all("eunmi@" in item["email"] for item in body["items"])

    async def test_rejects_unknown_role(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers=auth_header(), params={"role": "SUPER"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"


class TestAdminDetailAPI:
    async def test_returns_admin_detail(self) -> None:
        response = await get(f"{ADMIN_ACCOUNTS_URL}/1", headers=auth_header())

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["adminId"] == 1
        assert set(body) == {
            "adminId",
            "name",
            "email",
            "role",
            "status",
            "createdByAdminId",
            "approvedAt",
            "createdAt",
        }

    async def test_allows_null_created_by_for_first_super_admin(self) -> None:
        """최초 슈퍼 ADMIN 은 생성자가 없다(admin.id 자기 참조, nullable)."""
        response = await get(f"{ADMIN_ACCOUNTS_URL}/1", headers=auth_header())

        assert response.json()["createdByAdminId"] is None

    async def test_returns_404_for_unknown_admin(self) -> None:
        response = await get(f"{ADMIN_ACCOUNTS_URL}/999999", headers=auth_header())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"code": "ADMIN_NOT_FOUND", "message": "관리자를 찾을 수 없습니다."}


class TestUserListAPI:
    async def test_returns_paginated_users(self) -> None:
        response = await get(ADMIN_USERS_URL, headers=auth_header())

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["totalCount"] == len(body["items"])
        assert set(body["items"][0]) == {"userId", "name", "email", "status", "createdAt"}

    async def test_filters_by_status(self) -> None:
        response = await get(ADMIN_USERS_URL, headers=auth_header(), params={"status": "PENDING"})

        body = response.json()
        assert all(item["status"] == "PENDING" for item in body["items"])

    async def test_rejects_reversed_date_range(self) -> None:
        response = await get(
            ADMIN_USERS_URL,
            headers=auth_header(),
            params={"startDate": "2026-01-01", "endDate": "2025-01-01"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_size_over_limit(self) -> None:
        response = await get(ADMIN_USERS_URL, headers=auth_header(), params={"size": 999})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["field"] == "size"


class TestUserDetailAPI:
    async def test_returns_user_detail(self) -> None:
        response = await get(f"{ADMIN_USERS_URL}/9201", headers=auth_header())

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["userId"] == 9201
        assert set(body) == {
            "userId",
            "name",
            "email",
            "phone",
            "status",
            "isTermsAgreed",
            "createdAt",
            "activeAlarmCount",
        }

    async def test_returns_terms_agreement_flag(self) -> None:
        """ERD v3 에서 user_consents 테이블이 is_terms_agreed 로 대체됐다."""
        agreed = await get(f"{ADMIN_USERS_URL}/9201", headers=auth_header())
        not_agreed = await get(f"{ADMIN_USERS_URL}/9202", headers=auth_header())

        assert agreed.json()["isTermsAgreed"] is True
        assert not_agreed.json()["isTermsAgreed"] is False

    async def test_returns_active_alarm_count(self) -> None:
        response = await get(f"{ADMIN_USERS_URL}/9201", headers=auth_header())

        assert isinstance(response.json()["activeAlarmCount"], int)

    async def test_returns_404_for_unknown_user(self) -> None:
        response = await get(f"{ADMIN_USERS_URL}/999999", headers=auth_header())

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}


class TestAdminApiAuthentication:
    async def test_requires_authorization_header(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"code": "UNAUTHORIZED", "message": "인증이 필요합니다."}

    async def test_rejects_malformed_token(self) -> None:
        response = await get(ADMIN_ACCOUNTS_URL, headers={"Authorization": "Bearer not-a-jwt"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_every_admin_endpoint_requires_authentication(self) -> None:
        urls = [
            ADMIN_ACCOUNTS_URL,
            f"{ADMIN_ACCOUNTS_URL}/1",
            ADMIN_USERS_URL,
            f"{ADMIN_USERS_URL}/9201",
        ]

        for url in urls:
            response = await get(url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, url
