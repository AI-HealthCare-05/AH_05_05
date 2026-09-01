from datetime import datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers, create_supplement


class TestMedNutrAPI(TestCase):
    async def _create_popularity_rows(self, user: User, *, manual_count: int):
        today = datetime.now(config.TIMEZONE).date()
        products = [await create_supplement(f"POPULAR-{index}", f"인기 표준 제품 {index}") for index in range(5)]
        for product in products:
            await UserSupplementNutrient.create(
                user=user,
                supplement_nutrient=product,
                dose_amount="1.000",
                dose_unit="정",
                start_date=today,
            )
        for index in range(manual_count):
            await UserSupplementNutrient.create(
                user=user,
                supplement_nutrient_id=None,
                custom_name=f"직접 입력 제품 {index}",
                dose_amount="1.000",
                dose_unit="정",
                start_date=today,
            )
        return products

    async def test_name_contains_search_is_paginated_and_case_insensitive(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-search@example.com", "01020000001")
            await create_supplement("FOOD-001", "철분 프리미엄")
            await create_supplement("FOOD-002", "고함량 철분")
            await create_supplement("FOOD-003", "VITAMIN D 1000")

            listed = await client.get(
                "/api/v1/med/nutr",
                params={"name": "철분", "offset": 0, "limit": 1},
                headers=headers,
            )
            english = await client.get(
                "/api/v1/med/nutr",
                params={"name": "vitamin"},
                headers=headers,
            )

        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 2
        assert listed.json()["offset"] == 0
        assert listed.json()["limit"] == 1
        assert len(listed.json()["items"]) == 1
        assert english.status_code == status.HTTP_200_OK
        assert english.json()["items"][0]["name"] == "VITAMIN D 1000"

    async def test_detail_returns_full_nutrition_and_missing_product_is_404(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-detail@example.com", "01020000002")
            product = await create_supplement("FOOD-010", "상세 영양제")

            detail = await client.get(f"/api/v1/med/nutr/{product.id}", headers=headers)
            missing = await client.get("/api/v1/med/nutr/999999", headers=headers)

        assert detail.status_code == status.HTTP_200_OK
        assert detail.json()["food_code"] == "FOOD-010"
        assert detail.json()["basis_qty"] == "500mg"
        assert detail.json()["protein_g"] == "0.00"
        assert detail.json()["water_g"] is None
        assert missing.status_code == status.HTTP_404_NOT_FOUND
        assert missing.json()["detail"] == "Supplement nutrient not found."

    async def test_catalog_requires_authentication_and_non_blank_name(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.get("/api/v1/med/nutr", params={"name": "철분"})
            headers = await authentication_headers(client, "nutr-validation@example.com", "01020000003")
            blank = await client.get("/api/v1/med/nutr", params={"name": "   "}, headers=headers)

        assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
        assert blank.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_popular_excludes_manual_registrations(self) -> None:
        email = "popular-excludes-manual@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, email, "01020000004")
            user = await User.get(email=email)
            products = await self._create_popularity_rows(user, manual_count=1)

            response = await client.get("/api/v1/med/nutr/popular", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert [item["id"] for item in response.json()] == [product.id for product in products]

    async def test_popular_returns_five_when_manual_rows_dominate(self) -> None:
        email = "popular-manual-dominates@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, email, "01020000005")
            user = await User.get(email=email)
            products = await self._create_popularity_rows(user, manual_count=6)

            response = await client.get("/api/v1/med/nutr/popular", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()) == 5
        assert {item["id"] for item in response.json()} == {product.id for product in products}
