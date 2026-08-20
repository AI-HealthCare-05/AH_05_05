from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.enums import AccountStatus, AdminRole


class AdminListQuery(PageQuery):
    """REQ-ADMIN-010 관리자 목록 조회 쿼리."""

    keyword: str | None = Field(default=None, description="이름·이메일 부분 일치")
    role: AdminRole | None = None
    # 관리자 계정에는 WITHDRAWN을 쓰지 않는다(탈퇴는 사용자 전용).
    # AccountStatus를 공유하므로 값 자체는 통과하나 결과가 항상 비어 있다.
    status: AccountStatus | None = None


class AdminCreateRequest(CamelModel):
    """REQ-ADMIN-008 관리자 등록 요청. 비밀번호는 서버가 생성하므로 받지 않는다."""

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=255)
    role: AdminRole
    # true -> ACTIVE, false -> PENDING(임시 비밀번호 변경 대기)
    is_active: bool = True


class AdminStatusUpdateRequest(CamelModel):
    """REQ-ADMIN-011 관리자 정지·해제 요청. 화면에서 체크박스로 여러 명을 선택한다."""

    admin_ids: list[int] = Field(min_length=1, max_length=100)
    # 계정 삭제는 제공하지 않는다. 정지·해제만 가능하다.
    status: Literal[AccountStatus.SUSPENDED, AccountStatus.ACTIVE]


class AdminPasswordResetResponse(CamelModel):
    """REQ-ADMIN-003 임시 비밀번호 재발송 결과."""

    admin_id: int
    email: str
    # 재발송하면 항상 PENDING 으로 돌아간다(임시 비밀번호를 다시 바꿔야 하므로).
    status: AccountStatus
    # false 면 비밀번호는 바뀌었지만 새 임시 비밀번호가 전달되지 않은 상태다.
    email_sent: bool


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
    # false 면 계정은 만들어졌지만 임시 비밀번호가 전달되지 않은 상태다.
    email_sent: bool


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
