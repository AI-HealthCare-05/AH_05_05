from datetime import datetime, timedelta

from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.models.enums import AdminRole
from app.tests.admin_apis.conftest import auth_header, create_admin, request
from app.tests.med_apis.helpers import create_supplement

DISPLAY_URL = "/api/v1/admin/supplement-rank-displays"
PRODUCT_SEARCH_URL = "/api/v1/admin/supplement-nutrients"


def display_payload(first_product_id: int, second_product_id: int, *, start_at: datetime) -> dict:
    return {
        "title": "9월 영양제 랭킹",
        "startAt": start_at.isoformat(),
        "endAt": (start_at + timedelta(days=7)).isoformat(),
        "isEnabled": True,
        "items": [
            {"supplementNutrientId": first_product_id, "rankNo": 1},
            {"supplementNutrientId": second_product_id, "rankNo": 2},
        ],
    }


class TestAdminSupplementRankDisplayAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="최고 관리자", email="rank-admin@ozcoding.ai", role=AdminRole.ADMIN)
        self.staff = await create_admin(
            name="일반 관리자",
            email="rank-staff@ozcoding.ai",
            role=AdminRole.STAFF,
            created_by_admin_id=self.admin.id,
        )
        self.admin_headers = auth_header(self.admin.id)
        self.staff_headers = auth_header(self.staff.id)
        self.first = await create_supplement("DISPLAY-RANK-001", "비타민 D")
        self.second = await create_supplement("DISPLAY-RANK-002", "철분")
        self.start_at = datetime.now(config.TIMEZONE) - timedelta(hours=1)

    async def test_admin_can_create_and_read_a_rank_display_with_ordered_items(self) -> None:
        created = await request(
            "POST",
            DISPLAY_URL,
            headers=self.admin_headers,
            json=display_payload(self.first.id, self.second.id, start_at=self.start_at),
        )

        assert created.status_code == status.HTTP_201_CREATED, created.text
        body = created.json()
        assert body["title"] == "9월 영양제 랭킹"
        assert body["is_enabled"] is True
        assert body["created_by_admin_id"] == self.admin.id
        assert body["items"] == [
            {"supplement_nutrient_id": self.first.id, "name": "비타민 D", "rank_no": 1},
            {"supplement_nutrient_id": self.second.id, "name": "철분", "rank_no": 2},
        ]

        detail = await request("GET", f"{DISPLAY_URL}/{body['display_id']}", headers=self.staff_headers)
        current = await request("GET", f"{DISPLAY_URL}/current", headers=self.staff_headers)

        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["display_id"] == body["display_id"]
        assert current.status_code == status.HTTP_200_OK
        assert current.json()["display_id"] == body["display_id"]

    async def test_enabled_display_rejects_an_overlapping_period(self) -> None:
        payload = display_payload(self.first.id, self.second.id, start_at=self.start_at)
        first = await request("POST", DISPLAY_URL, headers=self.admin_headers, json=payload)
        second = await request("POST", DISPLAY_URL, headers=self.admin_headers, json={**payload, "title": "중복 전시"})

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_409_CONFLICT
        assert second.json()["code"] == "SUPPLEMENT_RANK_PERIOD_CONFLICT"

    async def test_staff_can_read_and_create_rank_displays(self) -> None:
        listed = await request("GET", DISPLAY_URL, headers=self.staff_headers)
        created = await request(
            "POST",
            DISPLAY_URL,
            headers=self.staff_headers,
            json=display_payload(self.first.id, self.second.id, start_at=self.start_at),
        )

        assert listed.status_code == status.HTTP_200_OK
        assert created.status_code == status.HTTP_201_CREATED
        assert created.json()["created_by_admin_id"] == self.staff.id

    async def test_admin_can_replace_items_and_delete_the_display(self) -> None:
        created = await request(
            "POST",
            DISPLAY_URL,
            headers=self.admin_headers,
            json=display_payload(self.first.id, self.second.id, start_at=self.start_at),
        )
        display_id = created.json()["display_id"]
        updated_payload = display_payload(self.first.id, self.second.id, start_at=self.start_at)
        updated_payload["title"] = "수정된 랭킹"
        updated_payload["isEnabled"] = False
        updated_payload["items"] = [{"supplementNutrientId": self.second.id, "rankNo": 1}]

        updated = await request(
            "PUT",
            f"{DISPLAY_URL}/{display_id}",
            headers=self.admin_headers,
            json=updated_payload,
        )
        deleted = await request("DELETE", f"{DISPLAY_URL}/{display_id}", headers=self.admin_headers)
        missing = await request("GET", f"{DISPLAY_URL}/{display_id}", headers=self.admin_headers)

        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["title"] == "수정된 랭킹"
        assert updated.json()["items"] == [{"supplement_nutrient_id": self.second.id, "name": "철분", "rank_no": 1}]
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert missing.status_code == status.HTTP_404_NOT_FOUND

    async def test_staff_can_search_products_for_rank_items(self) -> None:
        response = await request(
            "GET",
            PRODUCT_SEARCH_URL,
            headers=self.staff_headers,
            params={"name": "비타민", "offset": 0, "limit": 20},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"][0]["id"] == self.first.id
