from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import JSONResponse as Response

from app.core import config
from app.core.config import Env
from app.dtos.auth import LoginRequest, LoginResponse, SignUpRequest, TokenRefreshResponse
from app.services.auth import AuthService
from app.services.jwt import JwtService

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# 관리자도 리프레시 쿠키를 쓴다(admin_refresh_token, /api/v1/admin/auth).
# 이름과 경로가 겹치면 브라우저가 둘 다 보내 서버가 어느 쪽인지 알 수 없다.
REFRESH_COOKIE_NAME = "refresh_token"
# path 를 지정하지 않으면 "/" 가 되어 리프레시 토큰이 모든 요청에 실려 나간다.
# 필요한 곳은 GET /api/v1/auth/token/refresh 하나뿐이므로 그 위로 좁힌다.
REFRESH_COOKIE_PATH = "/api/v1/auth"


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignUpRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    await auth_service.signup(request)
    return Response(content={"detail": "회원가입이 성공적으로 완료되었습니다."}, status_code=status.HTTP_201_CREATED)


@auth_router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    user = await auth_service.authenticate(request)
    tokens = await auth_service.login(user)
    resp = Response(
        content=LoginResponse(access_token=str(tokens["access_token"])).model_dump(), status_code=status.HTTP_200_OK
    )
    # 자동 로그인을 쓰지 않기로 해 기본값은 꺼짐이다. 만료되면 다시 로그인한다.
    # 관리자 콘솔은 별도 쿠키(admin_refresh_token)를 쓰며 이 플래그의 영향을 받지 않는다.
    if config.USER_REFRESH_ENABLED:
        resp.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=str(tokens["refresh_token"]),
            httponly=True,
            secure=True if config.ENV == Env.PROD else False,
            # domain 을 지정하지 않는다. COOKIE_DOMAIN="localhost" 를 넣으면 쿠키가 ".localhost" 로
            # 저장되는데, 단일 라벨 도메인이라 클라이언트가 전송을 거부해 갱신이 통째로 깨진다.
            # 생략하면 host-only 쿠키가 되어 발급한 호스트에만 실린다(관리자 쿠키와 같은 방식).
            path=REFRESH_COOKIE_PATH,
            max_age=config.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
        )
    return resp


@auth_router.get(
    "/token/refresh",
    response_model=TokenRefreshResponse,
    status_code=status.HTTP_200_OK,
    # 꺼져 있으면 문서에도 노출하지 않는다. import 시점 값이라 런타임 판단은 아래에서 한 번 더 한다.
    include_in_schema=config.USER_REFRESH_ENABLED,
)
async def token_refresh(
    jwt_service: Annotated[JwtService, Depends(JwtService)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    # 자동 로그인이 꺼져 있으면 이 엔드포인트는 없는 것으로 취급한다.
    # 라우트를 조건부로 등록하지 않고 여기서 막는 이유는, 테스트가 플래그를 켜고 끄며
    # 양쪽 동작을 확인할 수 있어야 하기 때문이다(등록 시점에 정하면 재import 가 필요하다).
    if not config.USER_REFRESH_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is missing.")
    access_token = jwt_service.refresh_jwt(refresh_token)
    return Response(
        content=TokenRefreshResponse(access_token=str(access_token)).model_dump(), status_code=status.HTTP_200_OK
    )
