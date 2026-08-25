from datetime import UTC, datetime, timedelta
from itertools import count as counter
from typing import Any

from httpx import ASGITransport, AsyncClient, Response
from starlette import status
from tortoise.contrib.test import TestCase

from app.apis.v1.accounts_routers import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from app.core import config
from app.core.jwt.state import token_backend
from app.core.jwt.tokens import AccessToken, JwtScope
from app.core.utils.security import hash_password

# 반드시 모듈 최상단에서 import 한다. app.main 이 Tortoise.init_models() 를 돌리는데,
# 그게 먼저 실행되지 않으면 tortoise.contrib.test.TestCase 의 트랜잭션 teardown 이
# 실패하면서 세션이 멈춘다(에러도 안 나오고 그대로 hang). 함수 안에서 늦게 import 하면 늦다.
from app.main import app
from app.models.care import CareEpisode
from app.models.enums import AccountStatus
from app.models.users import User

LOGIN_URL = "/api/v1/accounts/login"
ADMIN_USERS_URL = "/api/v1/admin/users"
PASSWORD = "Password123!"

_sequence = counter(1)


async def request(method: str, url: str, **kwargs: Any) -> Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, url, **kwargs)


async def create_user(
    *, email: str | None = None, user_status: AccountStatus = AccountStatus.ACTIVE, episodes: int = 0
) -> tuple[User, list[CareEpisode]]:
    user = await User.create(
        email=email or f"u{next(_sequence)}@example.com",
        hashed_password=hash_password(PASSWORD),
        name="회원",
        status=user_status,
    )
    created = [await CareEpisode.create(user=user, title=f"케어{index}") for index in range(episodes)]
    return user, created


async def login(email: str, password: str = PASSWORD) -> Response:
    return await request("POST", LOGIN_URL, json={"email": email, "password": password})


class TestLoginSuccess(TestCase):
    async def test_returns_active_with_latest_record_id(self) -> None:
        user, episodes = await create_user(episodes=1)

        response = await login(user.email)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert set(body) == {"accessToken", "statusCode", "latestRecordId"}
        assert body["statusCode"] == "active"
        assert body["latestRecordId"] == episodes[0].id

    async def test_returns_pending_when_no_record(self) -> None:
        user, _ = await create_user(episodes=0)

        body = (await login(user.email)).json()

        assert body["statusCode"] == "pending"
        assert body["latestRecordId"] is None

    async def test_picks_the_most_recent_record(self) -> None:
        user, episodes = await create_user(episodes=3)

        body = (await login(user.email)).json()

        assert body["latestRecordId"] == episodes[-1].id
        assert body["latestRecordId"] == max(episode.id for episode in episodes)

    async def test_active_never_comes_with_null_record_id(self) -> None:
        """두 필드는 항상 짝이 맞아야 한다. 화면이 이 조합으로 분기한다."""
        for episodes in (0, 1, 2):
            user, _ = await create_user(episodes=episodes)
            body = (await login(user.email)).json()

            if body["statusCode"] == "active":
                assert body["latestRecordId"] is not None
            else:
                assert body["latestRecordId"] is None

    async def test_other_users_records_are_not_counted(self) -> None:
        await create_user(episodes=5)
        user, _ = await create_user(episodes=0)

        body = (await login(user.email)).json()

        assert body["statusCode"] == "pending"
        assert body["latestRecordId"] is None

    async def test_never_returns_password(self) -> None:
        user, _ = await create_user()

        response = await login(user.email)

        assert PASSWORD not in response.text
        assert not any("password" in key.lower() for key in response.json())


class TestLoginFailure(TestCase):
    async def test_unknown_email_and_wrong_password_are_identical(self) -> None:
        """이메일 존재 여부가 새어나가지 않도록 응답이 완전히 같아야 한다."""
        user, _ = await create_user()

        unknown = await login("nobody@example.com")
        wrong = await login(user.email, "WrongPassword1!")

        assert unknown.status_code == wrong.status_code == status.HTTP_400_BAD_REQUEST
        assert unknown.json() == wrong.json()
        assert unknown.json() == {"detail": "이메일 또는 비밀번호가 일치하지 않습니다."}
        # 헤더도 같아야 한다. date 는 초 단위로 달라질 수 있어 제외한다.
        ignored = {"date", "content-length"}
        assert {k: v for k, v in unknown.headers.items() if k not in ignored} == {
            k: v for k, v in wrong.headers.items() if k not in ignored
        }

    async def test_failure_does_not_set_refresh_cookie(self) -> None:
        response = await login("nobody@example.com")

        assert REFRESH_COOKIE_NAME not in response.cookies

    async def test_suspended_account_is_forbidden(self) -> None:
        user, _ = await create_user(user_status=AccountStatus.SUSPENDED)

        response = await login(user.email)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "정지된 계정입니다."}

    async def test_withdrawn_account_is_forbidden(self) -> None:
        user, _ = await create_user(user_status=AccountStatus.WITHDRAWN)

        response = await login(user.email)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "사용할 수 없는 계정입니다."}

    async def test_missing_fields_return_422(self) -> None:
        """명세서는 400 empty_fields 를 요구하나 Pydantic 이 먼저 422 로 막는다(미정 2)."""
        for payload in ({}, {"email": "a@b.com"}, {"password": PASSWORD}, {"email": "a@b.com", "password": ""}):
            response = await request("POST", LOGIN_URL, json=payload)
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, payload

    async def test_malformed_email_returns_422(self) -> None:
        response = await request("POST", LOGIN_URL, json={"email": "not-an-email", "password": PASSWORD})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestIssuedToken(TestCase):
    async def test_payload_carries_user_scope_and_string_sub(self) -> None:
        user, _ = await create_user()

        token = AccessToken(token=(await login(user.email)).json()["accessToken"])

        assert token.payload["scope"] == JwtScope.USER
        assert token.payload["sub"] == str(user.id)
        assert isinstance(token.payload["sub"], str)

    async def test_keeps_legacy_user_id_claim(self) -> None:
        """dependencies/security.py 가 user_id 를 읽는다. 빼면 기존 사용자 API 가 깨진다."""
        user, _ = await create_user()

        token = AccessToken(token=(await login(user.email)).json()["accessToken"])

        assert token.payload["user_id"] == user.id

    async def test_access_token_expires_in_thirty_minutes(self) -> None:
        """timegm(timetuple()) 을 쓰면 KST 를 UTC 로 오해해 9시간 밀린다."""
        user, _ = await create_user()
        issued_at = datetime.now(tz=UTC)

        payload = token_backend.decode((await login(user.email)).json()["accessToken"], verify=True)
        expiry = datetime.fromtimestamp(payload["exp"], tz=UTC)

        expected = issued_at + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
        assert abs(expiry - expected) < timedelta(seconds=60)

    async def test_user_token_cannot_call_admin_api(self) -> None:
        """scope 클레임이 실제로 관리자 API 를 막는지 확인한다."""
        user, _ = await create_user()
        access_token = (await login(user.email)).json()["accessToken"]

        response = await request("GET", ADMIN_USERS_URL, headers={"Authorization": f"Bearer {access_token}"})

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestRefreshCookie(TestCase):
    async def test_sets_http_only_cookie_on_its_own_path(self) -> None:
        user, _ = await create_user()

        response = await login(user.email)

        assert REFRESH_COOKIE_NAME in response.cookies
        set_cookie = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert f"Path={REFRESH_COOKIE_PATH}" in set_cookie
        assert f"Max-Age={config.REFRESH_TOKEN_EXPIRE_MINUTES * 60}" in set_cookie

    async def test_refresh_token_is_not_in_body(self) -> None:
        user, _ = await create_user()

        assert "refreshToken" not in (await login(user.email)).json()

    async def test_cookie_name_differs_from_admin(self) -> None:
        """같은 브라우저에서 관리자·사용자가 동시에 로그인될 수 있다."""
        from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_NAME as ADMIN_COOKIE
        from app.apis.v1.admin_auth_routers import REFRESH_COOKIE_PATH as ADMIN_PATH

        assert REFRESH_COOKIE_NAME != ADMIN_COOKIE
        assert not REFRESH_COOKIE_PATH.startswith(ADMIN_PATH)
        assert not ADMIN_PATH.startswith(REFRESH_COOKIE_PATH)
