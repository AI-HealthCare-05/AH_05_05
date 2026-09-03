from starlette import status
from tortoise.contrib.test import TestCase

from app.models.enums import AdminRole
from app.tests.admin_apis.conftest import auth_header, create_admin, request

GROUP_URL = "/api/v1/admin/common-code-groups"


class TestAdminCommonCodeAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="최고 관리자", email="common-admin@example.com", role=AdminRole.ADMIN)
        self.staff = await create_admin(name="일반 관리자", email="common-staff@example.com", role=AdminRole.STAFF)
        self.admin_headers = auth_header(self.admin.id)
        self.staff_headers = auth_header(self.staff.id)

    async def test_admin_can_create_category_group_and_detail_code(self) -> None:
        created_group = await request(
            "POST",
            GROUP_URL,
            headers=self.admin_headers,
            json={
                "category": " chat ",
                "group_code": " p_reason ",
                "group_name": "긍정 평가 사유",
                "description": "챗봇 긍정 평가",
                "is_active": True,
            },
        )

        assert created_group.status_code == status.HTTP_201_CREATED, created_group.text
        group = created_group.json()
        assert group["category"] == "CHAT"
        assert group["group_code"] == "P_REASON"
        assert "groupCode" not in group

        created_code = await request(
            "POST",
            f"{GROUP_URL}/{group['id']}/codes",
            headers=self.admin_headers,
            json={
                "detail_code": " helpful ",
                "detail_name": "도움이 되었어요",
                "sort_order": 1,
                "is_active": True,
            },
        )

        assert created_code.status_code == status.HTTP_201_CREATED, created_code.text
        assert created_code.json()["detail_code"] == "HELPFUL"
        assert created_code.json()["group_id"] == group["id"]

    async def test_staff_can_read_but_cannot_create_common_codes(self) -> None:
        listed = await request("GET", GROUP_URL, headers=self.staff_headers)
        denied = await request(
            "POST",
            GROUP_URL,
            headers=self.staff_headers,
            json={"category": "CHAT", "group_code": "N_REASON", "group_name": "부정 사유"},
        )

        assert listed.status_code == status.HTTP_200_OK
        assert denied.status_code == status.HTTP_403_FORBIDDEN

    async def test_duplicate_group_code_returns_conflict(self) -> None:
        payload = {"category": "CHAT", "group_code": "P_REASON", "group_name": "긍정 사유"}
        first = await request("POST", GROUP_URL, headers=self.admin_headers, json=payload)
        second = await request("POST", GROUP_URL, headers=self.admin_headers, json=payload)

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_409_CONFLICT
        assert second.json()["code"] == "COMMON_CODE_ALREADY_EXISTS"

    async def test_group_list_filters_by_category_and_paginates_with_snake_case(self) -> None:
        for category, code in (("CHAT", "P_REASON"), ("USER", "STATUS")):
            await request(
                "POST",
                GROUP_URL,
                headers=self.admin_headers,
                json={"category": category, "group_code": code, "group_name": code},
            )

        response = await request(
            "GET",
            GROUP_URL,
            headers=self.staff_headers,
            params={"category": "chat", "offset": 0, "limit": 20},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["total_count"] == 1
        assert [item["group_code"] for item in response.json()["items"]] == ["P_REASON"]
