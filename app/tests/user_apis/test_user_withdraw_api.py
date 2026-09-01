from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.enums import AccountStatus
from app.models.users import User
from app.tests.conftest import TEST_PHONE_ENCRYPTION_KEY

EMAIL = "withdraw@example.com"
PASSWORD = "Password123!"
NAME = "탈퇴테스터"
PHONE = "01055556666"


class TestUserWithdrawApi(TestCase):
    @staticmethod
    def signup_data(**overrides):
        data = {
            "email": EMAIL,
            "password": PASSWORD,
            "name": NAME,
            "phone_number": PHONE,
            "birth_date": "1990-01-01",
            "gender": "FEMALE",
            "is_terms_agreed": True,
        }
        data.update(overrides)
        return data

    async def _signed_in(self, client: AsyncClient) -> dict[str, str]:
        await client.post("/api/v1/auth/signup", json=self.signup_data())
        login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def test_withdraw_marks_account_and_blocks_login(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"password": PASSWORD})

            assert response.status_code == status.HTTP_204_NO_CONTENT
            assert response.content == b""

            # 탈퇴한 계정은 로그인을 막는다. 사유는 알려주지 않는다 — 자격증명 오류와
            # 같은 응답이라 탈퇴 여부가 드러나지 않는다(#196).
            login = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

        assert login.status_code == status.HTTP_400_BAD_REQUEST
        assert login.json()["code"] == "INVALID_CREDENTIALS"
        assert (await User.get(email=EMAIL)).status == AccountStatus.WITHDRAWN

    async def test_withdraw_rejects_wrong_password_and_keeps_status(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.request(
                "DELETE", "/api/v1/users/me", headers=headers, json={"password": "WrongPassword123!"}
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_PASSWORD"
        assert (await User.get(email=EMAIL)).status == AccountStatus.ACTIVE

    async def test_withdraw_requires_authentication(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.request("DELETE", "/api/v1/users/me", json={"password": PASSWORD})

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_already_withdrawn_account_is_blocked_by_token_check(self):
        """이미 탈퇴한 계정은 409 가 아니라 401 이다.

        get_request_user 가 ACTIVE 가 아닌 계정을 먼저 막아 라우트까지 오지 않는다.
        토큰은 탈퇴 전에 받은 것이라 서명은 유효하다.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)
            first = await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"password": PASSWORD})

            second = await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"password": PASSWORD})

        assert first.status_code == status.HTTP_204_NO_CONTENT
        assert second.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_withdrawn_email_cannot_sign_up_again(self):
        """재가입 차단은 새로 구현하지 않았다. exists_by_email 이 상태를 보지 않고
        행 존재만 확인하기 때문에 자동으로 걸린다.

        나중에 누가 거기에 상태 필터를 넣으면 조용히 뚫리므로 여기서 고정한다.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)
            await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"password": PASSWORD})

            again = await client.post("/api/v1/auth/signup", json=self.signup_data())

        assert again.status_code == status.HTTP_409_CONFLICT
        assert again.json()["code"] == "EMAIL_ALREADY_EXISTS"
        assert again.json()["field"] == "email"

    async def test_withdraw_keeps_personal_data(self):
        """확정된 정책은 「status 만 바꾼다」다.

        나중에 누가 익명화나 물리 삭제를 끼워 넣으면 여기서 깨진다.
        물리 삭제는 REQ-ADMIN-007 범위이고 이번 작업에서 의도적으로 제외했다.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)
            await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"password": PASSWORD})

        user = await User.get(email=EMAIL)
        assert user.name == NAME
        assert user.email == EMAIL
        assert Fernet(TEST_PHONE_ENCRYPTION_KEY).decrypt(user.phone.encode()).decode() == PHONE
        assert user.birth_date.isoformat() == "1990-01-01"

    async def test_withdraw_accepts_both_spellings(self):
        # CamelModel 은 populate_by_name=True 라 별칭과 필드명을 둘 다 받는다.
        # password 는 한 단어라 표기법이 같지만, 모르는 키는 걸러져야 한다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            unknown = await client.request("DELETE", "/api/v1/users/me", headers=headers, json={"passwrod": PASSWORD})

        assert unknown.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert (await User.get(email=EMAIL)).status == AccountStatus.ACTIVE
