from starlette import status
from tortoise.contrib.test import TestCase

from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.tests.admin_apis.conftest import (
    ADMIN_ACCOUNTS_URL,
    ADMIN_USERS_URL,
    auth_header,
    create_admin,
    create_user,
    request,
)


class AdminQueryTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.super_admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.staff = await create_admin(
            name="김진형",
            email="jinhyeong@ozcoding.ai",
            role=AdminRole.STAFF,
            status=AccountStatus.PENDING,
            created_by_admin_id=self.super_admin.id,
        )
        self.headers = auth_header(self.super_admin.id)


class TestAdminListAPI(AdminQueryTestBase):
    async def test_returns_paginated_admins(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["totalCount"] == 2
        assert body["page"] == 1
        assert body["size"] == 20

    async def test_item_uses_camel_case_and_upper_case_enum(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers)

        item = response.json()["items"][0]
        assert set(item) == {"adminId", "name", "email", "role", "status"}
        assert item["role"] in {"ADMIN", "STAFF"}
        assert item["status"] in {"PENDING", "ACTIVE", "SUSPENDED", "WITHDRAWN"}

    async def test_filters_by_role(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers, params={"role": "STAFF"})

        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["adminId"] == self.staff.id

    async def test_filters_by_status(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers, params={"status": "PENDING"})

        assert response.json()["totalCount"] == 1

    async def test_filters_by_keyword(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers, params={"keyword": "eunmi@"})

        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["email"] == "eunmi@ozcoding.ai"

    async def test_paginates(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers, params={"page": 2, "size": 1})

        body = response.json()
        assert body["totalCount"] == 2
        assert len(body["items"]) == 1

    async def test_rejects_unknown_role(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=self.headers, params={"role": "SUPER"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"


class TestAdminDetailAPI(AdminQueryTestBase):
    async def test_returns_admin_detail(self) -> None:
        response = await request("GET", f"{ADMIN_ACCOUNTS_URL}/{self.super_admin.id}", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.json()) == {
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
        response = await request("GET", f"{ADMIN_ACCOUNTS_URL}/{self.super_admin.id}", headers=self.headers)

        assert response.json()["createdByAdminId"] is None

    async def test_returns_creator_id(self) -> None:
        response = await request("GET", f"{ADMIN_ACCOUNTS_URL}/{self.staff.id}", headers=self.headers)

        assert response.json()["createdByAdminId"] == self.super_admin.id

    async def test_returns_404_for_unknown_admin(self) -> None:
        response = await request("GET", f"{ADMIN_ACCOUNTS_URL}/999999", headers=self.headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"code": "ADMIN_NOT_FOUND", "message": "관리자를 찾을 수 없습니다."}


class TestUserListAPI(AdminQueryTestBase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.active_user = await create_user(
            name="홍길동", email="user@mail.com", phone="010-1234-5678", is_terms_agreed=True
        )
        # 설정 행이 없는 가입 직후 사용자
        self.pending_user = await create_user(name="김퇴원", email="discharged@mail.com", status=AccountStatus.PENDING)

    async def test_returns_paginated_users(self) -> None:
        response = await request("GET", ADMIN_USERS_URL, headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["totalCount"] == 2
        assert set(body["items"][0]) == {"userId", "name", "email", "status", "createdAt"}

    async def test_filters_by_status(self) -> None:
        response = await request("GET", ADMIN_USERS_URL, headers=self.headers, params={"status": "PENDING"})

        body = response.json()
        assert body["totalCount"] == 1
        assert body["items"][0]["userId"] == self.pending_user.id

    async def test_filters_by_keyword(self) -> None:
        response = await request("GET", ADMIN_USERS_URL, headers=self.headers, params={"keyword": "홍길동"})

        assert response.json()["totalCount"] == 1

    async def test_includes_signup_date_boundary(self) -> None:
        """종료일 당일에 가입한 사용자도 결과에 포함되어야 한다."""
        today = self.active_user.created_at.date().isoformat()

        response = await request(
            "GET", ADMIN_USERS_URL, headers=self.headers, params={"startDate": today, "endDate": today}
        )

        assert response.json()["totalCount"] == 2

    async def test_rejects_reversed_date_range(self) -> None:
        response = await request(
            "GET",
            ADMIN_USERS_URL,
            headers=self.headers,
            params={"startDate": "2026-01-01", "endDate": "2025-01-01"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_size_over_limit(self) -> None:
        response = await request("GET", ADMIN_USERS_URL, headers=self.headers, params={"size": 999})

        body = response.json()
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert body["code"] == "VALIDATION_ERROR"
        assert body["field"] == "size"


class TestUserDetailAPI(AdminQueryTestBase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.agreed_user = await create_user(
            name="홍길동", email="user@mail.com", phone="010-1234-5678", is_terms_agreed=True
        )
        self.no_settings_user = await create_user(name="김퇴원", email="discharged@mail.com")

    async def test_returns_user_detail(self) -> None:
        response = await request("GET", f"{ADMIN_USERS_URL}/{self.agreed_user.id}", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert set(response.json()) == {
            "userId",
            "name",
            "email",
            "phone",
            "status",
            "isTermsAgreed",
            "createdAt",
            "activeAlarmCount",
        }

    async def test_reads_terms_agreement_from_settings(self) -> None:
        response = await request("GET", f"{ADMIN_USERS_URL}/{self.agreed_user.id}", headers=self.headers)

        assert response.json()["isTermsAgreed"] is True

    async def test_treats_missing_settings_as_not_agreed(self) -> None:
        """설정 행이 아직 없는 가입 직후 사용자는 미동의로 본다."""
        response = await request("GET", f"{ADMIN_USERS_URL}/{self.no_settings_user.id}", headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["isTermsAgreed"] is False

    async def test_counts_only_active_alarms(self) -> None:
        response = await request("GET", f"{ADMIN_USERS_URL}/{self.agreed_user.id}", headers=self.headers)

        assert response.json()["activeAlarmCount"] == 0

    async def test_returns_404_for_unknown_user(self) -> None:
        response = await request("GET", f"{ADMIN_USERS_URL}/999999", headers=self.headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}


class TestAdminApiAuthorization(AdminQueryTestBase):
    async def test_requires_authorization_header(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"code": "UNAUTHORIZED", "message": "인증이 필요합니다."}

    async def test_rejects_malformed_token(self) -> None:
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers={"Authorization": "Bearer not-a-jwt"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_rejects_token_of_non_admin_account(self) -> None:
        """일반 사용자 토큰은 admin 테이블에 행이 없어 차단된다."""
        user = await create_user(name="홍길동", email="user@mail.com")

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=auth_header(user.id + 10_000))

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"

    async def test_rejects_suspended_admin(self) -> None:
        suspended = await create_admin(
            name="정지됨", email="suspended@ozcoding.ai", role=AdminRole.ADMIN, status=AccountStatus.SUSPENDED
        )

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=auth_header(suspended.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_rejects_pending_admin(self) -> None:
        """임시 비밀번호를 아직 바꾸지 않은 계정(PENDING)도 막는다."""
        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=auth_header(self.staff.id))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_staff_can_read(self) -> None:
        """조회는 ADMIN·STAFF 모두 허용한다(권한 매트릭스)."""
        active_staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request("GET", ADMIN_ACCOUNTS_URL, headers=auth_header(active_staff.id))

        assert response.status_code == status.HTTP_200_OK

    async def test_every_admin_endpoint_requires_authentication(self) -> None:
        admin_id = await Admin.all().first()
        assert admin_id is not None
        urls = [
            ADMIN_ACCOUNTS_URL,
            f"{ADMIN_ACCOUNTS_URL}/{admin_id.id}",
            ADMIN_USERS_URL,
            f"{ADMIN_USERS_URL}/1",
        ]

        for url in urls:
            response = await request("GET", url)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, url
