from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core import config
from app.core.config import Env
from app.dtos.user_auth import UserLoginRequest, UserLoginResponse
from app.services.user_auth import UserAuthService

# ERD v3 에서 accounts 테이블은 사라졌지만 경로는 프론트와 합의된 값이라 그대로 쓴다.
accounts_router = APIRouter(prefix="/accounts", tags=["accounts"])

# 관리자도 리프레시 쿠키를 쓴다(admin_refresh_token, /api/v1/admin/auth).
# 이름과 경로가 겹치면 브라우저가 둘 다 보내 서버가 어느 쪽인지 알 수 없다.
# 같은 브라우저에서 관리자·사용자가 동시에 로그인할 수 있으므로 반드시 분리한다.
REFRESH_COOKIE_NAME = "user_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/accounts"

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_400_BAD_REQUEST: {
        "description": "이메일이 없거나 비밀번호가 틀림 (두 경우를 구분하지 않는다)",
        "content": {"application/json": {"example": {"detail": "이메일 또는 비밀번호가 일치하지 않습니다."}}},
    },
    status.HTTP_403_FORBIDDEN: {
        "description": "정지·탈퇴 계정",
        "content": {"application/json": {"example": {"detail": "정지된 계정입니다."}}},
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": "필수 필드 누락 또는 이메일 형식 오류",
        "content": {
            "application/json": {"example": {"code": "VALIDATION_ERROR", "message": "입력값이 올바르지 않습니다."}}
        },
    },
}


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


@accounts_router.post(
    "/login",
    response_model=UserLoginResponse,
    status_code=status.HTTP_200_OK,
    summary="사용자 로그인",
    responses=_ERROR_RESPONSES,
)
async def login(
    request: UserLoginRequest,
    response: Response,
    service: Annotated[UserAuthService, Depends(UserAuthService)],
) -> UserLoginResponse:
    """이메일·비밀번호로 로그인한다. 인증 불필요.

    액세스 토큰은 본문으로, 리프레시 토큰은 `user_refresh_token` http_only 쿠키로 내려간다.
    쿠키는 `/api/v1/accounts` 경로에서만 오간다(관리자 쿠키와 분리).

    **`statusCode` 는 계정 상태가 아니라 진료기록 유무다.**

    | 값 | 뜻 | `latestRecordId` |
    |---|---|---|
    | `"active"` | 진료기록 1건 이상 | 가장 최근 기록 ID |
    | `"pending"` | 진료기록 없음 | `null` |

    두 값은 항상 짝이 맞는다. `"active"` 인데 `latestRecordId` 가 `null` 일 수 없다.

    - **400** — 이메일이 없거나 비밀번호가 틀림. 이메일 존재 여부가 드러나지 않도록
      두 경우의 상태 코드·본문·응답 시간을 모두 같게 맞춘다
    - **403** — 정지·탈퇴 계정 (관리자 로그인과 같은 상태 코드)
    - **422** — 필수 필드 누락 또는 이메일 형식 오류

    갱신 엔드포인트는 아직 없다. 쿠키만 발급해 두고 별건으로 처리한다.
    """
    result, refresh_token = await service.login(request)
    _set_refresh_cookie(response, str(refresh_token))
    return result
