from datetime import datetime

from fastapi.exceptions import HTTPException
from pydantic import EmailStr
from starlette import status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import SignupEmailAlreadyExistsError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.phone_encryption import encrypt_phone_number
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
                    phone=encrypt_phone_number(normalized_phone_number),
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
        """로그인 자격 검증.

        **실패 사유를 구분해 알려주지 않는다.** 계정 없음·비밀번호 불일치·정지·탈퇴·대기가
        모두 같은 응답으로 나간다. 사유가 드러나면 그 이메일이 이 서비스에 등록돼 있다는
        사실이 새어나가, 이메일 목록을 넣어보는 것만으로 가입자를 골라낼 수 있다.

        예전에는 비활성 계정만 423 ACCOUNT_INACTIVE 로 갈라져 문구를 보지 않아도 구분됐다.

        **감수하는 것**: 정지된 사용자가 「관리자에게 문의하세요」 안내를 잃는다.
        비밀번호가 틀린 줄 알고 계속 다시 치게 된다. 보안을 우선하기로 한 선택이다(#196).

        관리자 로그인(AdminAuthService)은 이 규칙을 따르지 않는다. 내부용이라 열거 위험이
        낮고, 관리자에게는 정지 사유를 알려주는 편이 낫다.

        **남는 한계**: 계정이 없으면 verify_password 를 타지 않아 응답이 더 빠르다.
        응답 시간으로는 여전히 가입 여부를 구분할 수 있다. 막으려면 없는 계정에도
        더미 해시를 대조해 시간을 맞춰야 하는데, 이번 범위 밖으로 두었다.
        """
        user = await self.user_repo.get_user_by_email(str(data.email))
        if (
            user is None
            or not verify_password(data.password, user.hashed_password)
            or user.status != AccountStatus.ACTIVE
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        return user

    async def login(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        return self.jwt_service.issue_jwt_pair(user)

    async def check_email_exists(self, email: str | EmailStr) -> None:
        if await self.user_repo.exists_by_email(email):
            raise SignupEmailAlreadyExistsError()
