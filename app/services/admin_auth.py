import logging

from fastapi import HTTPException

from app.core.exceptions import (
    AccountSuspendedError,
    AccountWithdrawnError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.jwt.tokens import AccessToken, JwtScope, RefreshToken
from app.core.utils.security import verify_password
from app.dtos.admin_auth import AdminInfo, AdminLoginRequest, AdminLoginResponse, AdminTokenRefreshResponse
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

        logger.info("admin login: id=%s", admin.id)
        response = AdminLoginResponse(
            access_token=str(access_token),
            admin=AdminInfo(admin_id=admin.id, name=admin.name, email=admin.email, role=admin.role),
            # PENDING 은 로그인만 허용한다. 다른 관리자 API 는 get_current_admin 에서 막히므로
            # 비밀번호를 바꿔야 실제로 사용할 수 있다.
            must_change_password=admin.status == AccountStatus.PENDING,
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
