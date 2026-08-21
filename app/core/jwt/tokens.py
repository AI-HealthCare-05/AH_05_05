from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self
from uuid import uuid4

from app.core import config
from app.core.jwt.exceptions import ExpiredTokenError, TokenBackendError, TokenBackendExpiredError, TokenError
from app.core.jwt.state import token_backend
from app.models.users import User

if TYPE_CHECKING:
    from app.core.jwt.backends import TokenBackend


class JwtScope(StrEnum):
    """토큰이 어느 계정 종류에 발급됐는지 나타낸다.

    user 와 admin 은 별도 테이블이라 id 만으로는 구분할 수 없다.
    사용자 토큰에 USER 를 넣는 작업은 사용자 인증 담당 몫이며 규칙만 공유한다.
    """

    ADMIN = "admin"
    USER = "user"


class Token:
    token_type: str | None = None
    lifetime: timedelta | None = None
    _token_backend: "TokenBackend" = token_backend

    def __init__(self, token: str | None = None, verify: bool = True) -> None:
        if not self.token_type:
            raise TokenError("token_type must be set")
        if not self.lifetime:
            raise TokenError("lifetime must be set")

        self.token = token
        self.current_time = datetime.now(tz=config.TIMEZONE)
        self.payload: dict[str, Any] = {}

        if token is not None:
            try:
                self.payload = token_backend.decode(token, verify=verify)
            except TokenBackendExpiredError as err:
                raise ExpiredTokenError("Token is expired") from err
            except TokenBackendError as err:
                raise TokenError("Token is invalid") from err
        else:
            self.payload = {"type": self.token_type}
            self.set_exp(from_time=self.current_time, lifetime=self.lifetime)
            self.set_jti()

    def __repr__(self) -> str:
        return repr(self.payload)

    def __getitem__(self, key: str):
        return self.payload[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.payload[key] = value

    def __delitem__(self, key: str) -> None:
        del self.payload[key]

    def __contains__(self, key: str) -> Any:
        return key in self.payload

    def __str__(self) -> str:
        """
        Signs and returns a token as a base64 encoded string.
        """
        return self._token_backend.encode(self.payload)

    def set_exp(self, from_time: datetime | None = None, lifetime: timedelta | None = None) -> None:
        if from_time is None:
            from_time = self.current_time

        if lifetime is None:
            lifetime = self.lifetime

        assert lifetime is not None

        dt = from_time + lifetime
        # timegm(dt.timetuple()) 은 timetuple 을 UTC 로 해석한다. current_time 이 KST
        # aware 라 벽시계 그대로 넘어가 exp 가 9시간 뒤로 밀렸다(30분 토큰이 9시간 30분).
        # timestamp() 는 tzinfo 를 반영하므로 aware/naive 어느 쪽이든 올바른 epoch 을 준다.
        self.payload["exp"] = int(dt.timestamp())

    def set_jti(self) -> None:
        self.payload["jti"] = uuid4().hex

    @classmethod
    def for_user(cls, user: User) -> Self:
        token = cls()
        token["user_id"] = user.id
        return token

    @classmethod
    def for_admin(cls, admin_id: int) -> Self:
        """관리자 토큰을 만든다.

        user 와 admin 은 별도 테이블이라 id 가 겹칠 수 있다. scope 가 없으면
        사용자 토큰으로 관리자 API 를 호출할 수 있으므로 반드시 함께 넣는다.

        발급한 토큰을 만료 전에 개별 폐기할 수단은 없다. 정지된 계정은 갱신 시점의
        DB 상태 확인으로 막고, 그 외의 노출 위험은 리프레시 수명을 짧게 두어 줄인다.
        """
        token = cls()
        # JWT 표준상 sub 는 문자열이어야 한다. 정수로 넣으면 PyJWT 가 검증 단계에서 거부한다.
        token["sub"] = str(admin_id)
        token["scope"] = JwtScope.ADMIN
        return token


class AccessToken(Token):
    token_type = "access"
    lifetime = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)


class RefreshToken(Token):
    token_type = "refresh"
    # config 값이 분 단위이므로 minutes 로 넘긴다.
    # days 로 넘기면 20160일(약 55년)짜리 토큰이 발급된다.
    lifetime = timedelta(minutes=config.REFRESH_TOKEN_EXPIRE_MINUTES)
    no_copy_claims = ("type", "exp", "jti")

    @property
    def access_token(self) -> AccessToken:
        access = AccessToken()
        access.set_exp(from_time=self.current_time)

        no_copy = self.no_copy_claims
        for claim, value in self.payload.items():
            if claim in no_copy:
                continue
            access[claim] = value

        return access
