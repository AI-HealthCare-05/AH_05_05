from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.supplement_nutrients import SupplementDose
from app.tests.med_apis.helpers import authentication_headers


class TestSupplementDoseAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.headers = await authentication_headers(self.client, "dose-owner@example.com", "01029000001")
        self.other_headers = await authentication_headers(self.client, "dose-other@example.com", "01029000002")
        self.today = datetime.now(config.TIMEZONE).date()
        created = await self.client.post(
            "/api/v1/med/user-suppl-nutr",
            headers=self.headers,
            json={
                "custom_name": "테스트 영양제", "dose_amount": "1", "dose_unit": "정",
                "start_date": (self.today - timedelta(days=1)).isoformat(), "slots": ["MORNING", "EVENING"],
            },
        )
        assert created.status_code == 201
        self.registration_id = created.json()["id"]
        self.payload = {
            "supplementId": self.registration_id, "date": self.today.isoformat(), "slot": "morning", "taken": True,
        }

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await super().asyncTearDown()

    async def save(self, **changes):
        return await self.client.put(
            "/api/v1/med/supplement-doses", headers=self.headers, json={**self.payload, **changes},
        )

    async def test_record_is_idempotent_and_undo_only_removes_selected_slot(self) -> None:
        for _ in range(2):
            response = await self.save()
            assert response.status_code == 200
            assert response.json() == self.payload
        assert await SupplementDose.all().count() == 1
        await self.save(slot="evening")
        listed = await self.client.get(
            "/api/v1/med/supplement-doses", params={"date": self.today.isoformat()}, headers=self.headers,
        )
        assert [item["slot"] for item in listed.json()] == ["morning", "evening"]
        for _ in range(2):
            undone = await self.save(taken=False)
            assert undone.status_code == 200
            assert undone.json() == {**self.payload, "taken": False}
        assert await SupplementDose.all().count() == 1
        assert (await SupplementDose.all().first()).slot.value == "EVENING"

    async def test_other_user_cannot_read_or_write_owned_registration(self) -> None:
        await self.save()
        for taken in (True, False):
            response = await self.client.put(
                "/api/v1/med/supplement-doses", headers=self.other_headers, json={**self.payload, "taken": taken},
            )
            assert response.status_code == 404
        missing = await self.save(supplementId=99999999)
        assert missing.status_code == 404
        listed = await self.client.get(
            "/api/v1/med/supplement-doses", params={"date": self.today.isoformat()}, headers=self.other_headers,
        )
        assert listed.status_code == 200
        assert listed.json() == []
        assert await SupplementDose.all().count() == 1

    async def test_invalid_date_and_unregistered_slot_do_not_create_records(self) -> None:
        for changes in (
            {"date": (self.today + timedelta(days=1)).isoformat()},
            {"date": (self.today - timedelta(days=366)).isoformat()},
            {"date": (self.today - timedelta(days=2)).isoformat()},
            {"slot": "lunch"}, {"slot": "dinner"},
        ):
            response = await self.save(**changes)
            assert response.status_code == 422
        assert await SupplementDose.all().count() == 0

    async def test_undo_remains_available_after_registration_is_stopped_or_slots_change(self) -> None:
        await self.save()
        await self.client.patch(
            f"/api/v1/med/user-suppl-nutr/{self.registration_id}",
            headers=self.headers, json={"slots": ["EVENING"]},
        )
        assert (await self.save()).status_code == 422
        assert (await self.save(taken=False)).status_code == 200
        await self.save(slot="evening")
        await self.client.delete(f"/api/v1/med/user-suppl-nutr/{self.registration_id}", headers=self.headers)
        assert (await self.save(slot="evening")).status_code == 422
        assert (await self.save(slot="evening", taken=False)).status_code == 200
        assert await SupplementDose.all().count() == 0

    async def test_authentication_required(self) -> None:
        response = await self.client.put("/api/v1/med/supplement-doses", json=self.payload)
        assert response.status_code == 401
        response = await self.client.get("/api/v1/med/supplement-doses", params={"date": self.today.isoformat()})
        assert response.status_code == 401

    async def test_records_are_isolated_by_registration_and_date(self) -> None:
        other = await self.client.post(
            "/api/v1/med/user-suppl-nutr", headers=self.headers,
            json={
                "custom_name": "다른 영양제", "dose_amount": "1", "dose_unit": "정",
                "start_date": self.today.isoformat(), "slots": ["MORNING"],
            },
        )
        assert other.status_code == 201
        other_id = other.json()["id"]
        yesterday = (self.today - timedelta(days=1)).isoformat()
        assert (await self.save()).status_code == 200
        assert (await self.save(supplementId=other_id)).status_code == 200
        assert (await self.save(date=yesterday)).status_code == 200
        assert (await self.save(taken=False)).status_code == 200
        current = await self.client.get(
            "/api/v1/med/supplement-doses", headers=self.headers, params={"date": self.today.isoformat()},
        )
        previous = await self.client.get(
            "/api/v1/med/supplement-doses", headers=self.headers, params={"date": yesterday},
        )
        assert current.json() == [{**self.payload, "supplementId": other_id}]
        assert previous.json() == [{**self.payload, "date": yesterday}]
