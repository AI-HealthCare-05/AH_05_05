from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.core import config
from app.dtos.base import BaseSerializerModel
from app.models.enums import AlarmEventType, AlarmStatus, AlarmType, MealSlot
from app.services.alarm_schedule import next_occurrence, parse_timezone, validate_alarm_shape


def _validate_aware_datetime(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("scheduled_at must include timezone information.")


class AlarmCreateRequest(BaseModel):
    care_episode_id: Annotated[int | None, Field(gt=0)] = None
    source_guide_id: Annotated[int | None, Field(gt=0)] = None
    follow_up_visit_id: Annotated[int | None, Field(gt=0)] = None
    alarm_type: AlarmType = AlarmType.MEDICATION
    meal_slot: MealSlot | None = None
    title: Annotated[str, Field(min_length=1, max_length=255)]
    message: Annotated[str | None, Field(max_length=500)] = None
    scheduled_at: datetime
    recurrence_rule: Annotated[str | None, Field(max_length=100)] = None
    timezone: Annotated[str, Field(min_length=1, max_length=50)] = Field(
        default_factory=lambda: str(config.TIMEZONE)
    )

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        validate_alarm_shape(self.alarm_type, self.meal_slot)
        parse_timezone(self.timezone)
        _validate_aware_datetime(self.scheduled_at)
        if self.recurrence_rule and next_occurrence(self.recurrence_rule, self.scheduled_at, self.scheduled_at) is None:
            raise ValueError("recurrence_rule must have a future occurrence.")
        return self


class AlarmUpdateRequest(BaseModel):
    care_episode_id: Annotated[int | None, Field(gt=0)] = None
    source_guide_id: Annotated[int | None, Field(gt=0)] = None
    follow_up_visit_id: Annotated[int | None, Field(gt=0)] = None
    alarm_type: AlarmType | None = None
    meal_slot: MealSlot | None = None
    title: Annotated[str | None, Field(min_length=1, max_length=255)] = None
    message: Annotated[str | None, Field(max_length=500)] = None
    scheduled_at: datetime | None = None
    recurrence_rule: Annotated[str | None, Field(max_length=100)] = None
    timezone: Annotated[str | None, Field(min_length=1, max_length=50)] = None

    @model_validator(mode="after")
    def validate_supplied_schedule(self) -> Self:
        if self.timezone is not None:
            parse_timezone(self.timezone)
        if self.scheduled_at is not None:
            _validate_aware_datetime(self.scheduled_at)
        if self.recurrence_rule and self.scheduled_at:
            if next_occurrence(self.recurrence_rule, self.scheduled_at, self.scheduled_at) is None:
                raise ValueError("recurrence_rule must have a future occurrence.")
        return self


class AlarmActionRequest(BaseModel):
    action: Literal["pause", "resume", "complete", "skip"]


class AlarmResponse(BaseSerializerModel):
    id: int
    user_id: int
    care_episode_id: int | None
    source_guide_id: int | None
    follow_up_visit_id: int | None
    alarm_type: AlarmType
    meal_slot: MealSlot | None
    title: str
    message: str | None
    scheduled_at: datetime
    recurrence_rule: str | None
    #timezone: str
    #next_trigger_at: datetime
    status: AlarmStatus
    #last_triggered_at: datetime | None
    #completed_at: datetime | None
    #cancelled_at: datetime | None
    #created_at: datetime
    #updated_at: datetime | None


class AlarmListResponse(BaseModel):
    items: list[AlarmResponse]
    total: int
    offset: int
    limit: int


class PushSubscriptionUpsertRequest(BaseModel):
    endpoint: Annotated[str, Field(min_length=1, max_length=500)]
    p256dh_key: Annotated[str, Field(min_length=1, max_length=255)]
    auth_key: Annotated[str, Field(min_length=1, max_length=255)]
    platform: Annotated[str | None, Field(max_length=50)] = None
    user_agent: Annotated[str | None, Field(max_length=255)] = None


class PushSubscriptionResponse(BaseSerializerModel):
    id: int
    user_id: int
    endpoint: str
    platform: str | None
    user_agent: str | None
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class PushSubscriptionListResponse(BaseModel):
    items: list[PushSubscriptionResponse]


class DeliveryAckRequest(BaseModel):
    push_subscription_id: Annotated[int, Field(gt=0)]
    payload: dict[str, object] | None = None


class AlarmEventResponse(BaseSerializerModel):
    id: int
    alarm_id: int
    event_type: AlarmEventType
    push_subscription_id: int | None
    event_at: datetime
    payload: dict[str, object] | list[object] | None
    error_code: str | None
    created_at: datetime


class AlarmEventListResponse(BaseModel):
    items: list[AlarmEventResponse]
    total: int
    offset: int
    limit: int


class PushPublicKeyResponse(BaseModel):
    public_key: str
