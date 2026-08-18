from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.admin import AdminRole
from app.services.jwt import JwtService

# auto_error=False 로 두어 인증 실패도 공통 규격({"code", "message"})으로 응답한다.
# 기본값(True)이면 FastAPI가 {"detail": "Not authenticated"} 를 반환해 규격이 어긋난다.
admin_security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedAdmin:
    """요청을 보낸 관리자. ORM 모델과 분리해 라우터·서비스가 DB 구현에 묶이지 않게 한다."""

    admin_id: int
    account_id: int
    role: AdminRole


async def get_current_admin(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_security)],
) -> AuthenticatedAdmin:
    if credential is None:
        raise UnauthorizedError()

    try:
        # JwtService 는 만료·위변조를 HTTPException(401/400) 으로 던진다.
        # 공통 규격({"code", "message"})으로 맞추기 위해 여기서 변환한다.
        verified = JwtService().verify_jwt(token=credential.credentials, token_type="access")
    except HTTPException as err:
        raise UnauthorizedError("유효하지 않거나 만료된 토큰입니다.") from err

    account_id = verified.payload.get("user_id")
    if account_id is None:
        raise UnauthorizedError("유효하지 않은 토큰입니다.")

    # TODO(#10): accounts·admin 조회로 교체한다. 마이그레이션 완료 후 작업.
    #   - account_type 이 ADMIN 인지 확인 (아니면 ForbiddenError)
    #   - status 가 ACTIVE 인지 확인 (SUSPENDED 면 ForbiddenError)
    #   - admin.role 을 읽어 AuthenticatedAdmin 에 담는다
    # 현재는 토큰 검증까지만 실제로 동작하고 역할은 고정값이다.
    return AuthenticatedAdmin(admin_id=int(account_id), account_id=int(account_id), role=AdminRole.ADMIN)


def require_roles(
    *allowed: AdminRole,
) -> Callable[[AuthenticatedAdmin], Coroutine[Any, Any, AuthenticatedAdmin]]:
    """지정한 역할만 통과시키는 의존성을 만든다.

    조회 API는 ADMIN·STAFF 모두 허용하고, 등록·권한변경은 ADMIN 전용이다(권한 매트릭스).
    """

    async def dependency(
        admin: Annotated[AuthenticatedAdmin, Depends(get_current_admin)],
    ) -> AuthenticatedAdmin:
        if admin.role not in allowed:
            raise ForbiddenError()
        return admin

    return dependency


# 조회 계열 공통 — ADMIN·STAFF 모두 허용
require_admin_or_staff = require_roles(AdminRole.ADMIN, AdminRole.STAFF)
