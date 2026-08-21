from datetime import date, datetime
from typing import Self

from pydantic import Field, model_validator

from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.enums import AccountStatus


class AdminUserListQuery(PageQuery):
    """REQ-ADMIN-004 사용자 목록 조회 쿼리."""

    keyword: str | None = Field(default=None, description="이름·이메일 부분 일치")
    status: AccountStatus | None = None
    start_date: date | None = Field(default=None, description="가입일 시작 (YYYY-MM-DD)")
    end_date: date | None = Field(default=None, description="가입일 종료 (YYYY-MM-DD)")

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("가입일 시작이 종료보다 늦을 수 없습니다.")
        return self


class AdminUserListItem(CamelModel):
    user_id: int
    name: str
    email: str
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
    # 복약 알람이 (사용자 x 시간대) 단위라 사용자당 최대 4건이므로,
    # 화면이 기대하는 "활성 알림 수"와 같은지 알림 담당자 확인이 남아 있다.
    active_alarm_count: int = 0
