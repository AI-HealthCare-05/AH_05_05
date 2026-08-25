import logging
import secrets

from app.core.exceptions import (
    InvalidUserCredentialsError,
    UserSuspendedError,
    UserWithdrawnError,
)
from app.core.jwt.tokens import RefreshToken
from app.core.utils.security import hash_password, verify_password
from app.dtos.user_auth import RecordStatus, UserLoginRequest, UserLoginResponse
from app.models.care import CareEpisode
from app.models.enums import AccountStatus
from app.models.users import User
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# 존재하지 않는 이메일에도 해시 검증을 수행해 응답 시간을 맞춘다.
# 곧바로 실패를 돌려주면 bcrypt 비용만큼 빨라져 "가입된 이메일인지" 가 시간으로 드러난다.
# 모듈 로드 시 한 번만 만든다.
_TIMING_EQUALIZER_HASH = hash_password(secrets.token_urlsafe(32))


class UserAuthService:
    """사용자 로그인. 관리자 인증(AdminAuthService)과는 응답 규격이 다르다."""

    def __init__(self) -> None:
        self.user_repo = UserRepository()

    async def login(self, request: UserLoginRequest) -> tuple[UserLoginResponse, RefreshToken]:
        user = await self._authenticate(str(request.email), request.password)

        refresh_token = RefreshToken.for_user(user)
        access_token = refresh_token.access_token

        status_code, latest_record_id = await self.resolve_record_status(user.id)

        logger.info("user login: id=%s record_status=%s", user.id, status_code)
        response = UserLoginResponse(
            access_token=str(access_token),
            status_code=status_code,
            latest_record_id=latest_record_id,
        )
        return response, refresh_token

    async def _authenticate(self, email: str, password: str) -> User:
        user = await self.user_repo.get_user_by_email(email)

        # 사용자가 없어도 검증을 건너뛰지 않는다. 위 상수 주석 참고.
        stored_hash = user.hashed_password if user else _TIMING_EQUALIZER_HASH
        password_matched = verify_password(password, stored_hash)

        # 계정 없음과 비밀번호 오류를 같은 예외로 묶는다. 응답이 달라지면 이메일이 노출된다.
        if user is None or not password_matched:
            raise InvalidUserCredentialsError()

        self._ensure_usable(user)
        return user

    @staticmethod
    async def resolve_record_status(user_id: int) -> tuple[RecordStatus, int | None]:
        """**진료기록 유무**로 status_code 를 정한다. 계정 상태와는 무관하다.

        이름이 statusCode 라 계정 상태(ACTIVE/SUSPENDED)로 오해하기 쉽다.
        프론트는 이 값으로 "기록 등록 화면" 과 "홈" 을 가른다.

            기록 1건 이상 -> (ACTIVE,  최신 기록 id)
            기록 0건      -> (PENDING, None)

        두 값은 항상 짝이 맞는다. ACTIVE 인데 id 가 None 일 수 없다.
        """
        # only("id") 를 붙이면 Tortoise 가 SELECT 목록이 빈 SQL 을 만들어 문법 오류가 난다.
        # 한 행만 읽으므로 컬럼을 다 가져와도 부담이 없다.
        latest = (
            await CareEpisode.filter(user_id=user_id)
            # created_at 이 같은 초에 몰릴 수 있어 id 로 한 번 더 가른다.
            .order_by("-created_at", "-id")
            .first()
        )
        if latest is None:
            return RecordStatus.PENDING, None
        return RecordStatus.ACTIVE, latest.id

    @staticmethod
    def _ensure_usable(user: User) -> None:
        """정지·탈퇴 계정을 막는다. 상태 코드는 관리자 로그인과 같은 403 이다."""
        if user.status == AccountStatus.SUSPENDED:
            raise UserSuspendedError()
        if user.status == AccountStatus.WITHDRAWN:
            raise UserWithdrawnError()
