from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.jwt.tokens import JwtScope
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


async def _authenticate(
    credential: HTTPAuthorizationCredentials | None,
    allowed_statuses: frozenset[AccountStatus],
) -> AuthenticatedAdmin:
    """토큰을 검증하고 계정 상태가 허용 목록에 있는지 확인한다.

    이 함수는 직접 의존성으로 쓰지 않는다. 허용 상태를 명시한 아래 두 함수를 쓴다.
    """
    if credential is None:
        raise UnauthorizedError()

    try:
        # JwtService 는 만료·위변조를 HTTPException(401/400) 으로 던진다.
        # 공통 규격({"code", "message"})으로 맞추기 위해 여기서 변환한다.
        verified = JwtService().verify_jwt(token=credential.credentials, token_type="access")
    except HTTPException as err:
        raise UnauthorizedError("유효하지 않거나 만료된 토큰입니다.") from err

    # user 와 admin 은 별도 테이블이라 id 가 겹칠 수 있다.
    # scope 가 없는 구버전 토큰과 사용자 토큰을 여기서 먼저 걸러낸다.
    if verified.payload.get("scope") != JwtScope.ADMIN:
        raise ForbiddenError("관리자 토큰이 아닙니다.")

    admin_id = verified.payload.get("sub")
    if admin_id is None:
        raise UnauthorizedError("유효하지 않은 토큰입니다.")

    admin = await Admin.get_or_none(id=int(admin_id))
    if admin is None:
        raise ForbiddenError("관리자 계정이 아닙니다.")
    if admin.status not in allowed_statuses:
        raise ForbiddenError("사용할 수 없는 관리자 계정입니다.")

    return AuthenticatedAdmin(admin_id=admin.id, role=admin.role)


async def get_current_admin(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_security)],
) -> AuthenticatedAdmin:
    """관리자 API 의 기본 인증. ACTIVE 계정만 허용한다.

    정지(SUSPENDED)·탈퇴(WITHDRAWN)뿐 아니라 임시 비밀번호를 아직 바꾸지 않은
    PENDING 계정도 막는다. PENDING 계정은 비밀번호를 변경해야 서비스를 쓸 수 있다.
    """
    return await _authenticate(credential, frozenset({AccountStatus.ACTIVE}))


async def get_current_admin_allow_pending(
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_security)],
) -> AuthenticatedAdmin:
    """비밀번호 변경 API 전용. ACTIVE 와 PENDING 을 허용한다.

    PENDING 계정이 임시 비밀번호를 바꿀 유일한 경로라 예외적으로 열어둔다.
    get_current_admin 에 옵션을 붙이지 않고 함수를 나눈 이유는, 어느 API 가
    PENDING 을 허용하는지 호출부에서 바로 보이게 하기 위해서다.

    SUSPENDED·WITHDRAWN 은 여기서도 막는다. 정지된 계정이 비밀번호 변경으로
    되살아나면 안 된다.
    """
    return await _authenticate(credential, frozenset({AccountStatus.ACTIVE, AccountStatus.PENDING}))


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
