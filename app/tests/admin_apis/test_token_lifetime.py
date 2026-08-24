from datetime import UTC, datetime, timedelta
from unittest import TestCase

from app.core import config
from app.core.jwt.state import token_backend
from app.core.jwt.tokens import AccessToken, RefreshToken

# 설정값은 분 단위다. timedelta(days=...) 로 잘못 넘기면 값이 1440배로 부풀어
# 20160일(약 55년)짜리 리프레시 토큰이 나간 적이 있다. 아래 테스트는 그 재발을 막는다.
EXPECTED_ACCESS_MINUTES = 30
EXPECTED_REFRESH_MINUTES = 24 * 60

# 발급과 디코드 사이의 시간차를 흡수한다.
TOLERANCE = timedelta(seconds=60)


def decoded_expiry(token: object) -> datetime:
    """서명된 문자열을 실제로 디코드해 exp 를 읽는다.

    lifetime 속성을 그대로 비교하면 토큰에 실린 값과 어긋나도 알 수 없다.
    """
    payload = token_backend.decode(str(token), verify=True)
    return datetime.fromtimestamp(payload["exp"], tz=UTC)


class TestTokenLifetime(TestCase):
    def test_config_unit_is_minutes(self) -> None:
        """단위를 바꾸면 아래 만료 검증이 통째로 흔들리므로 여기서 못 박는다."""
        assert config.ACCESS_TOKEN_EXPIRE_MINUTES == EXPECTED_ACCESS_MINUTES
        assert config.REFRESH_TOKEN_EXPIRE_MINUTES == EXPECTED_REFRESH_MINUTES

    def test_refresh_token_expires_in_one_day(self) -> None:
        issued_at = datetime.now(tz=UTC)

        expiry = decoded_expiry(RefreshToken.for_admin(1))

        assert abs(expiry - (issued_at + timedelta(minutes=EXPECTED_REFRESH_MINUTES))) < TOLERANCE

    def test_access_token_expires_in_thirty_minutes(self) -> None:
        issued_at = datetime.now(tz=UTC)

        expiry = decoded_expiry(AccessToken.for_admin(1))

        assert abs(expiry - (issued_at + timedelta(minutes=EXPECTED_ACCESS_MINUTES))) < TOLERANCE

    def test_refresh_lifetime_is_not_absurdly_long(self) -> None:
        """분을 일로 잘못 넘기면 20160일이 된다. 상한을 둬서 그런 값이 나가지 못하게 한다."""
        expiry = decoded_expiry(RefreshToken.for_admin(1))

        assert expiry - datetime.now(tz=UTC) < timedelta(days=30)

    def test_refresh_outlives_access(self) -> None:
        access = decoded_expiry(AccessToken.for_admin(1))
        refresh = decoded_expiry(RefreshToken.for_admin(1))

        assert refresh > access

    def test_derived_access_token_does_not_inherit_refresh_expiry(self) -> None:
        """리프레시에서 파생한 액세스 토큰이 리프레시 수명을 물려받으면 안 된다.

        access_token 프로퍼티가 클레임을 복사하므로 exp 를 다시 설정하지 않으면
        30분짜리여야 할 토큰이 하루를 산다.
        """
        refresh = RefreshToken.for_admin(1)

        access_expiry = decoded_expiry(refresh.access_token)
        refresh_expiry = decoded_expiry(refresh)

        assert access_expiry < refresh_expiry
        assert abs(access_expiry - (datetime.now(tz=UTC) + timedelta(minutes=EXPECTED_ACCESS_MINUTES))) < TOLERANCE


class TestRefreshCookieMaxAge(TestCase):
    def test_cookie_max_age_matches_token_lifetime(self) -> None:
        """쿠키가 토큰보다 먼저 사라지면 갱신이 안 되고, 오래 남으면 죽은 쿠키를 계속 보낸다."""
        from app.apis.v1.admin_auth_routers import _set_refresh_cookie

        class FakeResponse:
            def __init__(self) -> None:
                self.kwargs: dict[str, object] = {}

            def set_cookie(self, **kwargs: object) -> None:
                self.kwargs = kwargs

        response = FakeResponse()
        _set_refresh_cookie(response, "token")  # type: ignore[arg-type]

        assert response.kwargs["max_age"] == EXPECTED_REFRESH_MINUTES * 60
