import logging
from datetime import datetime

from fastapi import HTTPException

from app.core import config
from app.core.exceptions import (
    AccountSuspendedError,
    AccountWithdrawnError,
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidTokenError,
    SamePasswordError,
)
from app.core.jwt.tokens import AccessToken, JwtScope, RefreshToken
from app.core.utils.security import hash_password, verify_password
from app.dtos.admin_auth import (
    AdminInfo,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPasswordChangeRequest,
    AdminPasswordChangeResponse,
    AdminTokenRefreshResponse,
)
from app.models.admins import Admin
from app.models.enums import AccountStatus
from app.services.jwt import JwtService

logger = logging.getLogger(__name__)


class AdminAuthService:
    """REQ-ADMIN-001 / REQ-ADMIN-002 관리자 인증."""

    def __init__(self) -> None:
        self.jwt_service = JwtService()

    async def login(self, request: AdminLoginRequest) -> tuple[AdminLoginResponse, RefreshToken]:
        admin = await Admin.get_or_none(email=str(request.email))

        # 계정이 없을 때와 비밀번호가 틀렸을 때를 구분하면 이메일 존재 여부가 새어나간다.
        # 두 경우 모두 같은 예외로 응답한다.
        if admin is None or not verify_password(request.password, admin.hashed_password):
            raise InvalidCredentialsError()

        self._ensure_usable(admin)

        refresh_token = RefreshToken.for_admin(admin.id)
        access_token = refresh_token.access_token

        # 전환보다 **먼저** 읽어야 한다. 아래에서 ACTIVE 로 바꾼 뒤에 보면 항상 false 가 된다.
        is_first_login = admin.status == AccountStatus.PENDING

        # PENDING -> ACTIVE 는 여기서 일어난다. 예전에는 change_password 가 했으나,
        # 비밀번호 변경이 선택제가 되면서 "안 바꾸면 영영 PENDING" 이 되어버려 옮겼다.
        # 정지에서 해제된 계정도 PENDING 으로 돌아오므로 같은 경로로 되살아난다.
        if is_first_login:
            admin.status = AccountStatus.ACTIVE
            # approved_at 은 "현재 활성 상태가 된 시각"이다. 재설정으로 PENDING 이 되면
            # reset_password 가 None 으로 지우고, 다시 로그인할 때 여기서 새로 찍힌다.
            admin.approved_at = datetime.now(tz=config.TIMEZONE)
            await admin.save(update_fields=["status", "approved_at"])

        logger.info("admin login: id=%s first_login=%s", admin.id, is_first_login)
        response = AdminLoginResponse(
            access_token=str(access_token),
            admin=AdminInfo(admin_id=admin.id, name=admin.name, email=admin.email, role=admin.role),
            is_first_login=is_first_login,
        )
        return response, refresh_token

    async def refresh(self, refresh_token: str | None) -> AdminTokenRefreshResponse:
        if not refresh_token:
            raise InvalidTokenError()

        try:
            verified = self.jwt_service.verify_jwt(token=refresh_token, token_type="refresh")
        except HTTPException as err:
            raise InvalidTokenError() from err

        admin_id = self._read_admin_id(verified)

        # 로그인 이후 정지된 계정이 갱신만으로 접근을 이어가면 안 된다. 매번 상태를 다시 확인한다.
        admin = await Admin.get_or_none(id=admin_id)
        if admin is None:
            raise InvalidTokenError()
        self._ensure_usable(admin)

        # access_token 은 리프레시의 클레임을 복사하므로 scope 도 함께 넘어간다.
        access_token: AccessToken = verified.access_token
        return AdminTokenRefreshResponse(access_token=str(access_token))

    async def change_password(self, admin_id: int, request: AdminPasswordChangeRequest) -> AdminPasswordChangeResponse:
        """REQ-ADMIN-009 본인 비밀번호 변경."""
        admin = await Admin.get_or_none(id=admin_id)
        if admin is None:
            raise InvalidTokenError()

        if not verify_password(request.current_password, admin.hashed_password):
            raise InvalidPasswordError()
        if verify_password(request.new_password, admin.hashed_password):
            raise SamePasswordError()

        admin.hashed_password = hash_password(request.new_password)
        # 다른 기기에 남은 리프레시 토큰은 끊지 못한다. 발급된 JWT 를 개별 폐기할 수단이
        # 없어서이며, 노출 창은 리프레시 수명(REFRESH_TOKEN_EXPIRE_MINUTES)으로 제한한다.

        # **상태는 건드리지 않는다.** 예전에는 여기서 PENDING -> ACTIVE 로 올렸으나,
        # 비밀번호 변경이 선택제가 되면서 전환 트리거를 첫 로그인(login)으로 옮겼다.
        # 여기까지 왔다는 것은 이미 로그인했다는 뜻이라 상태는 ACTIVE 여야 정상이다.

        await admin.save()

        logger.info("admin password changed: id=%s status=%s", admin.id, admin.status)
        return AdminPasswordChangeResponse(message="비밀번호가 변경되었습니다.", status=admin.status)

    @staticmethod
    def _read_admin_id(token: AccessToken | RefreshToken) -> int:
        if token.payload.get("scope") != JwtScope.ADMIN:
            # 사용자 토큰이거나 scope 가 없는 구버전 토큰이다.
            raise InvalidTokenError()

        subject = token.payload.get("sub")
        if subject is None:
            raise InvalidTokenError()
        return int(subject)

    @staticmethod
    def _ensure_usable(admin: Admin) -> None:
        if admin.status == AccountStatus.SUSPENDED:
            raise AccountSuspendedError()
        if admin.status == AccountStatus.WITHDRAWN:
            raise AccountWithdrawnError()
