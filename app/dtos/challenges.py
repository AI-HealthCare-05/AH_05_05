from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    BadgeAwardStatus,
    ChallengeParticipationStatus,
    ChallengeVerificationStatus,
)


class SnakeModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BadgeCreateRequest(SnakeModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    image_path: str = Field(min_length=1, max_length=500)
    is_active: bool = True


class BadgeUpdateRequest(SnakeModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    image_path: str | None = Field(default=None, min_length=1, max_length=500)
    is_active: bool | None = None


class BadgeResponse(SnakeModel):
    id: int
    name: str
    description: str | None
    image_path: str
    is_active: bool
    created_by_admin_id: int | None
    updated_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None


class BadgeImageUploadResponse(SnakeModel):
    image_path: str


class ChallengeCreateRequest(SnakeModel):
    name: str = Field(min_length=1, max_length=100)
    challenge_type_id: int = Field(ge=1)
    phrase: str = Field(min_length=1, max_length=255)
    description: str | None = None
    recruit_start_at: datetime
    recruit_end_at: datetime
    challenge_period_id: int = Field(ge=1)
    check_type_id: int = Field(ge=1)
    check_frequency_id: int = Field(ge=1)
    reward_badge_id: int | None = Field(default=None, ge=1)
    is_displayed: bool = False

    @model_validator(mode="after")
    def validate_recruit_period(self) -> "ChallengeCreateRequest":
        if self.recruit_end_at <= self.recruit_start_at:
            raise ValueError("모집 종료 일시는 모집 시작 일시보다 늦어야 합니다.")
        return self


class ChallengeUpdateRequest(SnakeModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    challenge_type_id: int | None = Field(default=None, ge=1)
    phrase: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    recruit_start_at: datetime | None = None
    recruit_end_at: datetime | None = None
    challenge_period_id: int | None = Field(default=None, ge=1)
    check_type_id: int | None = Field(default=None, ge=1)
    check_frequency_id: int | None = Field(default=None, ge=1)
    reward_badge_id: int | None = Field(default=None, ge=1)
    is_displayed: bool | None = None


class ChallengeResponse(SnakeModel):
    id: int
    name: str
    challenge_type_id: int
    phrase: str
    description: str | None
    recruit_start_at: datetime
    recruit_end_at: datetime
    challenge_period_id: int
    check_type_id: int
    check_frequency_id: int
    reward_badge_id: int | None
    is_displayed: bool
    is_deleted: bool
    created_by_admin_id: int | None
    updated_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None


class BadgeListResponse(SnakeModel):
    items: list[BadgeResponse]
    total_count: int
    offset: int
    limit: int


class BadgeAdminListQuery(SnakeModel):
    badge_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class ChallengeListResponse(SnakeModel):
    items: list[ChallengeResponse]
    total_count: int
    offset: int
    limit: int


class ChallengeAdminListQuery(SnakeModel):
    name: str | None = Field(default=None, max_length=100)
    challenge_type_id: int | None = Field(default=None, ge=1)
    is_displayed: bool | None = None
    recruit_start_date: date | None = None
    recruit_end_date: date | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_recruit_search_period(self) -> "ChallengeAdminListQuery":
        if self.recruit_start_date and self.recruit_end_date and self.recruit_end_date < self.recruit_start_date:
            raise ValueError("조회 기간이 올바르지 않습니다.")
        return self


class CustomChallengeTemplateCreateRequest(SnakeModel):
    name: str = Field(min_length=1, max_length=100)
    check_type_id: int = Field(ge=1)
    is_active: bool = True


class CustomChallengeTemplateUpdateRequest(SnakeModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    check_type_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class CustomChallengeTemplateResponse(SnakeModel):
    id: int
    name: str
    check_type_id: int
    is_active: bool
    created_by_admin_id: int | None
    updated_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime | None


class CustomChallengeTemplateListResponse(SnakeModel):
    items: list[CustomChallengeTemplateResponse]
    total_count: int
    offset: int
    limit: int


class CustomChallengeTemplateAdminListQuery(SnakeModel):
    template_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, max_length=100)
    check_type_id: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)


class ProgressResponse(SnakeModel):
    id: int
    period_start: date
    period_end: date
    target_count: int
    completed_count: int
    progress_rate: Decimal
    is_completed: bool
    completed_at: datetime | None


class UserChallengeResponse(SnakeModel):
    id: int
    user_id: int
    challenge_id: int
    challenge_name: str
    status: ChallengeParticipationStatus
    joined_at: datetime
    started_at: datetime
    end_at: datetime
    target_count: int
    completed_count: int
    progress_rate: Decimal
    completed_at: datetime | None
    cancelled_at: datetime | None
    progress_periods: list[ProgressResponse]


class UserChallengeListResponse(SnakeModel):
    items: list[UserChallengeResponse]
    total_count: int


class VerificationCreateRequest(SnakeModel):
    verification_date: date
    idempotency_key: str = Field(min_length=16, max_length=64)
    content: str | None = Field(default=None, max_length=500)
    image_path: str | None = Field(default=None, max_length=500)


class VerificationResponse(SnakeModel):
    id: int
    user_challenge_id: int
    progress_id: int
    verification_date: date
    content: str | None
    image_path: str | None
    status: ChallengeVerificationStatus
    rejection_reason: str | None
    reviewed_by_admin_id: int | None
    reviewed_at: datetime | None
    submitted_at: datetime


class VerificationListResponse(SnakeModel):
    items: list[VerificationResponse]
    total_count: int
    offset: int
    limit: int


class VerificationActionRequest(SnakeModel):
    action: Literal["APPROVE", "REJECT"]
    rejection_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "VerificationActionRequest":
        if self.action == "REJECT" and not (self.rejection_reason or "").strip():
            raise ValueError("반려 사유를 입력해 주세요.")
        return self


class UserBadgeResponse(SnakeModel):
    id: int
    user_id: int
    badge_id: int
    challenge_id: int
    user_challenge_id: int
    status: BadgeAwardStatus
    badge_name: str
    badge_image_path: str
    awarded_at: datetime
    revoked_at: datetime | None
    revoke_reason: str | None


class UserBadgeListResponse(SnakeModel):
    items: list[UserBadgeResponse]
    total_count: int
