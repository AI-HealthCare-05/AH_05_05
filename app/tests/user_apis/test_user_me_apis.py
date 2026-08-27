from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User


class TestUserMeApis(TestCase):
    async def test_get_user_me_success(self):
        # 사용자 등록 및 로그인
        email = "me@example.com"
        signup_data = {
            "email": email,
            "password": "Password123!",
            "name": "내정보테스터",
            "phone_number": "01055556666",
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            access_token = login_response.json()["access_token"]

            # 내 정보 조회
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["email"] == email
        assert response.json()["name"] == "내정보테스터"

    async def test_update_user_me_success(self):
        # 사용자 등록 및 로그인
        email = "update_me@example.com"
        signup_data = {
            "email": email,
            "password": "Password123!",
            "name": "수정전",
            "phone_number": "01077778888",
            "birth_date": "1990-01-01",
            "gender": "MALE",
            "is_terms_agreed": True,
        }
        update_data = {"name": "수정후"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            access_token = login_response.json()["access_token"]

            # 내 정보 수정
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.patch("/api/v1/users/me", json=update_data, headers=headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "수정후"

    async def test_get_user_me_unauthorized(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_update_user_me_allows_duplicate_phone_number(self):
        first_signup = {
            "email": "first@example.com",
            "password": "Password123!",
            "name": "첫번째",
            "phone_number": "01011112222",
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        second_signup = {**first_signup, "email": "second@example.com", "phone_number": "01033334444"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=first_signup)
            await client.post("/api/v1/auth/signup", json=second_signup)
            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": first_signup["email"], "password": first_signup["password"]},
            )
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
            response = await client.patch(
                "/api/v1/users/me",
                json={"phone_number": "010-3333-4444"},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["phone_number"] == "01033334444"
        assert await User.filter(phone="01033334444").count() == 2
