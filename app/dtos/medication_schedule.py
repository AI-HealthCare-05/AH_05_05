from datetime import date, time
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.dtos.base import CamelModel

MealSlotValue = Literal["morning", "lunch", "evening", "bedtime"]


class MedicationStartResponse(CamelModel):
    date: date
    slot: MealSlotValue


class MedicationMealTimesResponse(CamelModel):
    morning: str
    lunch: str
    evening: str
    bedtime: str


class ScheduledMedicationResponse(CamelModel):
    medication_id: int
    name: str
    dose: str
    times_per_day: int | None
    timing: str
    slots: list[MealSlotValue]


class MedicationScheduleResponse(CamelModel):
    start: MedicationStartResponse | None
    meal_times: MedicationMealTimesResponse | None
    medications: list[ScheduledMedicationResponse]


class MedicationStartRequest(CamelModel):
    date: date
    slot: MealSlotValue


class MedicationMealTimesRequest(CamelModel):
    morning: str
    lunch: str
    evening: str
    bedtime: str

    @field_validator("morning", "lunch", "evening", "bedtime")
    @classmethod
    def validate_half_hour_time(cls, value: str) -> str:
        try:
            parsed = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("알림 시각은 HH:MM 형식이어야 합니다.") from exc
        if parsed.second != 0 or parsed.microsecond != 0 or parsed.minute % 30 != 0:
            raise ValueError("알림 시각은 30분 단위여야 합니다.")
        return parsed.strftime("%H:%M")

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        values = [self.morning, self.lunch, self.evening, self.bedtime]
        if values != sorted(values) or len(set(values)) != len(values):
            raise ValueError("알림 시각은 아침, 점심, 저녁, 취침 순서여야 합니다.")
        return self


class MedicationSlotRequest(CamelModel):
    medication_id: int = Field(gt=0)
    slots: list[MealSlotValue] = Field(min_length=1, max_length=4)

    @field_validator("slots")
    @classmethod
    def validate_unique_slots(cls, value: list[MealSlotValue]) -> list[MealSlotValue]:
        if len(value) != len(set(value)):
            raise ValueError("같은 복용 시간대를 중복해서 저장할 수 없습니다.")
        return value


class MedicationScheduleSaveRequest(CamelModel):
    record_id: int = Field(gt=0)
    start: MedicationStartRequest
    meal_times: MedicationMealTimesRequest
    medications: list[MedicationSlotRequest]


class MedicationScheduleSaveResponse(CamelModel):
    saved: bool = True
