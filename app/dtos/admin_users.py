from datetime import date, datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.enums import AccountStatus


class AdminUserListQuery(PageQuery):
    """REQ-ADMIN-004 사용자 목록 조회 쿼리."""

    keyword: str | None = Field(default=None, description="이름·이메일 부분 일치")
    name: str | None = Field(default=None, description="이름 부분 일치")
    email: str | None = Field(default=None, description="이메일 부분 일치")
    status: AccountStatus | None = None
    start_date: date | None = Field(default=None, description="가입일 시작 (YYYY-MM-DD)")
    end_date: date | None = Field(default=None, description="가입일 종료 (YYYY-MM-DD)")

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("가입일 시작이 종료보다 늦을 수 없습니다.")
        return self


class AdminUserStatusUpdateRequest(CamelModel):
    """REQ-ADMIN-006 사용자 정지·해제 요청. 화면에서 체크박스로 여러 명을 선택한다."""

    user_ids: list[int] = Field(min_length=1, max_length=100)
    # 계정 삭제(WITHDRAWN)는 여기서 다루지 않는다. 탈퇴는 본인 의사이고,
    # 관리자에 의한 데이터 삭제는 REQ-ADMIN-007 의 별도 API 다.
    status: Literal[AccountStatus.SUSPENDED, AccountStatus.ACTIVE]


class AdminUserStatusUpdateResponse(CamelModel):
    updated_count: int
    status: AccountStatus
    user_ids: list[int]


class AdminUserListItem(CamelModel):
    user_id: int
    name: str
    email: str
    phone: str | None = None
    status: AccountStatus
    created_at: datetime


class AdminUserDetailResponse(CamelModel):
    """REQ-ADMIN-005 사용자 상세 조회 응답."""

    user_id: int
    name: str
    email: str
    phone: str | None = None
    status: AccountStatus
    # user_settings.is_terms_agreed. user 와 1:1 이라 조인해서 가져온다.
    # 설정 행이 아직 없는 사용자는 미동의(False)로 본다.
    is_terms_agreed: bool = False
    created_at: datetime
    # alarms.status = 'ACTIVE' 인 행의 수 (alarm_type 무관).
    # 복약 알람이 (사용자 x 시간대) 단위라 사용자당 최대 4건이다.
    # 「등록된」 수이지 「발송될」 수가 아니다 — 알림 설정이 꺼져 있거나 계정이
    # 활성이 아니면 발송 시점에 SKIPPED 로 걸러진다(#258).
    active_alarm_count: int = 0
