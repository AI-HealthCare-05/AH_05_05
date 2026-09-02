import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core.validators.user_validators import mask_name
from app.main import app
from app.models.users import User

PASSWORD = "Password123!"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("김훈", "김*"),
        ("김동훈", "김*훈"),
        ("남궁동훈", "남**훈"),
        ("황보동훈이", "황***이"),
        ("KimJinhyeong", "K***g"),
        ("", "익명"),
        ("ABCDEFGHIJKLMNOPQRST", "A***T"),
    ],
)
def test_mask_name_hides_middle_with_at_most_three_stars(raw: str, expected: str):
    assert mask_name(raw) == expected


def signup_data(email: str, **overrides):
    data = {
        "email": email,
        "password": PASSWORD,
        "name": "김진형",
        "phone_number": "01055556666",
        "birth_date": "1990-01-01",
        "gender": "FEMALE",
        "is_terms_agreed": True,
    }
    data.update(overrides)
    return data


class TestSignupNameRules(TestCase):
    """이름은 언어와 무관하게 문자만 받고 숫자·공백·기호는 거부한다."""

    async def test_accepts_names_written_with_unicode_letters(self):
        allowed = ("김진형", "KimJinhyeong", "Élodie", "山田", "Мария", "김É山")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for index, name in enumerate(allowed):
                response = await client.post(
                    "/api/v1/auth/signup", json=signup_data(f"ok{index}@example.com", name=name)
                )

                assert response.status_code == status.HTTP_201_CREATED, name

    async def test_rejects_disallowed_characters(self):
        rejected = (
            "김 진형",  # 공백
            "김진형2",  # 숫자
            "김철수😀",  # 이모지
            "Kim-Jinhyeong",  # 하이픈
            "김진형!",  # 특수문자
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for index, name in enumerate(rejected):
                response = await client.post(
                    "/api/v1/auth/signup", json=signup_data(f"no{index}@example.com", name=name)
                )

                assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, name
                assert response.json()["field"] == "name", name

    async def test_rejects_surrounding_whitespace(self):
        email = "space@example.com"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data(email, name="  김진형  "))

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert response.json()["field"] == "name"

    async def test_normalizes_name_to_unicode_nfc(self):
        email = "normalized@example.com"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/signup", json=signup_data(email, name="E\u0301lodie"))

        assert response.status_code == status.HTTP_201_CREATED
        assert (await User.get(email=email)).name == "Élodie"


class TestProfileUpdateNameRules(TestCase):
    """마이페이지 「기본정보 수정」도 같은 검사를 탄다."""

    EMAIL = "profile-name@example.com"

    async def _signed_in(self, client: AsyncClient) -> dict[str, str]:
        await client.post("/api/v1/auth/signup", json=signup_data(self.EMAIL))
        login = await client.post("/api/v1/auth/login", json={"email": self.EMAIL, "password": PASSWORD})
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def test_rejects_disallowed_name(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch("/api/v1/users/me", headers=headers, json={"name": "김 진형"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert (await User.get(email=self.EMAIL)).name == "김진형"

    async def test_accepts_allowed_name(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch("/api/v1/users/me", headers=headers, json={"name": "山田Élodie"})

        assert response.status_code == status.HTTP_200_OK
        assert (await User.get(email=self.EMAIL)).name == "山田Élodie"

    async def test_other_fields_can_be_updated_without_sending_name(self):
        """**이 테스트가 이번 작업의 핵심 회귀 방지다.**

        name 은 선택 필드다. optional_after_validator 가 아니라 그냥 AfterValidator 를 붙이면
        「이름을 안 보낸」 요청이 None 을 검사하다 죽는다. 그러면 이름을 건드리지 않고
        전화번호만 바꾸려는 사용자가 저장 자체를 못 하게 된다.
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await self._signed_in(client)

            response = await client.patch("/api/v1/users/me", headers=headers, json={"phoneNumber": "01099998888"})

        assert response.status_code == status.HTTP_200_OK
        user = await User.get(email=self.EMAIL)
        assert user.name == "김진형"  # 이름은 그대로다
