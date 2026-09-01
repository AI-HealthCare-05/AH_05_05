from datetime import date, datetime

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.supplement_nutrients import NutrientStandard
from app.models.users import User
from app.tests.med_apis.helpers import authentication_headers, create_supplement

STANDARD_NUTRIENT_KEYS = {
    "protein_g",
    "carb_g",
    "fat_g",
    "fiber_g",
    "calcium_mg",
    "iron_mg",
    "phosphorus_mg",
    "potassium_mg",
    "sodium_mg",
    "vitamin_a_ug_rae",
    "thiamine_mg",
    "riboflavin_mg",
    "niacin_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
}


def registration_payload(*, slots: list[str] | None = None) -> dict:
    return {
        "dose_amount": "1.000",
        "dose_unit": "정",
        "start_date": "2026-08-24",
        "slots": slots or ["MORNING", "EVENING"],
        "note": "식후 복용",
    }


async def get_active_supplement_list(client: AsyncClient, headers: dict[str, str]):
    return await client.get(
        "/api/v1/med/user-suppl-nutr",
        params={"status": "ACTIVE", "offset": 0, "limit": 20},
        headers=headers,
    )


class TestUserSupplementNutrientAPI(TestCase):
    async def test_list_includes_nutrient_standard(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(
            grp="여자",
            age="19-29세",
            calcium_mg_rni="800",
            calcium_mg_ul="2500",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-standard@example.com"
            headers = await authentication_headers(client, email, "01021000011")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        standard = response.json()["nutrient_standard"]
        assert standard["grp"] == "여자"
        assert standard["age"] == "19-29세"
        assert standard["calcium_mg"] == {"rni": "800.000", "ai": None, "ul": "2500.000"}

    async def test_list_standard_is_null_without_birth_date(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-no-birth-date@example.com"
            headers = await authentication_headers(client, email, "01021000012")
            user = await User.get(email=email)
            user.birth_date = None
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_is_null_without_gender(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-no-gender@example.com"
            headers = await authentication_headers(client, email, "01021000013")
            user = await User.get(email=email)
            user.gender = None
            await user.save(update_fields=["gender"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_is_null_when_row_missing(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(
                client,
                "user-suppl-missing-standard@example.com",
                "01021000014",
            )
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_list_standard_keys_are_always_present(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(grp="여자", age="19-29세")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-standard-keys@example.com"
            headers = await authentication_headers(client, email, "01021000015")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        standard = response.json()["nutrient_standard"]
        assert set(standard) == {"grp", "age", *STANDARD_NUTRIENT_KEYS}
        for nutrient_key in STANDARD_NUTRIENT_KEYS:
            assert standard[nutrient_key] == {"rni": None, "ai": None, "ul": None}

    async def test_list_standard_never_matches_pregnant_group(self) -> None:
        today = datetime.now(config.TIMEZONE).date()
        await NutrientStandard.create(
            grp="임신부",
            age="19-29세",
            calcium_mg_rni="900",
        )
        await NutrientStandard.create(
            grp="수유부",
            age="19-29세",
            calcium_mg_rni="1000",
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "user-suppl-never-pregnant@example.com"
            headers = await authentication_headers(client, email, "01021000016")
            user = await User.get(email=email)
            user.birth_date = date(today.year - 26, 1, 1)
            await user.save(update_fields=["birth_date"])
            response = await get_active_supplement_list(client, headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["nutrient_standard"] is None

    async def test_authenticated_user_can_manage_own_supplement_registration(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "user-suppl@example.com", "01021000001")
            product = await create_supplement("USER-SUPPL-001", "사용자 철분")

            created = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(),
                headers=headers,
            )
            registration_id = created.json()["id"]
            listed = await client.get(
                "/api/v1/med/user-suppl-nutr",
                params={"status": "ACTIVE", "offset": 0, "limit": 20},
                headers=headers,
            )
            detail = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            updated = await client.patch(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                json={"dose_amount": "2.000", "slots": ["BEDTIME"], "note": "취침 전"},
                headers=headers,
            )
            completed = await client.delete(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )
            after_complete = await client.get(
                f"/api/v1/med/user-suppl-nutr/{registration_id}",
                headers=headers,
            )

        assert created.status_code == status.HTTP_200_OK
        assert created.json()["supplement"]["id"] == product.id
        assert [item["slot"] for item in created.json()["slots"]] == ["MORNING", "EVENING"]
        assert listed.status_code == status.HTTP_200_OK
        assert listed.json()["total"] == 1
        assert detail.status_code == status.HTTP_200_OK
        assert updated.status_code == status.HTTP_200_OK
        assert updated.json()["dose_amount"] == "2.000"
        assert updated.json()["slots"] == [{"slot": "BEDTIME", "time": "22:00:00"}]
        assert completed.status_code == status.HTTP_204_NO_CONTENT
        assert after_complete.json()["status"] == "COMPLETED"
        assert after_complete.json()["end_date"] is not None

    async def test_registration_is_upserted_and_is_owner_scoped(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_headers = await authentication_headers(client, "suppl-owner-api@example.com", "01021000002")
            other_headers = await authentication_headers(client, "suppl-other-api@example.com", "01021000003")
            product = await create_supplement("USER-SUPPL-002", "사용자 비타민")

            first = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["LUNCH"]),
                headers=owner_headers,
            )
            second = await client.put(
                f"/api/v1/med/user-suppl-nutr/{product.id}",
                json=registration_payload(slots=["BEDTIME"]),
                headers=owner_headers,
            )
            hidden = await client.get(
                f"/api/v1/med/user-suppl-nutr/{first.json()['id']}",
                headers=other_headers,
            )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.json()["id"] == second.json()["id"]
        assert hidden.status_code == status.HTTP_404_NOT_FOUND

    async def test_routes_require_authentication_and_are_exposed_in_openapi(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            anonymous = await client.get("/api/v1/med/user-suppl-nutr")
            openapi = (await client.get("/api/openapi.json")).json()

        assert anonymous.status_code == status.HTTP_401_UNAUTHORIZED
        assert "/api/v1/med/user-suppl-nutr" in openapi["paths"]
        assert "/api/v1/med/user-suppl-nutr/{registration_id}" in openapi["paths"]
        assert set(openapi["paths"]["/api/v1/med/user-suppl-nutr/{registration_id}"]) >= {
            "get",
            "put",
            "patch",
            "delete",
        }
