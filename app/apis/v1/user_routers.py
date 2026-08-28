from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse as Response

from app.core.phone_encryption import decrypt_phone_number
from app.dependencies.security import get_request_user
from app.dtos.users import UserInfoResponse, UserUpdateRequest
from app.models.users import User
from app.services.users import UserManageService

user_router = APIRouter(prefix="/users", tags=["users"])


def _user_info_response(user: User) -> Response:
    response = UserInfoResponse.model_validate(user).model_copy(
        update={"phone_number": decrypt_phone_number(user.phone)}
    )
    return Response(response.model_dump(), status_code=status.HTTP_200_OK)


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
