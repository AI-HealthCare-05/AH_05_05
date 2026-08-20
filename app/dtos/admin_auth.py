from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field

from app.core.validators.user_validators import validate_password
from app.dtos.base import CamelModel
from app.models.enums import AccountStatus, AdminRole


class AdminLoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AdminInfo(CamelModel):
    admin_id: int
    name: str
    email: str
    role: AdminRole


class AdminLoginResponse(CamelModel):
    """리프레시 토큰은 본문에 담지 않고 http_only 쿠키로 내려준다(NFR-ADMIN-001)."""

    access_token: str
    admin: AdminInfo
    # PENDING(임시 비밀번호 미변경) 계정이면 true. 프론트가 비밀번호 변경 화면으로 유도한다.
    must_change_password: bool


class AdminTokenRefreshResponse(CamelModel):
    access_token: str


class AdminLogoutResponse(CamelModel):
    message: str


class AdminPasswordChangeRequest(CamelModel):
    """REQ-ADMIN-009. 대상은 토큰의 sub 로 정하며 관리자 ID 를 받지 않는다."""

    current_password: str = Field(min_length=1)
    # 사용자 회원가입과 같은 검증기를 쓴다. 권한이 더 큰 관리자 쪽 정책이 더 느슨하면 안 되고,
    # 함수를 공유하면 두 곳의 정책이 어긋날 일도 없다.
    new_password: Annotated[str, AfterValidator(validate_password)]


class AdminPasswordChangeResponse(CamelModel):
    message: str
    # PENDING 계정은 변경과 함께 ACTIVE 로 전환된다.
    status: AccountStatus
