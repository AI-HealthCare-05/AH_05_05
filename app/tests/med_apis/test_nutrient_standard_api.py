from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.supplement_nutrients import NutrientStandard
from app.tests.med_apis.helpers import authentication_headers


class TestNutrientStandardAPI(TestCase):
    async def test_list_is_paginated_and_filterable_by_group_and_age(self) -> None:
        await NutrientStandard.create(grp="남자", age="19-29세", carb_g_rni="130", protein_g_rni="65")
        await NutrientStandard.create(grp="여자", age="19-29세", carb_g_rni="130", protein_g_rni="55")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-std@example.com", "01020990001")
            response = await client.get(
                "/api/v1/med/nutr-std",
                params={"grp": "여자", "age": 20, "offset": 0, "limit": 20},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["total"] == 1
        assert body["offset"] == 0
        assert body["limit"] == 20
        assert body["items"][0]["grp"] == "여자"
        assert body["items"][0]["age"] == "19-29세"
        assert body["items"][0]["carb_g_rni"] == "130.000"
        assert body["items"][0]["protein_g_rni"] == "55.000"

    async def test_age_range_boundaries_map_to_the_expected_database_rows(self) -> None:
        expected_ranges = (
            ("1-2세", (1, 2)),
            ("3-5세", (3, 5)),
            ("6-8세", (6, 8)),
            ("9-11세", (9, 11)),
            ("12-14세", (12, 14)),
            ("15-18세", (15, 18)),
            ("19-29세", (19, 29)),
            ("30-49세", (30, 49)),
            ("50-64세", (50, 64)),
            ("65-74세", (65, 74)),
            ("75세 이상", (75, 100)),
        )
        for index, (age_range, _) in enumerate(expected_ranges, start=1):
            await NutrientStandard.create(grp=f"구분{index}", age=age_range, carb_g_rni="130")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-std-boundary@example.com", "01020990002")
            for expected_range, boundary_ages in expected_ranges:
                for age in boundary_ages:
                    response = await client.get(
                        "/api/v1/med/nutr-std",
                        params={"age": age},
                        headers=headers,
                    )
                    assert response.status_code == status.HTTP_200_OK
                    assert response.json()["items"][0]["age"] == expected_range

    async def test_age_must_be_at_least_one(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "nutr-std-age-validation@example.com", "01020990003")
            response = await client.get(
                "/api/v1/med/nutr-std",
                params={"age": 0},
                headers=headers,
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_list_requires_authentication(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/med/nutr-std")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
