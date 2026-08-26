from datetime import timedelta

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User, UserSettings


class TestSignupAPI(TestCase):
    async def test_signup_success(self):
        signup_data = {
            "email": "test@example.com",
            "password": "Password123!",
            "name": "테스터",
            "phone_number": "01012345678",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json() == {"detail": "회원가입이 성공적으로 완료되었습니다."}

        user = await User.get(email=signup_data["email"])
        settings = await UserSettings.get(user_id=user.id)
        assert settings.is_notify_medication is False
        assert settings.is_notify_schedule is False
        assert settings.is_notify_guide is False
        assert settings.morning_medication_time == timedelta(hours=8)
        assert settings.lunch_medication_time == timedelta(hours=13)
        assert settings.evening_medication_time == timedelta(hours=19)
        assert settings.bedtime_medication_time == timedelta(hours=22)

    async def test_signup_invalid_email(self):
        signup_data = {
            "email": "invalid-email",
            "password": "password123!",
            "name": "테스터",
            "phone_number": "01012345678",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
