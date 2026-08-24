from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.tests.med_apis.helpers import authentication_headers, create_supplement


def registration_payload(*, slots: list[str] | None = None) -> dict:
    return {
        "dose_amount": "1.000",
        "dose_unit": "정",
        "start_date": "2026-08-24",
        "slots": slots or ["MORNING", "EVENING"],
        "note": "식후 복용",
    }


class TestUserSupplementNutrientAPI(TestCase):
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
