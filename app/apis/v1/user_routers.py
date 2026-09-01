from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse as Response

from app.core.phone_encryption import decrypt_phone_number
from app.dependencies.security import get_request_user
from app.dtos.users import PasswordChangeRequest, PasswordChangeResponse, UserInfoResponse, UserUpdateRequest
from app.models.users import User
from app.services.users import UserManageService

user_router = APIRouter(prefix="/users", tags=["users"])


def _user_info_response(user: User) -> Response:
    response = UserInfoResponse.model_validate(user).model_copy(
        update={"phone_number": decrypt_phone_number(user.phone)}
    )
    # by_alias 가 없으면 CamelModel 이라도 snake_case 로 나간다. 여기서는 응답을 직접
    # 만들어 FastAPI 의 직렬화(기본 by_alias=True)를 거치지 않기 때문이다.
    return Response(response.model_dump(by_alias=True), status_code=status.HTTP_200_OK)


@user_router.get("/me", response_model=UserInfoResponse, status_code=status.HTTP_200_OK)
async def user_me_info(
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    return _user_info_response(user)


@user_router.patch("/me", response_model=UserInfoResponse, status_code=status.HTTP_200_OK)
async def update_user_me_info(
    update_data: UserUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    user_manage_service: Annotated[UserManageService, Depends(UserManageService)],
) -> Response:
    updated_user = await user_manage_service.update_user(user=user, data=update_data)
    return _user_info_response(updated_user)


@user_router.patch("/me/password", response_model=PasswordChangeResponse, status_code=status.HTTP_200_OK)
async def change_my_password(
    request: PasswordChangeRequest,
    user: Annotated[User, Depends(get_request_user)],
    user_manage_service: Annotated[UserManageService, Depends(UserManageService)],
) -> Response:
    """로그인한 본인의 비밀번호를 바꾼다.

    대상은 토큰의 사용자로 정한다. 다른 사용자 ID 를 받는 파라미터는 없다.

    조회(GET)·수정(PATCH)·탈퇴(DELETE)와 같은 `user` 리소스라 `/users/me` 아래에 둔다.
    `/me/settings` 는 `user_settings` 라는 다른 테이블을 다뤄 경로가 따로다.
    새 비밀번호는 회원가입과 같은 정책을 따른다 —
    8자 이상, 대문자·소문자·숫자·특수문자 각 1개 이상.

    관리자 비밀번호 변경과 같은 제약이 있다. 발급된 JWT 를 개별 폐기할 수단이 없어
    **다른 기기에 남은 토큰은 끊지 못하고** 만료될 때까지 유효하다.

    - **400 INVALID_PASSWORD** — 현재 비밀번호 불일치
    - **400 SAME_AS_CURRENT** — 새 비밀번호가 현재와 동일
    - **422 VALIDATION_ERROR** — 비밀번호 정책 위반 (부족한 조건을 메시지로 알려준다)
    """
    await user_manage_service.change_password(user=user, data=request)
    return Response(
        # detail 은 한 단어라 지금은 차이가 없지만, 필드가 늘 때 조용히 snake 로
        # 나가지 않도록 위 응답과 같은 방식을 쓴다.
        PasswordChangeResponse(detail="비밀번호가 변경되었습니다.").model_dump(by_alias=True),
        status_code=status.HTTP_200_OK,
    )
