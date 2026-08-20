from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.models.admins import Admin
from app.models.enums import AccountStatus, AdminRole
from app.services.jwt import JwtService

# auto_error=False 로 두어 인증 실패도 공통 규격({"code", "message"})으로 응답한다.
# 기본값(True)이면 FastAPI가 {"detail": "Not authenticated"} 를 반환해 규격이 어긋난다.
admin_security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedAdmin:
    """요청을 보낸 관리자. ORM 모델과 분리해 라우터·서비스가 DB 구현에 묶이지 않게 한다."""

    admin_id: int
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

    admin_id = verified.payload.get("user_id")
    if admin_id is None:
        raise UnauthorizedError("유효하지 않은 토큰입니다.")

    # user 와 admin 은 별도 테이블이고 토큰 페이로드에 구분자가 없다.
    # 따라서 admin 테이블에 실제로 존재하는지가 사용자 토큰을 걸러내는 유일한 방어선이다.
    # 페이로드에 scope("admin"|"user") 클레임을 넣으면 DB 조회 전에 걸러낼 수 있다(회의 안건 B-3).
    admin = await Admin.get_or_none(id=int(admin_id))
    if admin is None:
        raise ForbiddenError("관리자 계정이 아닙니다.")
    if admin.status != AccountStatus.ACTIVE:
        # 정지된 계정과 임시 비밀번호 미변경(PENDING) 계정을 모두 막는다.
        raise ForbiddenError("사용할 수 없는 관리자 계정입니다.")

    return AuthenticatedAdmin(admin_id=admin.id, role=admin.role)


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


# 조회 계열 — ADMIN·STAFF 모두 허용
require_admin_or_staff = require_roles(AdminRole.ADMIN, AdminRole.STAFF)

# 계정 생성·권한 변경 계열 — ADMIN 전용 (권한 매트릭스)
require_admin = require_roles(AdminRole.ADMIN)
