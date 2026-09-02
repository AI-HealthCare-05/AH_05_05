from datetime import datetime, time, timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.main import app
from app.models.alarms import Alarm
from app.models.care import CareEpisode
from app.models.enums import AlarmType, MealSlot
from app.models.medications import Medication
from app.models.users import User, UserSettings


class TestNotifySettingsApis(TestCase):
    async def create_authenticated_client(self, email: str) -> tuple[AsyncClient, dict[str, str]]:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        signup_response = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "Password123!",
                "name": "알림테스터",
                "phone_number": "01012345678",
                "birth_date": "1990-01-01",
                "gender": "FEMALE",
                "is_terms_agreed": True,
            },
        )
        assert signup_response.status_code == status.HTTP_201_CREATED
        login_response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login_response.status_code == status.HTTP_200_OK
        return client, {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    async def test_get_settings_requires_authentication(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/me/settings")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_get_settings_returns_signup_defaults(self):
        client, headers = await self.create_authenticated_client("notify-defaults@example.com")
        try:
            response = await client.get("/api/v1/me/settings", headers=headers)
        finally:
            await client.aclose()

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "notifyMedication": False,
            "notifySupplement": False,
            "notifyConsentedAt": None,
            "morningMedicationTime": "08:00:00",
            "lunchMedicationTime": "13:00:00",
            "eveningMedicationTime": "19:00:00",
            "bedtimeMedicationTime": "22:00:00",
        }

    async def test_patch_updates_one_time_and_keeps_the_other_three(self):
        client, headers = await self.create_authenticated_client("notify-time@example.com")
        try:
            response = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"morningMedicationTime": "07:30"},
            )
        finally:
            await client.aclose()

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert {
            key: body[key]
            for key in (
                "morningMedicationTime",
                "lunchMedicationTime",
                "eveningMedicationTime",
                "bedtimeMedicationTime",
            )
        } == {
            "morningMedicationTime": "07:30:00",
            "lunchMedicationTime": "13:00:00",
            "eveningMedicationTime": "19:00:00",
            "bedtimeMedicationTime": "22:00:00",
        }

    async def test_patch_rejects_invalid_order_after_merging_database_values(self):
        client, headers = await self.create_authenticated_client("notify-order@example.com")
        try:
            response = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"morningMedicationTime": "21:00"},
            )
        finally:
            await client.aclose()

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        settings = await UserSettings.get(user__email="notify-order@example.com")
        assert settings.morning_medication_time in {time(8, 0), timedelta(hours=8)}

    async def test_patch_resynchronizes_existing_medication_alarm(self):
        email = "notify-alarm-time@example.com"
        client, headers = await self.create_authenticated_client(email)
        user = await User.get(email=email)
        today = datetime.now(config.TIMEZONE).date()
        episode = await CareEpisode.create(
            user=user,
            title="복약 시간 변경 테스트",
            medication_start_date=today,
            medication_days=7,
        )
        medication = await Medication.create(
            care_episode=episode,
            name="시간 변경 약",
            times_per_day=1,
            days=7,
            prescribed_at=today,
        )
        try:
            scheduled = await client.put(
                f"/api/v1/med/medication/schedule/{episode.id}",
                headers=headers,
                json={
                    "start": {"date": today.isoformat(), "slot": "morning"},
                    "mealTimes": {
                        "morning": "08:00",
                        "lunch": "13:00",
                        "evening": "19:00",
                        "bedtime": "22:00",
                    },
                    "medications": [
                        {"medicationId": medication.id, "slots": ["morning"]},
                    ],
                },
            )
            patched = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"morningMedicationTime": "09:00"},
            )
        finally:
            await client.aclose()

        alarm = await Alarm.get(
            user=user,
            alarm_type=AlarmType.MEDICATION,
            meal_slot=MealSlot.MORNING,
        )
        assert scheduled.status_code == status.HTTP_200_OK
        assert patched.status_code == status.HTTP_200_OK
        assert alarm.scheduled_at.strftime("%H:%M") == "09:00"
        assert alarm.next_trigger_at == alarm.scheduled_at

    async def test_patch_updates_only_supplied_setting_and_records_first_consent(self):
        client, headers = await self.create_authenticated_client("notify-patch@example.com")
        try:
            first_response = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"notifyMedication": True},
            )
            second_response = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"notifySupplement": True},
            )
        finally:
            await client.aclose()

        assert first_response.status_code == status.HTTP_200_OK
        first_body = first_response.json()
        assert first_body["notifyMedication"] is True
        assert first_body["notifySupplement"] is False
        assert first_body["notifyConsentedAt"] is not None

        assert second_response.status_code == status.HTTP_200_OK
        second_body = second_response.json()
        assert second_body["notifyMedication"] is True
        assert second_body["notifySupplement"] is True
        assert second_body["notifyConsentedAt"] == first_body["notifyConsentedAt"]

        settings = await UserSettings.get(user__email="notify-patch@example.com")
        assert settings.is_notify_medication is True
        assert settings.is_notify_supplement is True
        assert settings.is_notify_schedule is False
        assert settings.is_notify_guide is False

    async def test_empty_patch_records_consent_without_changing_toggles(self):
        client, headers = await self.create_authenticated_client("notify-consent@example.com")
        try:
            response = await client.patch("/api/v1/me/settings", headers=headers, json={})
        finally:
            await client.aclose()

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["notifyConsentedAt"] is not None
        settings = await UserSettings.get(user__email="notify-consent@example.com")
        assert settings.is_notify_medication is False
        assert settings.is_notify_supplement is False
