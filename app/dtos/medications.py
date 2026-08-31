from datetime import date

from app.dtos.base import CamelModel


class MedicationStart(CamelModel):
    date: date
    slot: str


class MedicationMealTimes(CamelModel):
    morning: str
    lunch: str
    evening: str
    bedtime: str


class MedicationOverviewItem(CamelModel):
    medication_id: int
    name: str
    dose: str
    days: int
    days_remaining: int | None
    slots: list[str]
    as_needed: bool
    until_complete: bool | None = None


class MedicationOverview(CamelModel):
    record_id: int
    document_image_url: str
    start: MedicationStart
    end_date: date
    days_remaining: int
    meal_times: MedicationMealTimes
    medications: list[MedicationOverviewItem]


class SaveMedicationDoseRequest(CamelModel):
    date: date
    slot: str
    taken: bool


class MedicationDoseResponse(CamelModel):
    date: date
    slot: str
    taken: bool
