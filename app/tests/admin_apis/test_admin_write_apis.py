from starlette import status
from tortoise.contrib.test import TestCase

from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.tests.admin_apis.conftest import (
    ADMIN_ACCOUNTS_URL,
    ADMIN_STATUS_URL,
    auth_header,
    create_admin,
    create_user,
    request,
)

CREATE_PAYLOAD = {"name": "한지수", "email": "jisu@ozcoding.ai", "role": "STAFF", "isActive": True}


class AdminWriteTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.super_admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.staff = await create_admin(
            name="김진형",
            email="jinhyeong@ozcoding.ai",
            role=AdminRole.STAFF,
            created_by_admin_id=self.super_admin.id,
        )
        self.headers = auth_header(self.super_admin.id)


class TestAdminCreateAPI(AdminWriteTestBase):
    async def test_creates_admin(self) -> None:
        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["name"] == "한지수"
        assert body["role"] == "STAFF"
        assert body["status"] == "ACTIVE"
        assert body["createdByAdminId"] == self.super_admin.id
        assert await Admin.filter(email="jisu@ozcoding.ai").exists()

    async def test_stores_hashed_password_only(self) -> None:
        """임시 비밀번호는 이메일로만 전달하며 응답에 포함하지 않는다."""
        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert not any("password" in key.lower() for key in response.json())
        created = await Admin.get(email="jisu@ozcoding.ai")
        assert created.hashed_password.startswith("$2")

    async def test_inactive_flag_creates_pending_admin(self) -> None:
        payload = {**CREATE_PAYLOAD, "isActive": False}

        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=payload)

        assert response.json()["status"] == "PENDING"

    async def test_rejects_duplicate_email(self) -> None:
        payload = {**CREATE_PAYLOAD, "email": "eunmi@ozcoding.ai"}

        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=payload)

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "EMAIL_ALREADY_EXISTS"
        assert await Admin.all().count() == 2

    async def test_rejects_invalid_email_format(self) -> None:
        payload = {**CREATE_PAYLOAD, "email": "not-an-email"}

        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_unknown_role(self) -> None:
        payload = {**CREATE_PAYLOAD, "role": "SUPER"}

        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_staff_cannot_create_admin(self) -> None:
        """등록은 ADMIN 전용이다(권한 매트릭스)."""
        active_staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=auth_header(active_staff.id), json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"

    async def test_requires_authentication(self) -> None:
        response = await request("POST", ADMIN_ACCOUNTS_URL, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminStatusUpdateAPI(AdminWriteTestBase):
    async def test_suspends_admins(self) -> None:
        response = await request(
            "PATCH", ADMIN_STATUS_URL, headers=self.headers, json={"adminIds": [self.staff.id], "status": "SUSPENDED"}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"updatedCount": 1, "status": "SUSPENDED", "adminIds": [self.staff.id]}
        await self.staff.refresh_from_db()
        assert self.staff.status == AccountStatus.SUSPENDED

    async def test_rejects_suspending_self(self) -> None:
        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=self.headers,
            json={"adminIds": [self.super_admin.id], "status": "SUSPENDED"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_SUSPEND_SELF"

    async def test_rejects_suspending_last_active_admin(self) -> None:
        """활성 ADMIN 이 0명이 되면 아무도 콘솔에 들어올 수 없다."""
        actor = await create_admin(name="부관리자", email="sub@ozcoding.ai", role=AdminRole.ADMIN)

        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(actor.id),
            json={"adminIds": [self.super_admin.id, actor.id], "status": "SUSPENDED"},
        )

        # 본인이 포함돼 있으므로 자기 정지 규칙이 먼저 걸린다.
        assert response.status_code == status.HTTP_409_CONFLICT

        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(actor.id),
            json={"adminIds": [self.super_admin.id], "status": "SUSPENDED"},
        )
        # 요청자(actor)가 활성 ADMIN 으로 남으므로 이번에는 통과한다.
        assert response.status_code == status.HTTP_200_OK

        # 이제 마지막 활성 ADMIN 은 actor 뿐이다. 다른 ADMIN 이 actor 를 정지시키려 하면 막힌다.
        await Admin.filter(id=self.super_admin.id).update(status=AccountStatus.ACTIVE)
        await Admin.filter(id=actor.id).update(status=AccountStatus.SUSPENDED)
        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(self.super_admin.id),
            json={"adminIds": [self.super_admin.id], "status": "SUSPENDED"},
        )
        assert response.json()["code"] == "CANNOT_SUSPEND_SELF"

    async def test_blocks_when_no_active_admin_would_remain(self) -> None:
        actor = await create_admin(name="부관리자", email="sub@ozcoding.ai", role=AdminRole.ADMIN)
        await Admin.filter(id=actor.id).update(status=AccountStatus.SUSPENDED)

        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(self.super_admin.id),
            json={"adminIds": [self.staff.id], "status": "SUSPENDED"},
        )
        # staff 는 STAFF 라 ADMIN 수에 영향이 없다 -> 통과
        assert response.status_code == status.HTTP_200_OK

    async def test_rolls_back_when_any_id_is_missing(self) -> None:
        """부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다."""
        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=self.headers,
            json={"adminIds": [self.staff.id, 999999], "status": "SUSPENDED"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "ADMIN_NOT_FOUND"
        await self.staff.refresh_from_db()
        assert self.staff.status != AccountStatus.SUSPENDED

    async def test_reactivation_is_not_blocked_by_invariant(self) -> None:
        await Admin.filter(id=self.staff.id).update(status=AccountStatus.SUSPENDED)

        response = await request(
            "PATCH", ADMIN_STATUS_URL, headers=self.headers, json={"adminIds": [self.staff.id], "status": "ACTIVE"}
        )

        assert response.status_code == status.HTTP_200_OK
        await self.staff.refresh_from_db()
        assert self.staff.status == AccountStatus.ACTIVE

    async def test_rejects_empty_id_list(self) -> None:
        response = await request(
            "PATCH", ADMIN_STATUS_URL, headers=self.headers, json={"adminIds": [], "status": "SUSPENDED"}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_rejects_status_other_than_active_or_suspended(self) -> None:
        """계정 삭제 기능은 없으므로 WITHDRAWN 등으로는 바꿀 수 없다."""
        response = await request(
            "PATCH", ADMIN_STATUS_URL, headers=self.headers, json={"adminIds": [self.staff.id], "status": "WITHDRAWN"}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_staff_cannot_change_status(self) -> None:
        active_staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(active_staff.id),
            json={"adminIds": [self.staff.id], "status": "SUSPENDED"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_user_token_cannot_change_status(self) -> None:
        """일반 사용자 토큰은 admin 테이블에 행이 없어 차단된다."""
        user = await create_user(name="홍길동", email="user@mail.com")

        response = await request(
            "PATCH",
            ADMIN_STATUS_URL,
            headers=auth_header(user.id + 10_000),
            json={"adminIds": [self.staff.id], "status": "SUSPENDED"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_requires_authentication(self) -> None:
        response = await request("PATCH", ADMIN_STATUS_URL, json={"adminIds": [self.staff.id], "status": "SUSPENDED"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
