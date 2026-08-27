from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import UserSettings


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
        }

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
