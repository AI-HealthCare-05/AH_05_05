from unittest.mock import patch

from cryptography.fernet import Fernet
from starlette import status
from tortoise.contrib.test import TestCase

from app.core.smtp_settings_encryption import decrypt_smtp_password
from app.models.admin_settings import AdminSetting
from app.models.enums import AdminRole
from app.services.admin_settings import SmtpRuntimeSettings, SmtpSettingsService
from app.tests.admin_apis.conftest import auth_header, create_admin, request

SMTP_SETTINGS_URL = "/api/v1/admin/settings/smtp"
SMTP_PAYLOAD = {
    "smtpHost": "smtp.gmail.com",
    "smtpPort": 587,
    "smtpUser": "sender@example.com",
    "smtpPassword": "gmail-app-password",
    "smtpFromEmail": "sender@example.com",
}


class TestAdminSmtpSettingsAPI(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="최고관리자", email="root@example.com", role=AdminRole.ADMIN)
        self.staff = await create_admin(name="일반관리자", email="staff@example.com", role=AdminRole.STAFF)
        self.headers = auth_header(self.admin.id)
        self.encryption_key = Fernet.generate_key().decode()
        self.key_patch = patch(
            "app.core.smtp_settings_encryption.config.SMTP_SETTINGS_ENCRYPTION_KEY",
            self.encryption_key,
        )
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    async def test_admin_can_create_smtp_settings_without_password_exposure(self) -> None:
        response = await request("PUT", SMTP_SETTINGS_URL, headers=self.headers, json=SMTP_PAYLOAD)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "smtpHost": "smtp.gmail.com",
            "smtpPort": 587,
            "smtpUser": "sender@example.com",
            "smtpFromEmail": "sender@example.com",
            "smtpPasswordConfigured": True,
        }
        assert "password" not in response.text.lower().replace("passwordconfigured", "")

        setting = await AdminSetting.get(setting_key="SMTP")
        assert setting.smtp_password_enc != "gmail-app-password"
        assert decrypt_smtp_password(setting.smtp_password_enc, key=self.encryption_key) == "gmail-app-password"
        assert setting.updated_by_admin_id == self.admin.id

    async def test_get_returns_saved_settings_without_password(self) -> None:
        await request("PUT", SMTP_SETTINGS_URL, headers=self.headers, json=SMTP_PAYLOAD)

        response = await request("GET", SMTP_SETTINGS_URL, headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["smtpPasswordConfigured"] is True
        assert "gmail-app-password" not in response.text
        assert "smtpPassword" not in response.json()

    async def test_get_without_saved_settings_returns_env_defaults(self) -> None:
        with (
            patch("app.services.admin_settings.config.SMTP_HOST", "smtp.env.example.com"),
            patch("app.services.admin_settings.config.SMTP_PORT", 2525),
            patch("app.services.admin_settings.config.SMTP_USER", "env-user@example.com"),
            patch("app.services.admin_settings.config.SMTP_PASSWORD", "env-password"),
            patch("app.services.admin_settings.config.SMTP_FROM_EMAIL", "env-from@example.com"),
        ):
            response = await request("GET", SMTP_SETTINGS_URL, headers=self.headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "smtpHost": "smtp.env.example.com",
            "smtpPort": 2525,
            "smtpUser": "env-user@example.com",
            "smtpFromEmail": "env-from@example.com",
            "smtpPasswordConfigured": True,
        }
        assert not await AdminSetting.exists()

    async def test_email_runtime_without_saved_settings_uses_env_defaults(self) -> None:
        with (
            patch("app.services.admin_settings.config.SMTP_HOST", "smtp.env.example.com"),
            patch("app.services.admin_settings.config.SMTP_PORT", 2525),
            patch("app.services.admin_settings.config.SMTP_USER", "env-user@example.com"),
            patch("app.services.admin_settings.config.SMTP_PASSWORD", "env-password"),
            patch("app.services.admin_settings.config.SMTP_FROM_EMAIL", "env-from@example.com"),
        ):
            settings = await SmtpSettingsService().get_runtime_settings()

        assert settings == SmtpRuntimeSettings(
            host="smtp.env.example.com",
            port=2525,
            username="env-user@example.com",
            password="env-password",
            from_email="env-from@example.com",
        )
        assert not await AdminSetting.exists()

    async def test_blank_password_keeps_existing_encrypted_password(self) -> None:
        await request("PUT", SMTP_SETTINGS_URL, headers=self.headers, json=SMTP_PAYLOAD)
        before = await AdminSetting.get(setting_key="SMTP")
        encrypted_before = before.smtp_password_enc
        updated_payload = {
            **SMTP_PAYLOAD,
            "smtpHost": "smtp.changed.example.com",
            "smtpPassword": "",
        }

        response = await request("PUT", SMTP_SETTINGS_URL, headers=self.headers, json=updated_payload)

        assert response.status_code == status.HTTP_200_OK
        await before.refresh_from_db()
        assert before.smtp_host == "smtp.changed.example.com"
        assert before.smtp_password_enc == encrypted_before

    async def test_first_save_requires_password(self) -> None:
        response = await request(
            "PUT",
            SMTP_SETTINGS_URL,
            headers=self.headers,
            json={**SMTP_PAYLOAD, "smtpPassword": ""},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "SMTP_PASSWORD_REQUIRED"
        assert not await AdminSetting.exists()

    async def test_staff_cannot_read_or_update_smtp_settings(self) -> None:
        staff_headers = auth_header(self.staff.id)

        get_response = await request("GET", SMTP_SETTINGS_URL, headers=staff_headers)
        put_response = await request("PUT", SMTP_SETTINGS_URL, headers=staff_headers, json=SMTP_PAYLOAD)

        assert get_response.status_code == status.HTTP_403_FORBIDDEN
        assert put_response.status_code == status.HTTP_403_FORBIDDEN

    async def test_invalid_port_is_rejected(self) -> None:
        response = await request(
            "PUT",
            SMTP_SETTINGS_URL,
            headers=self.headers,
            json={**SMTP_PAYLOAD, "smtpPort": 70000},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
