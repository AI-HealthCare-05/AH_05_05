from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core.utils.security import verify_password
from app.main import app
from app.models.users import User

EMAIL = "password_change@example.com"
CURRENT_PASSWORD = "Password123!"
NEW_PASSWORD = "NewPassword456!"


class TestUserPasswordApi(TestCase):
    @staticmethod
    def signup_data(**overrides):
        data = {
            "email": EMAIL,
            "password": CURRENT_PASSWORD,
            "name": "비번테스터",
            "phone_number": "01055556666",
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        data.update(overrides)
        return data

    async def _signed_in_client(self, client: AsyncClient) -> dict[str, str]:
        await client.post("/api/v1/auth/signup", json=self.signup_data())
        login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": CURRENT_PASSWORD})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def test_change_password_updates_hash_and_allows_login_with_new_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)
            before = (await User.get(email=EMAIL)).hashed_password

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": CURRENT_PASSWORD, "newPassword": NEW_PASSWORD},
            )

            assert response.status_code == status.HTTP_200_OK
            assert response.json() == {"detail": "비밀번호가 변경되었습니다."}

            # 새 비밀번호로 로그인되고, 옛 비밀번호는 더 이상 통하지 않아야 한다.
            new_login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD})
            old_login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": CURRENT_PASSWORD})

        assert new_login.status_code == status.HTTP_200_OK
        assert old_login.status_code == status.HTTP_400_BAD_REQUEST

        user = await User.get(email=EMAIL)
        assert user.hashed_password != before
        # 평문이 저장되지 않는지 확인한다.
        assert user.hashed_password != NEW_PASSWORD
        assert verify_password(NEW_PASSWORD, user.hashed_password)

    async def test_change_password_rejects_wrong_current_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)
            before = (await User.get(email=EMAIL)).hashed_password

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": "WrongPassword123!", "newPassword": NEW_PASSWORD},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_PASSWORD"
        assert (await User.get(email=EMAIL)).hashed_password == before

    async def test_change_password_rejects_same_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": CURRENT_PASSWORD, "newPassword": CURRENT_PASSWORD},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "SAME_AS_CURRENT"

    async def test_change_password_applies_signup_password_policy(self):
        # 회원가입과 같은 validate_password 를 쓰는지 확인한다.
        # 정책이 갈리면 비밀번호 변경으로 약한 비밀번호를 심을 수 있다.
        weak_passwords = (
            "Ab1!",  # 8자 미만
            "alllowercase1!",  # 대문자 없음
            "NOLOWERCASE1!",  # 소문자 없음
            "NoSpecialChar1",  # 특수문자 없음
            "NoDigitHere!",  # 숫자 없음
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)
            before = (await User.get(email=EMAIL)).hashed_password

            for weak in weak_passwords:
                response = await client.patch(
                    "/api/v1/users/me/password",
                    headers=headers,
                    json={"currentPassword": CURRENT_PASSWORD, "newPassword": weak},
                )
                assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, weak
                assert response.json()["code"] == "VALIDATION_ERROR", weak
                # field 는 클라이언트가 보낸 표기법을 그대로 돌려준다. camelCase 로 보냈으니
                # newPassword 다. 화면이 이 값으로 오류를 붙일 칸을 고른다(PasswordChangeSheet).
                assert response.json()["field"] == "newPassword", weak

        assert (await User.get(email=EMAIL)).hashed_password == before

    async def test_change_password_requires_authentication(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/users/me/password",
                json={"currentPassword": CURRENT_PASSWORD, "newPassword": NEW_PASSWORD},
            )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_change_password_accepts_both_spellings(self):
        # CamelModel 은 populate_by_name=True 라 별칭(camel)과 필드명(snake)을 둘 다 받는다.
        # 이관(#172) 중에도 기존 snake_case 요청이 계속 통해야 한다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)

            camel = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": CURRENT_PASSWORD, "newPassword": NEW_PASSWORD},
            )
            snake = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"current_password": NEW_PASSWORD, "new_password": CURRENT_PASSWORD},
            )

        assert camel.status_code == status.HTTP_200_OK
        assert snake.status_code == status.HTTP_200_OK

    async def test_change_password_rejects_unknown_field_name(self):
        # 이름 자체가 틀린 키는 어느 표기법으로도 통하면 안 된다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in_client(client)

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPasword": CURRENT_PASSWORD, "newPassword": NEW_PASSWORD},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
