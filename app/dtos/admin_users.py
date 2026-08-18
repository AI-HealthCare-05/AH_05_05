from datetime import date, datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from app.dtos.base import CamelModel
from app.dtos.pagination import PageQuery
from app.models.accounts import AccountStatus


class ConsentType(StrEnum):
    """ERD v3 user_consents.consent_type. 프론트 REQ-DOC-002의 3항목과 일치한다.

    user_consents 모델이 만들어지면 app/models/user_consents.py 로 옮긴다(models 1:1 규칙).
    """

    MEDICAL_DATA = "MEDICAL_DATA"  # [필수] 진료기록 및 처방정보 수집
    AI_USAGE = "AI_USAGE"  # [필수] AI 이용 안내
    NOTIFICATION = "NOTIFICATION"  # [선택] 복약·진료 알림 수신


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


class UserConsentItem(CamelModel):
    """REQ-DOC-002 항목별 동의. 프론트가 항목별 동의 여부와 각 동의 시각을 요구한다."""

    consent_type: ConsentType
    agreed: bool
    agreed_at: datetime
    # ERD v3 user_consents 에는 withdrawn_at 컬럼이 없다.
    # 철회는 agreed=false 인 새 행으로 남기므로(UPDATE 하지 않음) 서비스에서 파생시킨다.
    #   최신 행 agreed=false -> withdrawn_at = 그 행의 agreed_at
    #   최신 행 agreed=true  -> withdrawn_at = null
    withdrawn_at: datetime | None = None


class AdminUserDetailResponse(CamelModel):
    """REQ-ADMIN-005 사용자 상세 조회 응답."""

    user_id: int
    name: str
    email: str
    phone: str | None = None
    status: AccountStatus
    is_alarm: bool
    created_at: datetime
    consents: list[UserConsentItem] = Field(default_factory=list)
    # ERD v3 기준 alarms.status = 'ACTIVE' 인 행의 수 (alarm_type 무관).
    # 복약 알람이 (사용자 x 시간대) 단위로 바뀌어 사용자당 최대 4건이므로,
    # 화면이 기대하는 "활성 알림 수"와 같은지 알림 담당자 확인이 남아 있다.
    active_alarm_count: int = 0
