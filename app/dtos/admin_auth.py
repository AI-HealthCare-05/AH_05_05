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
    # 로그인 직전 상태가 PENDING 이었으면 true. 즉 "이번이 첫 로그인"이다.
    #
    # 예전 이름은 must_change_password 였고 실제로 강제였다. 비밀번호 변경이 선택제가
    # 되면서 must 가 거짓말이 돼 개명했다. 지금은 **권유 프롬프트를 한 번 띄우는 신호**일
    # 뿐이고, 닫아도 모든 기능을 쓸 수 있다.
    #
    # "임시 비밀번호를 아직 쓰고 있는가"와는 다르다. 로그인과 동시에 ACTIVE 로 바뀌므로
    # 두 번째 로그인부터는 비밀번호를 안 바꿨어도 false 다. 그 용도로는 쓸 수 없다.
    # 「재설정」으로 임시 비밀번호를 재발급하면 다시 PENDING 이 되어 true 로 돌아온다.
    is_first_login: bool


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
