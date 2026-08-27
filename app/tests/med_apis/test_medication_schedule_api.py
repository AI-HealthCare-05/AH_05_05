import asyncio
from datetime import date, datetime, time

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase, TruncationTestCase

from app.main import app
from app.models.alarms import Alarm
from app.models.care import CareEpisode
from app.models.enums import AlarmStatus, AlarmType, MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User, UserSettings
from app.tests.med_apis.helpers import authentication_headers


async def create_ocr_medications(user: User) -> tuple[CareEpisode, Medication, Medication]:
    episode = await CareEpisode.create(
        user=user,
        title="2026-08-25 조제약 복약안내",
        medication_start_date=date(2026, 8, 25),
        medication_days=7,
    )
    scheduled = await Medication.create(
        care_episode=episode,
        name="셀레콕시브",
        dose="200mg",
        administration="아침·저녁 식후",
        times_per_day=2,
        days=7,
        prescribed_at=date(2026, 8, 25),
    )
    as_needed = await Medication.create(
        care_episode=episode,
        name="아세트아미노펜",
        dose="650mg",
        administration="6시간 이상 간격",
        times_per_day=None,
        days=7,
        prescribed_at=date(2026, 8, 25),
    )
    return episode, scheduled, as_needed


def schedule_url(record_id: int) -> str:
    return f"/api/v1/med/medication/schedule/{record_id}"


def schedule_payload(medication_id: int) -> dict[str, object]:
    return {
        "start": {"date": "2026-08-25", "slot": "morning"},
        "mealTimes": {
            "morning": "08:00",
            "lunch": "12:30",
            "evening": "18:30",
            "bedtime": "22:30",
        },
        "medications": [
            {"medicationId": medication_id, "slots": ["morning", "evening"]},
        ],
    }


class TestMedicationScheduleAPI(TestCase):
    async def test_openapi_exposes_only_path_scoped_schedule_contract(self) -> None:
        schema = app.openapi()
        schedule_path = "/api/v1/med/medication/schedule/{record_id}"

        assert schedule_path in schema["paths"]
        assert {"get", "put"} <= set(schema["paths"][schedule_path])
        assert "/api/v1/medications/schedule" not in schema["paths"]

        get_parameters = schema["paths"][schedule_path]["get"]["parameters"]
        assert get_parameters == [
            {
                "name": "record_id",
                "in": "path",
                "required": True,
                "schema": {"type": "integer", "minimum": 1, "title": "Record Id"},
            }
        ]
        request_properties = schema["components"]["schemas"]["SaveMedicationScheduleRequest"]["properties"]
        assert "recordId" not in request_properties

    async def test_old_schedule_route_is_removed(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            old_get = await client.get("/api/v1/medications/schedule", params={"recordId": 1})
            old_put = await client.put("/api/v1/medications/schedule", json={})

        assert old_get.status_code == status.HTTP_404_NOT_FOUND
        assert old_put.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    async def test_schedule_path_requires_positive_integer_record_id(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await authentication_headers(client, "schedule-path@example.com", "01022000010")
            zero = await client.get(schedule_url(0), headers=headers)
            text = await client.get("/api/v1/med/medication/schedule/not-an-id", headers=headers)

        assert zero.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert text.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_schedule_routes_require_authentication_without_writes(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-auth-owner@example.com"
            await authentication_headers(client, email, "01022000011")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)

            unauthorized_get = await client.get(schedule_url(episode.id))
            unauthorized_put = await client.put(
                schedule_url(episode.id),
                json=schedule_payload(scheduled.id),
            )

        assert unauthorized_get.status_code == status.HTTP_401_UNAUTHORIZED
        assert unauthorized_put.status_code == status.HTTP_401_UNAUTHORIZED
        assert await MedicationSlot.filter(medication=scheduled).count() == 0

    async def test_new_record_without_settings_returns_null_meal_times_for_frontend_defaults(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-load@example.com"
            headers = await authentication_headers(client, email, "01022000001")
            user = await User.get(email=email)
            episode, scheduled, as_needed = await create_ocr_medications(user)
            await UserSettings.filter(user=user).delete()

            response = await client.get(
                schedule_url(episode.id),
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "start": None,
            "mealTimes": None,
            "medications": [
                {
                    "medicationId": scheduled.id,
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
                    "timing": "6시간 이상 간격",
                    "slots": [],
                },
            ],
        }

    async def test_new_record_uses_existing_user_settings_times_even_without_start(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-existing-settings@example.com"
            headers = await authentication_headers(client, email, "01022000008")
            user = await User.get(email=email)
            episode, _, _ = await create_ocr_medications(user)
            settings = await UserSettings.get(user=user)
            settings.morning_medication_time = time(7, 30)
            settings.lunch_medication_time = time(12, 0)
            settings.evening_medication_time = time(18, 0)
            settings.bedtime_medication_time = time(21, 30)
            await settings.save(
                update_fields=[
                    "morning_medication_time",
                    "lunch_medication_time",
                    "evening_medication_time",
                    "bedtime_medication_time",
                ]
            )

            response = await client.get(
                schedule_url(episode.id),
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["start"] is None
        assert response.json()["mealTimes"] == {
            "morning": "07:30",
            "lunch": "12:00",
            "evening": "18:00",
            "bedtime": "21:30",
        }

    async def test_save_replaces_slots_and_returns_persisted_lowercase_schedule(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-save@example.com"
            headers = await authentication_headers(client, email, "01022000002")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)
            await MedicationSlot.create(medication=scheduled, slot=MealSlot.LUNCH)

            saved = await client.put(
                schedule_url(episode.id),
                json=schedule_payload(scheduled.id),
                headers=headers,
            )
            loaded = await client.get(
                schedule_url(episode.id),
                headers=headers,
            )

        assert saved.status_code == status.HTTP_200_OK
        assert saved.json() == {"saved": True}
        assert loaded.status_code == status.HTTP_200_OK
        assert loaded.json()["start"] == {"date": "2026-08-25", "slot": "morning"}
        assert loaded.json()["mealTimes"] == {
            "morning": "08:00",
            "lunch": "12:30",
            "evening": "18:30",
            "bedtime": "22:30",
        }
        assert loaded.json()["medications"][0]["slots"] == ["morning", "evening"]

        stored_episode = await CareEpisode.get(id=episode.id)
        assert stored_episode.medication_start_date == date(2026, 8, 25)
        assert stored_episode.medication_start_slot == MealSlot.MORNING
        assert await MedicationSlot.filter(medication=scheduled).count() == 2

    async def test_save_creates_active_user_slot_medication_alarms(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-alarm-create@example.com"
            headers = await authentication_headers(client, email, "01022000012")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)
            payload = schedule_payload(scheduled.id)
            payload["start"]["date"] = datetime.now().date().isoformat()  # type: ignore[index]

            response = await client.put(
                schedule_url(episode.id),
                json=payload,
                headers=headers,
            )

        alarms = await Alarm.filter(user=user, alarm_type=AlarmType.MEDICATION).order_by("meal_slot")
        assert response.status_code == status.HTTP_200_OK
        assert {alarm.meal_slot for alarm in alarms} == {MealSlot.MORNING, MealSlot.EVENING}
        assert all(alarm.status == AlarmStatus.ACTIVE for alarm in alarms)
        assert all(alarm.care_episode_id is None for alarm in alarms)
        assert all(alarm.title == "복약 알림" for alarm in alarms)
        assert all(alarm.message == "약을 복용할 시간입니다." for alarm in alarms)
        assert all(alarm.recurrence_rule and alarm.recurrence_rule.startswith("FREQ=DAILY;COUNT=") for alarm in alarms)
        assert {alarm.scheduled_at.strftime("%H:%M") for alarm in alarms} == {"08:00", "18:30"}
        assert all(alarm.next_trigger_at == alarm.scheduled_at for alarm in alarms)

    async def test_save_updates_existing_user_settings_times(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-update-settings@example.com"
            headers = await authentication_headers(client, email, "01022000009")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)
            existing_settings = await UserSettings.get(user=user)
            existing_settings.morning_medication_time = time(7, 0)
            existing_settings.lunch_medication_time = time(12, 0)
            existing_settings.evening_medication_time = time(18, 0)
            existing_settings.bedtime_medication_time = time(21, 0)
            await existing_settings.save(
                update_fields=[
                    "morning_medication_time",
                    "lunch_medication_time",
                    "evening_medication_time",
                    "bedtime_medication_time",
                ]
            )

            saved = await client.put(
                schedule_url(episode.id),
                json=schedule_payload(scheduled.id),
                headers=headers,
            )
            loaded = await client.get(
                schedule_url(episode.id),
                headers=headers,
            )

        stored_settings = await UserSettings.get(user=user)
        assert saved.status_code == status.HTTP_200_OK
        assert stored_settings.id == existing_settings.id
        assert await UserSettings.filter(user=user).count() == 1
        assert loaded.json()["mealTimes"] == {
            "morning": "08:00",
            "lunch": "12:30",
            "evening": "18:30",
            "bedtime": "22:30",
        }

    async def test_schedule_is_owner_scoped(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            owner_email = "schedule-owner@example.com"
            owner_headers = await authentication_headers(client, owner_email, "01022000003")
            other_headers = await authentication_headers(client, "schedule-other@example.com", "01022000004")
            owner = await User.get(email=owner_email)
            episode, scheduled, _ = await create_ocr_medications(owner)

            hidden_get = await client.get(
                schedule_url(episode.id),
                headers=other_headers,
            )
            hidden_put = await client.put(
                schedule_url(episode.id),
                json=schedule_payload(scheduled.id),
                headers=other_headers,
            )

        assert owner_headers
        assert hidden_get.status_code == status.HTTP_404_NOT_FOUND
        assert hidden_put.status_code == status.HTTP_404_NOT_FOUND
        assert hidden_get.json()["code"] == "MEDICATION_SCHEDULE_NOT_FOUND"
        assert hidden_put.json()["code"] == "MEDICATION_SCHEDULE_NOT_FOUND"
        assert await MedicationSlot.filter(medication=scheduled).count() == 0

    async def test_save_rejects_missing_scheduled_medication_without_partial_writes(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-invalid@example.com"
            headers = await authentication_headers(client, email, "01022000005")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)
            payload = schedule_payload(scheduled.id)
            payload["medications"] = []

            response = await client.put(
                schedule_url(episode.id),
                json=payload,
                headers=headers,
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "INVALID_MEDICATION_SCHEDULE"
        stored_episode = await CareEpisode.get(id=episode.id)
        assert stored_episode.medication_start_slot is None
        assert await MedicationSlot.filter(medication=scheduled).count() == 0

    async def test_save_rejects_invalid_slots_times_and_future_date(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-validation@example.com"
            headers = await authentication_headers(client, email, "01022000006")
            user = await User.get(email=email)
            episode, scheduled, _ = await create_ocr_medications(user)

            duplicate_slots = schedule_payload(scheduled.id)
            duplicate_slots["medications"][0]["slots"] = ["morning", "morning"]  # type: ignore[index]

            unordered_times = schedule_payload(scheduled.id)
            unordered_times["mealTimes"]["lunch"] = "07:30"  # type: ignore[index]

            off_grid_time = schedule_payload(scheduled.id)
            off_grid_time["mealTimes"]["morning"] = "08:15"  # type: ignore[index]

            future_start = schedule_payload(scheduled.id)
            future_start["start"]["date"] = "2999-01-01"  # type: ignore[index]

            compact_date = schedule_payload(scheduled.id)
            compact_date["start"]["date"] = "20260825"  # type: ignore[index]

            iso_week_date = schedule_payload(scheduled.id)
            iso_week_date["start"]["date"] = "2026-W35-2"  # type: ignore[index]

            responses = [
                await client.put(schedule_url(episode.id), json=payload, headers=headers)
                for payload in (
                    duplicate_slots,
                    unordered_times,
                    off_grid_time,
                    future_start,
                    compact_date,
                    iso_week_date,
                )
            ]

        assert [response.status_code for response in responses] == [
            status.HTTP_422_UNPROCESSABLE_CONTENT,
        ] * 6
        assert all(
            response.json()["code"] in {"INVALID_MEDICATION_SCHEDULE", "VALIDATION_ERROR"} for response in responses
        )
        stored_episode = await CareEpisode.get(id=episode.id)
        assert stored_episode.medication_start_slot is None
        assert await MedicationSlot.filter(medication=scheduled).count() == 0


class TestConcurrentMedicationScheduleAPI(TruncationTestCase):
    async def test_first_saves_for_two_records_create_one_user_settings_row(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            email = "schedule-concurrent@example.com"
            headers = await authentication_headers(client, email, "01022000007")
            user = await User.get(email=email)
            first_episode, first_medication, _ = await create_ocr_medications(user)
            second_episode, second_medication, _ = await create_ocr_medications(user)
            await UserSettings.filter(user=user).delete()

            responses = await asyncio.gather(
                client.put(
                    schedule_url(first_episode.id),
                    json=schedule_payload(first_medication.id),
                    headers=headers,
                ),
                client.put(
                    schedule_url(second_episode.id),
                    json=schedule_payload(second_medication.id),
                    headers=headers,
                ),
            )

        assert [response.status_code for response in responses] == [status.HTTP_200_OK] * 2
        assert await UserSettings.filter(user=user).count() == 1
