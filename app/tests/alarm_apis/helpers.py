from datetime import datetime

from httpx import AsyncClient

from app.dtos.alarms import AlarmCreateRequest
from app.models.enums import AccountStatus, AlarmType, MealSlot
from app.models.users import User


async def create_user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="hashed-password",
        status=AccountStatus.ACTIVE,
        name="알람 테스트 사용자",
    )


def medication_alarm_request() -> AlarmCreateRequest:
    return AlarmCreateRequest(
        alarm_type=AlarmType.MEDICATION,
        meal_slot=MealSlot.MORNING,
        title="아침약",
        message="약을 복용할 시간입니다.",
        scheduled_at=datetime.fromisoformat("2026-08-20T08:00:00+09:00"),
        recurrence_rule="FREQ=DAILY",
        timezone="Asia/Seoul",
    )


def medication_alarm_payload() -> dict[str, object]:
    return medication_alarm_request().model_dump(mode="json")


async def authentication_headers(client: AsyncClient, email: str, phone_number: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Password123!",
            "name": "알람테스트사용자",
            "phone_number": phone_number,
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}
