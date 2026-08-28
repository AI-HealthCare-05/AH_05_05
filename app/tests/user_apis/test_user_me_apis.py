from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.users import User
from app.tests.conftest import TEST_PHONE_ENCRYPTION_KEY


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
        assert response.json()["phone_number"] == signup_data["phone_number"]
        stored_user = await User.get(email=email)
        assert stored_user.phone != signup_data["phone_number"]

    async def test_get_user_me_returns_birth_date_and_gender(self):
        """마이페이지 「기본정보」 네 칸을 채우려면 이 둘이 응답에 있어야 한다.

        가입 때 받아 저장하고 있었으나 조회 응답에 싣지 않아, 화면이 폼을 채우지 못했다.
        """
        email = "profile_fields@example.com"
        signup_data = {
            "email": email,
            "password": "Password123!",
            "name": "기본정보",
            "phone_number": "01012341234",
            "birth_date": "1988-03-14",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)
            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

            response = await client.get("/api/v1/users/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["birth_date"] == "1988-03-14"
        assert body["gender"] == "FEMALE"

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

    async def test_update_user_me_changes_birth_date_and_gender(self):
        """생년월일·성별을 고칠 경로가 없었다. 마이페이지가 이 둘을 편집한다."""
        email = "update_profile_fields@example.com"
        signup_data = {
            "email": email,
            "password": "Password123!",
            "name": "수정전",
            "phone_number": "01099998888",
            "birth_date": "1990-01-01",
            "gender": "MALE",
            "is_terms_agreed": True,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)
            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

            response = await client.patch(
                "/api/v1/users/me",
                json={"birth_date": "1985-12-25", "gender": "FEMALE"},
                headers=headers,
            )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["birth_date"] == "1985-12-25"
        assert body["gender"] == "FEMALE"
        stored_user = await User.get(email=email)
        assert str(stored_user.birth_date) == "1985-12-25"

    async def test_update_user_me_keeps_untouched_fields(self):
        """보낸 항목만 바뀐다(exclude_none). 이름만 고쳐도 생년월일·성별이 남아야 한다."""
        email = "partial_update@example.com"
        signup_data = {
            "email": email,
            "password": "Password123!",
            "name": "부분수정",
            "phone_number": "01044443333",
            "birth_date": "1992-07-07",
            "gender": "MALE",
            "is_terms_agreed": True,
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)
            login_response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

            response = await client.patch("/api/v1/users/me", json={"name": "이름만"}, headers=headers)

        body = response.json()
        assert body["name"] == "이름만"
        assert body["birth_date"] == "1992-07-07"
        assert body["gender"] == "MALE"

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
        first_user = await User.get(email=first_signup["email"])
        second_user = await User.get(email=second_signup["email"])
        assert first_user.phone != second_user.phone
        assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(first_user.phone.encode()).decode() == "01033334444"
        assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(second_user.phone.encode()).decode() == "01033334444"
