from tortoise.transactions import in_transaction

from app.core.phone_encryption import encrypt_phone_number
from app.core.utils.common import normalize_phone_number
from app.dtos.users import UserUpdateRequest
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
