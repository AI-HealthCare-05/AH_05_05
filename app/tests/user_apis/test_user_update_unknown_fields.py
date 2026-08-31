from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User

EMAIL = "unknown_fields@example.com"
PASSWORD = "Password123!"


class TestUserUpdateRejectsUnknownFields(TestCase):
    """모르는 필드를 조용히 버리고 200 을 주던 문제를 막는다.

    전 필드가 선택이라 알아듣지 못한 키가 사라지면 "바꿀 항목 0개"가 되어
    성공 응답이 나갔다. 오타나 표기법 실수가 저장 성공으로 보였다.
    """

    async def _signed_in(self, client: AsyncClient) -> dict[str, str]:
        await client.post(
            "/api/v1/auth/signup",
            json={
                "email": EMAIL,
                "password": PASSWORD,
                "name": "원래이름",
                "phone_number": "01044445555",
                "birth_date": "1990-01-01",
                "gender": "MALE",
                "is_terms_agreed": True,
            },
        )
        login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def test_camel_case_body_is_rejected_instead_of_silently_ignored(self):
        # 프론트가 표기법을 잘못 보내면 저장이 안 된 채 성공으로 보였다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch(
                "/api/v1/users/me",
                headers=headers,
                json={"birthDate": "1985-03-03", "phoneNumber": "01011112222"},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["code"] == "VALIDATION_ERROR"

        user = await User.get(email=EMAIL)
        assert user.birth_date.isoformat() == "1990-01-01"

    async def test_misspelled_field_is_rejected(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch(
                "/api/v1/users/me",
                headers=headers,
                json={"name": "새이름", "phone_nubmer": "01011112222"},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        # 이름 하나만 바뀌는 부분 적용도 일어나면 안 된다.
        assert (await User.get(email=EMAIL)).name == "원래이름"

    async def test_empty_body_still_succeeds(self):
        # "아무 항목도 안 보냄"은 여전히 허용한다. 모르는 필드를 보낸 것과 다르다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch("/api/v1/users/me", headers=headers, json={})

        assert response.status_code == status.HTTP_200_OK
        assert (await User.get(email=EMAIL)).name == "원래이름"

    async def test_known_fields_still_update(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch(
                "/api/v1/users/me",
                headers=headers,
                json={"name": "바뀐이름", "birth_date": "1985-03-03"},
            )

        assert response.status_code == status.HTTP_200_OK
        user = await User.get(email=EMAIL)
        assert user.name == "바뀐이름"
        assert user.birth_date.isoformat() == "1985-03-03"

    async def test_notify_settings_also_rejects_unknown_fields(self):
        # 같은 이유로 전 필드가 선택인 알림 설정도 막는다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            unknown = await client.patch(
                "/api/v1/me/settings",
                headers=headers,
                json={"notifyMedicaton": True},  # 오타
            )
            camel = await client.patch("/api/v1/me/settings", headers=headers, json={"notifyMedication": True})
            # CamelModel 은 populate_by_name=True 라 필드명(snake)도 그대로 받는다.
            # 둘 다 정상 입력이며, 막는 것은 어느 쪽도 아닌 키다.
            snake = await client.patch("/api/v1/me/settings", headers=headers, json={"notify_supplement": True})

        assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert camel.status_code == status.HTTP_200_OK
        assert snake.status_code == status.HTTP_200_OK
