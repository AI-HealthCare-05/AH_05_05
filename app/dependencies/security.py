from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedError
from app.models.enums import AccountStatus
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.jwt import JwtService

security = HTTPBearer(auto_error=False)


async def get_request_user(
    credential: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
) -> User:
    if credential is None:
        raise UnauthorizedError()
    try:
        verified = JwtService().verify_jwt(
            token=credential.credentials,
            token_type="access",
        )
        user_id = verified.payload.get("user_id")
    except (HTTPException, KeyError, TypeError, ValueError) as error:
        raise UnauthorizedError("유효하지 않거나 만료된 토큰입니다.") from error
    if user_id is None:
        raise UnauthorizedError("유효하지 않은 토큰입니다.")
    user = await UserRepository().get_user(user_id)
    if not user:
        raise UnauthorizedError("사용자 계정을 찾을 수 없습니다.")
    if user.status != AccountStatus.ACTIVE:
        raise UnauthorizedError("활성 상태의 사용자 계정이 아닙니다.")
    return user
