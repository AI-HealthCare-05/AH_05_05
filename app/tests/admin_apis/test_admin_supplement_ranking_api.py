from datetime import datetime

from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.models.enums import AdminRole, SupplementStatus
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import User
from app.tests.admin_apis.conftest import auth_header, create_admin, request
from app.tests.med_apis.helpers import create_supplement

ADMIN_SUPPLEMENT_RANKING_URL = "/api/v1/admin/supplement-nutrients/popular"


class TestAdminSupplementRankingAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.staff = await create_admin(name="운영자", email="ranking-staff@ozcoding.ai", role=AdminRole.STAFF)
        self.headers = auth_header(self.staff.id)

    async def test_staff_can_list_currently_used_supplements_in_popularity_order(self) -> None:
        first = await create_supplement("RANK-001", "가장 인기 있는 영양제")
        second = await create_supplement("RANK-002", "두 번째 영양제")
        completed = await create_supplement("RANK-003", "복용 완료 영양제")
        users = [
            await User.create(email=f"ranking-{index}@example.com", hashed_password="unused", name=f"사용자 {index}")
            for index in range(1, 5)
        ]
        today = datetime.now(config.TIMEZONE).date()
        await UserSupplementNutrient.create(
            user=users[0], supplement_nutrient=first, dose_amount="1.000", dose_unit="정", start_date=today
        )
        await UserSupplementNutrient.create(
            user=users[1], supplement_nutrient=first, dose_amount="1.000", dose_unit="정", start_date=today
        )
        await UserSupplementNutrient.create(
            user=users[2], supplement_nutrient=second, dose_amount="1.000", dose_unit="정", start_date=today
        )
        await UserSupplementNutrient.create(
            user=users[3],
            supplement_nutrient=completed,
            dose_amount="1.000",
            dose_unit="정",
            start_date=today,
            end_date=today,
            status=SupplementStatus.COMPLETED,
        )

        response = await request("GET", ADMIN_SUPPLEMENT_RANKING_URL, headers=self.headers)

        assert response.status_code == status.HTTP_200_OK, response.text
        assert response.json() == [
            {"id": first.id, "name": "가장 인기 있는 영양제"},
            {"id": second.id, "name": "두 번째 영양제"},
        ]

    async def test_ranking_requires_admin_authentication(self) -> None:
        response = await request("GET", ADMIN_SUPPLEMENT_RANKING_URL)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
