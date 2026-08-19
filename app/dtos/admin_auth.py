from pydantic import EmailStr, Field

from app.dtos.base import CamelModel
from app.models.enums import AdminRole


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
