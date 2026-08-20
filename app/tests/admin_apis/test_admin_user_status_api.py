from starlette import status
from tortoise.contrib.test import TestCase

from app.models.enums import AccountStatus, AdminRole
from app.models.users import User
from app.tests.admin_apis.conftest import auth_header, create_admin, create_user, request

ADMIN_USER_STATUS_URL = "/api/v1/admin/users/status"


def payload(user_ids: list[int], new_status: str = AccountStatus.SUSPENDED) -> dict[str, object]:
    return {"userIds": user_ids, "status": new_status}


class AdminUserStatusTestBase(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.actor = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.actor.id)
        self.user = await create_user(name="한지수", email="jisu@example.com")
        self.other = await create_user(name="박서준", email="seojun@example.com")


class TestAdminUserStatusUpdateAPI(AdminUserStatusTestBase):
    async def test_suspends_single_user(self) -> None:
        response = await request("PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id]))

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "updatedCount": 1,
            "status": "SUSPENDED",
            "userIds": [self.user.id],
        }
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.SUSPENDED

    async def test_suspends_multiple_users(self) -> None:
        ids = sorted([self.user.id, self.other.id])

        response = await request("PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload(ids))

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["updatedCount"] == 2
        assert response.json()["userIds"] == ids
        for user in (self.user, self.other):
            await user.refresh_from_db()
            assert user.status == AccountStatus.SUSPENDED

    async def test_reactivates_suspended_user(self) -> None:
        await User.filter(id=self.user.id).update(status=AccountStatus.SUSPENDED)

        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id], AccountStatus.ACTIVE)
        )

        assert response.status_code == status.HTTP_200_OK
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.ACTIVE

    async def test_deduplicates_ids(self) -> None:
        """같은 ID 를 여러 번 보내도 한 명으로 센다."""
        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id, self.user.id])
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "updatedCount": 1,
            "status": "SUSPENDED",
            "userIds": [self.user.id],
        }

    async def test_rejects_when_any_user_is_missing(self) -> None:
        """부분 성공을 허용하면 프론트가 무엇이 실패했는지 알 수 없다."""
        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id, 999999])
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "USER_NOT_FOUND"
        # 존재하는 쪽도 바뀌지 않아야 한다(전체 롤백).
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.ACTIVE

    async def test_rejects_withdrawn_user(self) -> None:
        """탈퇴는 본인 의사다. 관리자가 되살리면 삭제 대기 계정이 다시 살아난다."""
        await User.filter(id=self.user.id).update(status=AccountStatus.WITHDRAWN)

        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id], AccountStatus.ACTIVE)
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_REACTIVATE_WITHDRAWN"
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.WITHDRAWN

    async def test_rejects_batch_containing_withdrawn_user(self) -> None:
        await User.filter(id=self.other.id).update(status=AccountStatus.WITHDRAWN)

        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id, self.other.id])
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.ACTIVE


class TestAdminUserStatusValidation(AdminUserStatusTestBase):
    async def test_rejects_empty_user_ids(self) -> None:
        response = await request("PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([]))

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_rejects_more_than_100_ids(self) -> None:
        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload(list(range(1, 102)))
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_rejects_withdrawn_as_target_status(self) -> None:
        """강제 탈퇴는 이 API 로 하지 않는다(REQ-ADMIN-007 데이터 삭제가 따로 있다)."""
        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id], AccountStatus.WITHDRAWN)
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.ACTIVE

    async def test_rejects_pending_as_target_status(self) -> None:
        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=self.headers, json=payload([self.user.id], AccountStatus.PENDING)
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestAdminUserStatusPermissions(AdminUserStatusTestBase):
    async def test_staff_cannot_change_user_status(self) -> None:
        """조회는 STAFF 도 되지만 상태 변경은 ADMIN 전용이다(관리자 계정 정지와 동일)."""
        staff = await create_admin(name="스태프", email="staff@ozcoding.ai", role=AdminRole.STAFF)

        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=auth_header(staff.id), json=payload([self.user.id])
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"
        await self.user.refresh_from_db()
        assert self.user.status == AccountStatus.ACTIVE

    async def test_requires_authentication(self) -> None:
        response = await request("PATCH", ADMIN_USER_STATUS_URL, json=payload([self.user.id]))

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "UNAUTHORIZED"

    async def test_suspended_admin_cannot_change_user_status(self) -> None:
        suspended = await create_admin(
            name="정지된관리자",
            email="suspended@ozcoding.ai",
            role=AdminRole.ADMIN,
            status=AccountStatus.SUSPENDED,
        )

        response = await request(
            "PATCH", ADMIN_USER_STATUS_URL, headers=auth_header(suspended.id), json=payload([self.user.id])
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
