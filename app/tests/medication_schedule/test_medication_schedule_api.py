from datetime import date, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User, UserSettings
from app.tests.med_apis.helpers import authentication_headers


class TestMedicationScheduleAPI(TestCase):
    async def test_ocr_confirmed_episode_opens_schedule_with_its_real_medication_ids(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "schedule@example.com", "01021000101")
            user = await User.get(email="schedule@example.com")
            episode = await CareEpisode.create(
                user=user,
                title="8월 22일 약봉투",
                status=CareEpisodeStatus.ACTIVE,
            )
            regular = await Medication.create(
                care_episode=episode,
                name="셀레콕시브",
                dose="200mg",
                administration="아침·저녁 식후",
                times_per_day=2,
                days=7,
                prescribed_at=date(2026, 8, 22),
            )
            as_needed = await Medication.create(
                care_episode=episode,
                name="아세트아미노펜",
                dose="650mg",
                administration="필요 시",
                times_per_day=None,
                days=7,
                prescribed_at=date(2026, 8, 22),
            )

            response = await client.get(
                "/api/v1/medications/schedule",
                params={"recordId": episode.id},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "start": None,
            "mealTimes": None,
            "medications": [
                {
                    "medicationId": regular.id,
                    "name": "셀레콕시브",
                    "dose": "200mg",
                    "timesPerDay": 2,
                    "timing": "아침·저녁 식후",
                    "slots": [],
                },
                {
                    "medicationId": as_needed.id,
                    "name": "아세트아미노펜",
                    "dose": "650mg",
                    "timesPerDay": None,
                    "timing": "필요 시",
                    "slots": [],
                },
            ],
        }

    async def test_schedule_save_persists_start_times_and_slots_for_the_confirmed_episode(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "schedule-save@example.com", "01021000102")
            user = await User.get(email="schedule-save@example.com")
            episode = await CareEpisode.create(
                user=user,
                title="8월 22일 약봉투",
                status=CareEpisodeStatus.ACTIVE,
            )
            regular = await Medication.create(
                care_episode=episode,
                name="셀레콕시브",
                dose="200mg",
                administration="아침·저녁 식후",
                times_per_day=2,
                days=7,
            )
            await Medication.create(
                care_episode=episode,
                name="아세트아미노펜",
                dose="650mg",
                administration="필요 시",
                times_per_day=None,
                days=7,
            )

            response = await client.put(
                "/api/v1/medications/schedule",
                headers=headers,
                json={
                    "recordId": episode.id,
                    "start": {"date": "2026-08-22", "slot": "morning"},
                    "mealTimes": {
                        "morning": "08:00",
                        "lunch": "13:00",
                        "evening": "19:00",
                        "bedtime": "22:00",
                    },
                    "medications": [
                        {"medicationId": regular.id, "slots": ["morning", "evening"]},
                    ],
                },
            )
            reloaded = await client.get(
                "/api/v1/medications/schedule",
                params={"recordId": episode.id},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"saved": True}

        await episode.refresh_from_db()
        settings = await UserSettings.get(user_id=user.id)
        saved_slots = await MedicationSlot.filter(medication_id=regular.id).order_by("slot")

        assert episode.medication_start_date == date(2026, 8, 22)
        assert episode.medication_start_slot == MealSlot.MORNING
        assert settings.morning_medication_time == timedelta(hours=8)
        assert settings.bedtime_medication_time == timedelta(hours=22)
        assert {slot.slot for slot in saved_slots} == {MealSlot.MORNING, MealSlot.EVENING}
        assert reloaded.status_code == status.HTTP_200_OK
        assert reloaded.json()["mealTimes"] == {
            "morning": "08:00",
            "lunch": "13:00",
            "evening": "19:00",
            "bedtime": "22:00",
        }
