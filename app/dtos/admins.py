from datetime import datetime

from pydantic import Field

from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.accounts import AccountStatus
from app.models.admin import AdminRole


class AdminListQuery(PageQuery):
    """REQ-ADMIN-010 관리자 목록 조회 쿼리."""

    keyword: str | None = Field(default=None, description="이름·이메일 부분 일치")
    role: AdminRole | None = None
    # 관리자 계정에는 WITHDRAWN을 쓰지 않는다(탈퇴는 사용자 전용).
    # AccountStatus를 공유하므로 값 자체는 통과하나 결과가 항상 비어 있다.
    status: AccountStatus | None = None


class AdminListItem(CamelModel):
    admin_id: int
    name: str
    email: str
    role: AdminRole
    status: AccountStatus


class AdminDetailResponse(CamelModel):
    """REQ-ADMIN-010 관리자 상세 조회 응답."""

    admin_id: int
    name: str
    email: str
    role: AdminRole
    status: AccountStatus
    # 최초 슈퍼 ADMIN은 생성자가 없어 null이다.
    # 다만 ERD의 admin.created_by_account_id 는 NOT NULL 이라 현재 스키마로는 저장할 수 없다.
    # 시드 방식(자기 참조 허용 / nullable 전환) 결정 필요 — 이슈 #10 참조.
    created_by_account_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime
