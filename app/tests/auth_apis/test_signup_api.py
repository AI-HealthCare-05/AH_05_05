from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase
from tortoise.exceptions import IntegrityError

from app.main import app
from app.models.users import User, UserSettings
from app.repositories.user_repository import UserRepository
from app.tests.conftest import TEST_PHONE_ENCRYPTION_KEY


class TestSignupAPI(TestCase):
    @staticmethod
    def signup_data(**overrides):
        data = {
            "email": "test@example.com",
            "password": "Password123!",
            "name": "테스터",
            "phone_number": "01012345678",
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        data.update(overrides)
        return data

    async def test_signup_success(self):
        signup_data = self.signup_data()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json() == {"detail": "회원가입이 성공적으로 완료되었습니다."}

        user = await User.get(email=signup_data["email"])
        settings = await UserSettings.get(user_id=user.id)
        assert user.phone != signup_data["phone_number"]
        assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(user.phone.encode()).decode() == signup_data["phone_number"]
        assert user.birth_date.isoformat() == signup_data["birth_date"]
        assert user.gender.value == signup_data["gender"]
        assert settings.is_terms_agreed is True
        assert settings.terms_agreed_at is not None
        assert settings.terms_agreed_at <= datetime.now(settings.terms_agreed_at.tzinfo)
        assert settings.is_notify_medication is False
        assert settings.is_notify_schedule is False
        assert settings.is_notify_guide is False
        assert settings.morning_medication_time == timedelta(hours=8)
        assert settings.lunch_medication_time == timedelta(hours=13)
        assert settings.evening_medication_time == timedelta(hours=19)
        assert settings.bedtime_medication_time == timedelta(hours=22)

    async def test_signup_invalid_email(self):
        signup_data = self.signup_data(email="invalid-email")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_signup_requires_terms_agreement(self):
        signup_data = self.signup_data(is_terms_agreed=False)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert response.json()["field"] == "is_terms_agreed"
        assert await User.filter(email=signup_data["email"]).exists() is False

    async def test_signup_accepts_phone_prefix_supported_by_existing_ui(self):
        signup_data = self.signup_data(phone_number="0111234567")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)

        assert response.status_code == status.HTTP_201_CREATED
        user = await User.get(email=signup_data["email"])
        assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(user.phone.encode()).decode() == "0111234567"

    async def test_signup_returns_field_error_for_duplicate_email(self):
        signup_data = self.signup_data()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/api/v1/auth/signup", json=signup_data)
            duplicate = await client.post(
                "/api/v1/auth/signup",
                json=self.signup_data(phone_number="01099998888"),
            )

        assert first.status_code == status.HTTP_201_CREATED
        assert duplicate.status_code == status.HTTP_409_CONFLICT
        assert duplicate.json() == {
            "code": "EMAIL_ALREADY_EXISTS",
            "message": "이미 사용중인 이메일입니다.",
            "field": "email",
        }

    async def test_signup_allows_duplicate_phone_number(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post("/api/v1/auth/signup", json=self.signup_data())
            second = await client.post(
                "/api/v1/auth/signup",
                json=self.signup_data(email="other@example.com"),
            )

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_201_CREATED
        users = await User.filter(email__in=["test@example.com", "other@example.com"]).order_by("email")
        assert users[0].phone != users[1].phone
        assert {Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(user.phone.encode()).decode() for user in users} == {
            "01012345678"
        }

    async def test_signup_maps_concurrent_email_unique_violation_to_conflict(self):
        email_exists = AsyncMock(side_effect=[False, True])
        create_user = AsyncMock(side_effect=IntegrityError("duplicate email"))

        with (
            patch.object(UserRepository, "exists_by_email", email_exists),
            patch.object(UserRepository, "create_user", create_user),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/auth/signup", json=self.signup_data())

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json() == {
            "code": "EMAIL_ALREADY_EXISTS",
            "message": "이미 사용중인 이메일입니다.",
            "field": "email",
        }

    async def test_signup_rejects_missing_new_fields_invalid_gender_and_non_boolean_terms(self):
        missing_birth_date = self.signup_data()
        missing_birth_date.pop("birth_date")
        invalid_payloads = (
            (missing_birth_date, "birth_date"),
            (self.signup_data(gender="UNKNOWN"), "gender"),
            (self.signup_data(is_terms_agreed=1), "is_terms_agreed"),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for payload, expected_field in invalid_payloads:
                response = await client.post("/api/v1/auth/signup", json=payload)
                assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
                assert response.json()["code"] == "VALIDATION_ERROR"
                assert response.json()["field"] == expected_field

    async def test_signup_rolls_back_user_when_settings_creation_fails(self):
        signup_data = self.signup_data()

        with patch.object(UserSettings, "create", side_effect=RuntimeError("settings failure")):
            with pytest.raises(RuntimeError, match="settings failure"):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    await client.post("/api/v1/auth/signup", json=signup_data)

        assert await User.filter(email=signup_data["email"]).exists() is False
