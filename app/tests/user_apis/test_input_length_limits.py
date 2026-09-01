from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.enums import AccountStatus
from app.models.users import User

# 정책이 생기기 전에 가입한 계정을 흉내낸다. 상한(32)보다 길다.
LEGACY_PASSWORD = "LegacyPassword1234567890!@#$%^&*()"
LIMIT_PASSWORD = "Aa1!" + "b" * 28  # 정확히 32자
OVER_PASSWORD = LIMIT_PASSWORD + "c"  # 33자


def signup_data(email: str, **overrides):
    data = {
        "email": email,
        "password": "Password123!",
        "name": "상한테스터",
        "phone_number": "01055556666",
        "birth_date": "1990-01-01",
        "gender": "FEMALE",
        "is_terms_agreed": True,
    }
    data.update(overrides)
    return data


class TestSignupInputLimits(TestCase):
    """입력 상한은 DB 컬럼 폭이 아니라 화면에서 받아야 할 길이 기준이다."""

    async def test_rejects_email_over_the_limit(self):
        over = "a" * 35 + "@example.com"  # 47자
        assert len(over) > 40

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data(over))

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["field"] == "email"

    async def test_accepts_email_at_the_limit(self):
        exact = "a" * 28 + "@example.com"  # 40자
        assert len(exact) == 40

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data(exact))

        assert response.status_code == status.HTTP_201_CREATED

    async def test_rejects_name_over_the_limit(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup", json=signup_data("name-over@example.com", name="가" * 21)
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["field"] == "name"

    async def test_accepts_name_at_the_limit(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup", json=signup_data("name-exact@example.com", name="가" * 20)
            )

        assert response.status_code == status.HTTP_201_CREATED

    async def test_rejects_password_over_the_limit(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup", json=signup_data("pw-over@example.com", password=OVER_PASSWORD)
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["field"] == "password"

    async def test_accepts_password_at_the_limit(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/signup", json=signup_data("pw-exact@example.com", password=LIMIT_PASSWORD)
            )

        assert response.status_code == status.HTTP_201_CREATED


class TestLegacyLongPasswordStillWorks(TestCase):
    """**이 클래스가 이 작업의 핵심 회귀 방지다.**

    상한은 「새로 정하는 비밀번호」에만 건다. 대조용으로 받는 칸에 걸면 이 정책이 생기기 전에
    더 긴 비밀번호로 가입한 계정이 로그인·탈퇴·비밀번호 변경 자체를 못 하게 된다.

    나중에 누가 「일관성 있게 다 막자」며 LoginRequest·WithdrawRequest·current_password 에
    상한을 붙이면 여기서 즉시 깨진다.
    """

    EMAIL = "legacy@example.com"

    async def _create_legacy_user(self, client: AsyncClient) -> None:
        """상한이 생기기 전 계정을 재현한다.

        회원가입 API 는 이제 33자를 거절하므로 그 경로로는 만들 수 없다.
        정상 가입 뒤 해시를 직접 갈아끼운다.
        """
        from app.core.utils.security import hash_password

        await client.post("/api/v1/auth/signup", json=signup_data(self.EMAIL))
        await User.filter(email=self.EMAIL).update(hashed_password=hash_password(LEGACY_PASSWORD))

    async def _token(self, client: AsyncClient) -> str:
        login = await client.post("/api/v1/auth/login", json={"email": self.EMAIL, "password": LEGACY_PASSWORD})
        return login.json()["access_token"]

    async def test_legacy_password_can_still_log_in(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await self._create_legacy_user(client)

            response = await client.post("/api/v1/auth/login", json={"email": self.EMAIL, "password": LEGACY_PASSWORD})

        assert response.status_code == status.HTTP_200_OK, "LoginRequest 에 상한을 붙이면 안 된다"

    async def test_legacy_password_can_still_change_password(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await self._create_legacy_user(client)
            headers = {"Authorization": f"Bearer {await self._token(client)}"}

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": LEGACY_PASSWORD, "newPassword": LIMIT_PASSWORD},
            )

        assert response.status_code == status.HTTP_200_OK, "current_password 에 상한을 붙이면 안 된다"

    async def test_legacy_password_can_still_withdraw(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await self._create_legacy_user(client)
            headers = {"Authorization": f"Bearer {await self._token(client)}"}

            response = await client.request(
                "DELETE", "/api/v1/users/me", headers=headers, json={"password": LEGACY_PASSWORD}
            )

        assert response.status_code == status.HTTP_204_NO_CONTENT, "WithdrawRequest 에 상한을 붙이면 안 된다"
        assert (await User.get(email=self.EMAIL)).status == AccountStatus.WITHDRAWN

    async def test_new_password_still_obeys_the_limit(self):
        # 대조용 칸은 열어두되, 「새로 정하는」 값에는 상한이 걸려야 한다.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await self._create_legacy_user(client)
            headers = {"Authorization": f"Bearer {await self._token(client)}"}

            response = await client.patch(
                "/api/v1/users/me/password",
                headers=headers,
                json={"currentPassword": LEGACY_PASSWORD, "newPassword": OVER_PASSWORD},
            )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["field"] == "newPassword"
