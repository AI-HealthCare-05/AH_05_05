from tortoise.transactions import in_transaction

from app.core.exceptions import InvalidPasswordError, SamePasswordError
from app.core.phone_encryption import encrypt_phone_number
from app.core.utils.common import normalize_phone_number
from app.core.utils.security import hash_password, verify_password
from app.dtos.users import PasswordChangeRequest, UserUpdateRequest
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.auth import AuthService


class UserManageService:
    def __init__(self):
        self.repo = UserRepository()
        self.auth_service = AuthService()

    async def update_user(self, user: User, data: UserUpdateRequest) -> User:
        if data.email:
            await self.auth_service.check_email_exists(data.email)
        payload = data.model_dump(exclude_none=True)
        if data.phone_number:
            normalized_phone_number = normalize_phone_number(data.phone_number)
            payload["phone"] = encrypt_phone_number(normalized_phone_number)
            payload.pop("phone_number", None)
        async with in_transaction():
            await self.repo.update_instance(user=user, data=payload)
            await user.refresh_from_db()
        return user

    async def change_password(self, user: User, data: PasswordChangeRequest) -> None:
        """로그인한 본인의 비밀번호를 바꾼다.

        관리자 쪽(AdminAuthService.change_password)과 같은 흐름이고 제약도 같다 —
        발급된 JWT 를 개별 폐기할 수단이 없어 다른 기기에 남은 토큰은 끊지 못한다.
        """
        if not verify_password(data.current_password, user.hashed_password):
            raise InvalidPasswordError()
        # 현재와 같은 값이면 바꾼 것이 아니다. 해시가 매번 달라 문자열 비교로는 못 잡는다.
        if verify_password(data.new_password, user.hashed_password):
            raise SamePasswordError()

        user.hashed_password = hash_password(data.new_password)
        await user.save()
