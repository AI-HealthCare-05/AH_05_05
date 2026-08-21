from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core import config
from app.core.config import Env
from app.dependencies.admin import AuthenticatedAdmin, get_current_admin
from app.dtos.admin_auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminLogoutResponse,
    AdminTokenRefreshResponse,
)
from app.services.admin_auth import AdminAuthService

admin_auth_router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

# 사용자 인증도 refresh_token 이라는 이름의 쿠키를 쓴다. 이름이 같으면 브라우저가
# 두 쿠키를 모두 보내 서버가 어느 쪽인지 알 수 없으므로 관리자용은 이름을 분리한다.
REFRESH_COOKIE_NAME = "admin_refresh_token"
# 관리자 인증 경로에서만 쿠키를 주고받는다. 다른 API 요청에는 실리지 않는다.
REFRESH_COOKIE_PATH = "/api/v1/admin/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=config.ENV == Env.PROD,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=config.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )


@admin_auth_router.post(
    "/login",
    response_model=AdminLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 로그인",
)
async def login(
    request: AdminLoginRequest,
    response: Response,
    service: Annotated[AdminAuthService, Depends(AdminAuthService)],
) -> AdminLoginResponse:
    """이메일·비밀번호로 로그인한다. (REQ-ADMIN-001)

    액세스 토큰은 본문으로, 리프레시 토큰은 `admin_refresh_token` http_only 쿠키로 내려간다.
    쿠키는 `/api/v1/admin/auth` 경로에서만 오간다.

    임시 비밀번호를 아직 바꾸지 않은 계정(PENDING)도 로그인은 되며, 이때
    `mustChangePassword` 가 true 다. 비밀번호 변경 외의 API 는 막힌다.

    - **401 INVALID_CREDENTIALS** — 이메일이 없거나 비밀번호가 틀림
      (이메일 존재 여부를 알 수 없도록 두 경우를 같은 응답으로 처리한다)
    - **403 ACCOUNT_SUSPENDED / ACCOUNT_WITHDRAWN** — 사용할 수 없는 계정
    """
    result, refresh_token = await service.login(request)
    _set_refresh_cookie(response, str(refresh_token))
    return result


@admin_auth_router.post(
    "/refresh",
    response_model=AdminTokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    summary="액세스 토큰 갱신",
)
async def refresh(
    service: Annotated[AdminAuthService, Depends(AdminAuthService)],
    admin_refresh_token: Annotated[str | None, Cookie()] = None,
) -> AdminTokenRefreshResponse:
    """리프레시 쿠키로 액세스 토큰을 새로 발급한다. (REQ-ADMIN-002)

    요청 본문은 없다. 브라우저가 `admin_refresh_token` 쿠키를 자동으로 보낸다.

    갱신 때마다 계정 상태를 다시 확인한다. 로그인 이후 정지된 계정이 리프레시 토큰만으로
    계속 접근하는 것을 막기 위해서다. 비밀번호 변경·정지·임시 비밀번호 재발송이 일어나면
    세션 난수가 바뀌어 이전 리프레시 토큰은 무효가 된다.

    - **401 UNAUTHORIZED / INVALID_TOKEN** — 쿠키가 없거나 만료·위변조됨, 또는 무효화된 세션
    - **403 ACCOUNT_SUSPENDED / ACCOUNT_WITHDRAWN** — 사용할 수 없는 계정
    """
    return await service.refresh(admin_refresh_token)


@admin_auth_router.post(
    "/logout",
    response_model=AdminLogoutResponse,
    status_code=status.HTTP_200_OK,
    summary="관리자 로그아웃",
)
async def logout(
    _: Annotated[AuthenticatedAdmin, Depends(get_current_admin)],
    response: Response,
) -> AdminLogoutResponse:
    """리프레시 쿠키를 삭제해 갱신을 막는다. (REQ-ADMIN-009)

    액세스 토큰은 JWT 라 서버에 저장하지 않으므로 즉시 무효화할 수 없고,
    만료(ACCESS_TOKEN_EXPIRE_MINUTES) 전까지는 그대로 유효하다.
    즉시 차단이 필요하면 Redis 블랙리스트에 jti 를 넣고 검증 단계에서 조회해야 하며,
    1차 범위 밖이다.
    """
    # 삭제하려면 발급 시와 path 가 같아야 한다.
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH, httponly=True)
    return AdminLogoutResponse(message="로그아웃되었습니다.")
