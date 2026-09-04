from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, StringConstraints

from app.core.validators.user_validators import validate_name
from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.enums import AccountStatus, AdminRole, BackgroundJobStatus

# 사용자 회원가입(SignUpRequest.name)과 같은 규칙이다. 한 서비스 안에서 이름 규칙이
# 갈리면 관리자 목록의 이름 검색이 사용자 쪽과 다르게 동작한다.
#
# strip_whitespace 를 넣지 않는다. 앞뒤 공백을 잘라내지 않고 validate_name 이 거부한다
# (사용자 쪽과 같은 방식이다). 화면이 trim() 해서 보내므로 실사용에 지장이 없다.
AdminName = Annotated[
    str,
    StringConstraints(min_length=2, max_length=20),
    AfterValidator(validate_name),
]


class AdminListQuery(PageQuery):
    """REQ-ADMIN-010 관리자 목록 조회 쿼리."""

    keyword: str | None = Field(default=None, description="이름·이메일 부분 일치")
    name: str | None = Field(default=None, description="이름 부분 일치")
    email: str | None = Field(default=None, description="이메일 부분 일치")
    role: AdminRole | None = None
    # 관리자 계정에는 WITHDRAWN을 쓰지 않는다(탈퇴는 사용자 전용).
    # AccountStatus를 공유하므로 값 자체는 통과하나 결과가 항상 비어 있다.
    status: AccountStatus | None = None


class AdminCreateRequest(CamelModel):
    """REQ-ADMIN-008 관리자 등록 요청. 비밀번호는 서버가 생성하므로 받지 않는다."""

    name: AdminName
    email: EmailStr = Field(max_length=255)
    role: AdminRole
    # true -> ACTIVE, false -> PENDING(임시 비밀번호 변경 대기)
    is_active: bool = True


class AdminStatusUpdateRequest(CamelModel):
    """REQ-ADMIN-011 관리자 정지·해제 요청.

    API 는 여러 건을 받도록 되어 있으나, 현재 화면은 한 번에 한 명만 보낸다
    (`adminIds: [adminId]`). 체크박스로 여럿을 고르는 화면은 만들어진 적이 없다.
    """

    admin_ids: list[int] = Field(min_length=1, max_length=100)
    # 계정 삭제(WITHDRAWN)는 제공하지 않는다.
    #
    # 화면의 「활성화」는 ACTIVE 가 아니라 **PENDING 을 보낸다.** 정지 해제된 계정은
    # 본인이 로그인해야 ACTIVE 가 된다는 결정 때문이다(전환은 login 에서 일어난다).
    # 서비스에서 몰래 바꾸지 않고 요청 값을 그대로 저장하는 이유는, 응답이 요청 값을
    # 되돌려주는 구조(update_status)라 요청과 저장이 다르면 화면이 틀린 상태로 행을
    # 그리기 때문이다.
    status: Literal[AccountStatus.SUSPENDED, AccountStatus.ACTIVE, AccountStatus.PENDING]


class AdminRoleUpdateRequest(CamelModel):
    """REQ-ADMIN-011 관리자 역할 변경 요청.

    상태 변경(정지·해제)은 PATCH /accounts/status 가 일괄로 처리한다. 역할은 한 명씩
    바꾸므로 대상을 경로 파라미터로 받고 본문에는 새 역할만 담는다.
    """

    role: AdminRole


class AdminRoleUpdateResponse(CamelModel):
    admin_id: int
    role: AdminRole


class AdminNameUpdateRequest(CamelModel):
    """관리자 이름 변경 요청.

    이메일은 로그인 식별자라 바꾸지 않는다. 역할은 PATCH /accounts/{id}/role 이 맡는다.
    """

    name: AdminName


class AdminNameUpdateResponse(CamelModel):
    admin_id: int
    name: str


class AdminPasswordResetResponse(CamelModel):
    """REQ-ADMIN-003 임시 비밀번호 재발송 결과."""

    admin_id: int
    email: str
    # 임시 비밀번호 발송 전의 계정 상태를 그대로 반환한다.
    status: AccountStatus
    email_job_id: int
    email_job_status: BackgroundJobStatus


class AdminStatusUpdateResponse(CamelModel):
    updated_count: int
    status: AccountStatus
    admin_ids: list[int]


class AdminListItem(CamelModel):
    admin_id: int
    name: str
    email: str
    role: AdminRole
    status: AccountStatus


class AdminCreateResponse(CamelModel):
    """등록 응답. 조회 응답과 달리 메일 발송 결과를 함께 알려준다.

    발송에 실패해도 계정 생성은 롤백하지 않으므로, 관리자가 이 값으로 상황을 알 수 있어야 한다.
    """

    admin_id: int
    name: str
    email: str
    role: AdminRole
    status: AccountStatus
    created_by_admin_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime
    email_job_id: int
    email_job_status: BackgroundJobStatus


class AdminDetailResponse(CamelModel):
    """REQ-ADMIN-010 관리자 상세 조회 응답."""

    admin_id: int
    name: str
    email: str
    role: AdminRole
    status: AccountStatus
    # 최초 슈퍼 ADMIN 은 생성자가 없어 null 이다(admin.id 자기 참조, nullable).
    created_by_admin_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime
