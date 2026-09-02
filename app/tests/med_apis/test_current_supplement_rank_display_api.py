from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.supplement_nutrients import (
    DisplaySupplementNutrientRank,
    SupplementNutrientRankItem,
)
from app.tests.med_apis.helpers import authentication_headers, create_supplement

CURRENT_DISPLAY_URL = "/api/v1/display/med/nutr/rank"


class TestCurrentSupplementRankDisplayAPI(TestCase):
    async def test_returns_the_current_enabled_display_with_items_in_rank_order(self) -> None:
        now = datetime.now(config.TIMEZONE)
        display = await DisplaySupplementNutrientRank.create(
            title="현재 영양제 랭킹",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            is_enabled=True,
        )
        first = await create_supplement("CURRENT-RANK-001", "비타민 D")
        second = await create_supplement("CURRENT-RANK-002", "철분")
        await SupplementNutrientRankItem.create(
            display=display,
            supplement_nutrient=second,
            rank_no=2,
        )
        await SupplementNutrientRankItem.create(
            display=display,
            supplement_nutrient=first,
            rank_no=1,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "display-rank@example.com", "01020000011")
            response = await client.get(CURRENT_DISPLAY_URL, headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["display_id"] == display.id
        assert response.json()["items"] == [
            {"supplement_nutrient_id": first.id, "name": "비타민 D", "rank_no": 1},
            {"supplement_nutrient_id": second.id, "name": "철분", "rank_no": 2},
        ]

    async def test_allows_unauthenticated_users_to_read_current_display(self) -> None:
        now = datetime.now(config.TIMEZONE)
        display = await DisplaySupplementNutrientRank.create(
            title="비로그인 공개 랭킹",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            is_enabled=True,
        )
        product = await create_supplement("PUBLIC-RANK-001", "공개 비타민")
        await SupplementNutrientRankItem.create(
            display=display,
            supplement_nutrient=product,
            rank_no=1,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(CURRENT_DISPLAY_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["items"] == [
            {
                "supplement_nutrient_id": product.id,
                "name": "공개 비타민",
                "rank_no": 1,
            }
        ]

    async def test_returns_404_when_displays_are_disabled_or_outside_the_current_period(self) -> None:
        now = datetime.now(config.TIMEZONE)
        await DisplaySupplementNutrientRank.create(
            title="종료된 전시",
            start_at=now - timedelta(days=2),
            end_at=now - timedelta(days=1),
            is_enabled=True,
        )
        await DisplaySupplementNutrientRank.create(
            title="비활성 전시",
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            is_enabled=False,
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "no-display-rank@example.com", "01020000012")
            response = await client.get(CURRENT_DISPLAY_URL, headers=headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "SUPPLEMENT_RANK_DISPLAY_NOT_FOUND"
