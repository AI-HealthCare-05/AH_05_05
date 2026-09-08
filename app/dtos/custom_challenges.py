from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from app.dtos.base import CamelModel
from app.models.enums import ChallengeParticipationStatus, CustomChallengeType, MealSlot


class CustomChallengeJoinRequest(CamelModel):
    model_config = CamelModel.model_config | {"extra": "forbid"}

    target_ids: list[int] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=64)

    @field_validator("target_ids")
    @classmethod
    def canonicalize_target_ids(cls, value: list[int]) -> list[int]:
        if any(target_id <= 0 for target_id in value):
            raise ValueError("target IDs must be positive")
        if len(value) != len(set(value)):
            raise ValueError("target IDs must be unique")
        return sorted(value)

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("idempotency key must not be blank")
        return value


class CustomChallengeRecommendationTarget(CamelModel):
    id: int
    name: str
    existing_participation_id: int | None = None


class CustomChallengeRecommendation(CamelModel):
    template_id: int
    challenge_type: CustomChallengeType
    challenge_name: str
    action: Literal["NONE"] = "NONE"
    targets: list[CustomChallengeRecommendationTarget]


class CustomChallengeRecommendationListResponse(CamelModel):
    items: list[CustomChallengeRecommendation]
    total_count: int


class CustomChallengeTargetResponse(CamelModel):
    id: int
    source_id: int
    name: str


class CustomChallengeOccurrenceResponse(CamelModel):
    id: int
    target_id: int
    scheduled_date: date
    slot: MealSlot
    scheduled_at: AwareDatetime
    is_completed: bool


class CustomChallengeParticipationResponse(CamelModel):
    id: int
    template_id: int
    challenge_type: CustomChallengeType
    challenge_name: str
    status: ChallengeParticipationStatus
    joined_at: AwareDatetime
    end_at: AwareDatetime
    actual_end_date: date
    target_count: int
    completed_count: int
    progress_rate: Decimal
    action: Literal["NONE"] = "NONE"
    targets: list[CustomChallengeTargetResponse]
    occurrences: list[CustomChallengeOccurrenceResponse]


class CustomChallengeParticipationListResponse(CamelModel):
    items: list[CustomChallengeParticipationResponse]
    total_count: int
