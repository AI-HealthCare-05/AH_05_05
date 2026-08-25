from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse

from app.core.exceptions import AppError, UserAuthError

# 본문 위치를 나타내는 loc 접두사. 프론트에 넘길 field 이름에서 제외한다.
_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})

# Pydantic 이 커스텀 validator 의 ValueError 앞에 붙이는 접두사.
# message 는 사용자에게 그대로 노출되므로 제거한다.
_VALUE_ERROR_PREFIX = "Value error, "


async def app_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
    error = exc if isinstance(exc, AppError) else AppError()
    return ORJSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message},
    )


async def validation_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
    content: dict[str, Any] = {"code": "VALIDATION_ERROR", "message": "입력값이 올바르지 않습니다."}

    if isinstance(exc, RequestValidationError) and exc.errors():
        first = exc.errors()[0]
        content["message"] = first.get("msg", content["message"]).removeprefix(_VALUE_ERROR_PREFIX)
        # 프론트가 field로 해당 입력칸 아래에 메시지를 붙인다(client.ts 참조).
        location = [str(part) for part in first.get("loc", ()) if part not in _LOC_PREFIXES]
        if location:
            content["field"] = location[-1]

    return ORJSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content=content)


async def user_auth_error_handler(request: Request, exc: Exception) -> ORJSONResponse:
    """사용자 인증 실패를 {"detail": ...} 로 직렬화한다.

    프론트 명세가 이 형식이라 관리자 API 의 {"code", "message"} 와 다르다.
    **팀 규약이 정해지면 이 함수만 고치면 된다** — 라우터·서비스는 UserAuthError 만 던진다.
    """
    error = exc if isinstance(exc, UserAuthError) else UserAuthError()
    return ORJSONResponse(status_code=error.status_code, content={"detail": error.detail})


def register_exception_handlers(app: FastAPI) -> None:
    """회의 확정 규격({"code", "message"})으로 응답하는 핸들러를 등록한다.

    사용자 로그인만 프론트 명세에 맞춰 {"detail"} 을 쓰며 UserAuthError 계열이 담당한다.
    나머지 기존 인증·사용자 API는 아직 HTTPException({"detail": ...})을 직접 사용한다.
    해당 API 이관은 별도 작업이며, 그때 HTTPException 핸들러도 함께 추가한다.
    """
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(UserAuthError, user_auth_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
