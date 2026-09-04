from starlette import status
from tortoise.contrib.test import TestCase

from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.tests.admin_apis.conftest import auth_header, create_admin, request


def name_url(admin_id: int) -> str:
    return f"/api/v1/admin/accounts/{admin_id}/name"


class AdminNameTestBase(TestCase):
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


class TestAdminNameUpdateAPI(AdminNameTestBase):
    async def test_admin_can_rename_another_admin(self) -> None:
        # 숫자를 넣으면 422 다(사용자 이름과 같은 규칙). 문자만으로 바꾼다.
        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": "김진형둘"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"adminId": self.staff.id, "name": "김진형둘"}
        await self.staff.refresh_from_db()
        assert self.staff.name == "김진형둘"

    async def test_admin_can_rename_self(self) -> None:
        response = await request("PATCH", name_url(self.super_admin.id), headers=self.headers, json={"name": "은미"})

        assert response.status_code == status.HTTP_200_OK
        await self.super_admin.refresh_from_db()
        assert self.super_admin.name == "은미"

    async def test_does_not_change_email_or_role(self) -> None:
        """이름만 바꾼다. 이메일은 로그인 식별자라 대상이 아니고, 역할은 별도 API 다."""
        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": "새이름"})

        assert response.status_code == status.HTTP_200_OK
        await self.staff.refresh_from_db()
        assert self.staff.email == "jinhyeong@ozcoding.ai"
        assert self.staff.role == AdminRole.STAFF


class TestAdminNamePermissions(AdminNameTestBase):
    async def test_staff_can_rename_self(self) -> None:
        response = await request(
            "PATCH", name_url(self.staff.id), headers=auth_header(self.staff.id), json={"name": "진형"}
        )

        assert response.status_code == status.HTTP_200_OK
        await self.staff.refresh_from_db()
        assert self.staff.name == "진형"

    async def test_staff_cannot_rename_others(self) -> None:
        """STAFF 는 본인 것만 바꿀 수 있다(권한 매트릭스)."""
        response = await request(
            "PATCH", name_url(self.super_admin.id), headers=auth_header(self.staff.id), json={"name": "탈취"}
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] == "FORBIDDEN"
        await self.super_admin.refresh_from_db()
        assert self.super_admin.name == "김은미"

    async def test_requires_authentication(self) -> None:
        response = await request("PATCH", name_url(self.staff.id), json={"name": "이름"})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminNameValidation(AdminNameTestBase):
    async def test_rejects_missing_admin(self) -> None:
        response = await request("PATCH", name_url(999999), headers=self.headers, json={"name": "이름"})

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "ADMIN_NOT_FOUND"

    async def test_rejects_suspended_admin(self) -> None:
        """쓸 수 없는 계정은 손대지 않는다(역할 변경과 같은 기준)."""
        await Admin.filter(id=self.staff.id).update(status=AccountStatus.SUSPENDED)

        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": "이름"})

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "CANNOT_CHANGE_INACTIVE_ADMIN"

    async def test_allows_pending_admin(self) -> None:
        """첫 로그인 전 오타를 고칠 유일한 경로라 PENDING 은 허용한다."""
        await Admin.filter(id=self.staff.id).update(status=AccountStatus.PENDING)

        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": "고친이름"})

        assert response.status_code == status.HTTP_200_OK

    async def test_rejects_empty_name(self) -> None:
        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": ""})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_rejects_name_over_100_characters(self) -> None:
        response = await request("PATCH", name_url(self.staff.id), headers=self.headers, json={"name": "가" * 101})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
