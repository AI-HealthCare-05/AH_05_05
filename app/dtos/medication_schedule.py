from pydantic import Field

from app.dtos.base import CamelModel


class MedicationScheduleStart(CamelModel):
    """The API intentionally uses lowercase slot names, independent of the ORM enum."""

    date: str
    slot: str


class MedicationScheduleMealTimes(CamelModel):
    morning: str
    lunch: str
    evening: str
    bedtime: str


class MedicationScheduleMedication(CamelModel):
    medication_id: int
    name: str
    dose: str
    times_per_day: int | None
    timing: str
    slots: list[str]


class MedicationScheduleResponse(CamelModel):
    start: MedicationScheduleStart | None
    meal_times: MedicationScheduleMealTimes | None
    medications: list[MedicationScheduleMedication]


class MedicationScheduleAssignment(CamelModel):
    medication_id: int
    slots: list[str] = Field(default_factory=list)


class SaveMedicationScheduleRequest(CamelModel):
    start: MedicationScheduleStart
    meal_times: MedicationScheduleMealTimes
    medications: list[MedicationScheduleAssignment] = Field(default_factory=list)


class SaveMedicationScheduleResponse(CamelModel):
    saved: bool = True
