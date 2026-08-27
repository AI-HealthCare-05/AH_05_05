from datetime import datetime

from fastapi.exceptions import HTTPException
from pydantic import EmailStr
from starlette import status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import SignupEmailAlreadyExistsError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.utils.common import normalize_phone_number
from app.core.utils.security import hash_password, verify_password
from app.dtos.auth import LoginRequest, SignUpRequest
from app.models.enums import AccountStatus
from app.models.users import User, UserSettings
from app.repositories.user_repository import UserRepository
from app.services.jwt import JwtService


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.jwt_service = JwtService()

    async def signup(self, data: SignUpRequest) -> User:
        # 이메일 중복 체크
        await self.check_email_exists(data.email)

        # 입력받은 휴대폰 번호를 노말라이즈
        normalized_phone_number = normalize_phone_number(data.phone_number)

        # 유저 생성. 사전 중복 조회 뒤 같은 이메일이 동시에 들어와도 DB unique
        # 위반을 프론트 계약(409)으로 돌려준다.
        try:
            async with in_transaction():
                user = await self.user_repo.create_user(
                    email=data.email,
                    hashed_password=hash_password(data.password),  # 해시화된 비밀번호를 사용
                    name=data.name,
                    phone=normalized_phone_number,
                    birth_date=data.birth_date,
                    gender=data.gender,
                    status=AccountStatus.ACTIVE,
                )
                await UserSettings.create(
                    user=user,
                    is_terms_agreed=data.is_terms_agreed,
                    terms_agreed_at=datetime.now(config.TIMEZONE),
                )

                return user
        except IntegrityError:
            if await self.user_repo.exists_by_email(data.email):
                raise SignupEmailAlreadyExistsError() from None
            raise

    async def authenticate(self, data: LoginRequest) -> User:
        # 이메일로 사용자 조회
        email = str(data.email)
        user = await self.user_repo.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        # 비밀번호 검증
        if not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        # 활성 사용자 체크
        if user.status != AccountStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="비활성화된 계정입니다.")

        return user

    async def login(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        return self.jwt_service.issue_jwt_pair(user)

    async def check_email_exists(self, email: str | EmailStr) -> None:
        if await self.user_repo.exists_by_email(email):
            raise SignupEmailAlreadyExistsError()
