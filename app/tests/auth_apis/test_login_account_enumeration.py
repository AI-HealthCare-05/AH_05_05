from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.enums import AccountStatus
from app.models.users import User

PASSWORD = "Password123!"


def signup_data(email: str, **overrides):
    data = {
        "email": email,
        "password": PASSWORD,
        "name": "열거테스터",
        "phone_number": "01055556666",
        "birth_date": "1990-01-01",
        "gender": "FEMALE",
        "is_terms_agreed": True,
    }
    data.update(overrides)
    return data


class TestLoginDoesNotRevealAccountState(TestCase):
    """로그인 실패 응답으로 계정의 존재·상태가 드러나면 안 된다(#196).

    사유가 구분되면 이메일 목록을 넣어보는 것만으로 가입자를 골라낼 수 있다.
    """

    async def _login(self, client: AsyncClient, email: str, password: str = PASSWORD):
        return await client.post("/api/v1/auth/login", json={"email": email, "password": password})

    async def test_all_failure_cases_return_an_identical_response(self):
        """이 테스트가 이 작업의 핵심이다.

        문구만 같고 상태 코드나 code 가 다르면 통일한 의미가 없다.
        응답 전체를 비교한다.
        """
        suspended = "suspended@example.com"
        withdrawn = "withdrawn@example.com"
        active = "active@example.com"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for email in (suspended, withdrawn, active):
                await client.post("/api/v1/auth/signup", json=signup_data(email))
            await User.filter(email=suspended).update(status=AccountStatus.SUSPENDED)
            await User.filter(email=withdrawn).update(status=AccountStatus.WITHDRAWN)

            responses = {
                "없는 계정": await self._login(client, "nobody@example.com"),
                "비밀번호 불일치": await self._login(client, active, "WrongPassword123!"),
                "정지 계정": await self._login(client, suspended),
                "탈퇴 계정": await self._login(client, withdrawn),
            }

        for label, response in responses.items():
            assert response.status_code == status.HTTP_400_BAD_REQUEST, label
            assert response.json() == {
                "code": "INVALID_CREDENTIALS",
                "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
            }, label

        # 상태 코드·본문이 모두 같아야 한다. 하나라도 갈리면 구분이 가능해진다.
        assert len({r.status_code for r in responses.values()}) == 1
        assert len({r.text for r in responses.values()}) == 1

    async def test_pending_account_is_also_indistinguishable(self):
        # 대기 계정도 같은 응답이어야 한다. 예전에는 423 으로 함께 갈라졌다.
        email = "pending@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data(email))
            await User.filter(email=email).update(status=AccountStatus.PENDING)

            response = await self._login(client, email)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["code"] == "INVALID_CREDENTIALS"

    async def test_active_account_still_logs_in(self):
        email = "normal@example.com"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data(email))

            response = await self._login(client, email)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["access_token"]

    async def test_signup_message_does_not_reveal_account_state(self):
        """회원가입은 「쓸 수 없다」를 알려야 기능이 성립해 409 자체는 남는다.

        문구에서 「왜」만 감춘다. 활성 계정과 탈퇴 계정이 같은 문구를 받아야 한다.
        """
        active = "dup-active@example.com"
        withdrawn = "dup-withdrawn@example.com"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for email in (active, withdrawn):
                await client.post("/api/v1/auth/signup", json=signup_data(email))
            await User.filter(email=withdrawn).update(status=AccountStatus.WITHDRAWN)

            again_active = await client.post("/api/v1/auth/signup", json=signup_data(active))
            again_withdrawn = await client.post("/api/v1/auth/signup", json=signup_data(withdrawn))

        for response in (again_active, again_withdrawn):
            assert response.status_code == status.HTTP_409_CONFLICT
            assert response.json() == {
                "code": "EMAIL_ALREADY_EXISTS",
                "message": "사용할 수 없는 이메일입니다.",
                "field": "email",
            }
        assert again_active.text == again_withdrawn.text
