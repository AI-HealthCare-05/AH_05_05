from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.tests.med_apis.helpers import authentication_headers, create_supplement


class TestMedNutrAPI(TestCase):
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
