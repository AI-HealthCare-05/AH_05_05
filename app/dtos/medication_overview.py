from datetime import date
from typing import Literal

from app.dtos.base import CamelModel

MealSlotValue = Literal["morning", "lunch", "evening", "bedtime"]


class MedicationOverviewStartResponse(CamelModel):
    date: date
    slot: MealSlotValue


class MedicationOverviewMealTimesResponse(CamelModel):
    morning: str
    lunch: str
    evening: str
    bedtime: str


class MedicationOverviewItemResponse(CamelModel):
    medication_id: int
    name: str
    dose: str
    days: int
    days_remaining: int
    slots: list[MealSlotValue]
    as_needed: bool
    until_complete: bool = False


class MedicationOverviewResponse(CamelModel):
    record_id: int
    document_image_url: str
    start: MedicationOverviewStartResponse
    end_date: date
    days_remaining: int
    meal_times: MedicationOverviewMealTimesResponse
    medications: list[MedicationOverviewItemResponse]
