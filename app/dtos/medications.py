from datetime import date, datetime

from pydantic import Field, field_validator, model_validator

from app.dtos.base import CamelModel
from app.models.enums import CareEpisodeStatus


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
    alias: str | None = None
    document_image_url: str
    start: MedicationStart
    end_date: date
    days_remaining: int
    is_finished: bool
    meal_times: MedicationMealTimes
    medications: list[MedicationOverviewItem]


class SaveMedicationDoseRequest(CamelModel):
    date: date
    slot: str
    taken: bool
    record_id: int


class MedicationDoseResponse(CamelModel):
    date: date
    slot: str
    taken: bool
    record_id: int


class UpdateCareEpisodeAliasRequest(CamelModel):
    alias: str | None = Field(max_length=50)

    @field_validator("alias", mode="before")
    @classmethod
    def normalize_alias(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        return value


class CareEpisodeAliasResponse(CamelModel):
    alias: str | None = None


class CreateMedicationNoteRequest(CamelModel):
    care_episode_id: int = Field(gt=0)
    medication_id: int | None = Field(default=None, gt=0)
    dosed_at: datetime
    body: str = Field(min_length=1, max_length=500)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("복약 메모 내용을 입력해주세요.")
        return normalized


class UpdateMedicationNoteRequest(CamelModel):
    medication_id: int | None = Field(default=None, gt=0)
    dosed_at: datetime | None = None
    body: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("복약 메모 내용을 입력해주세요.")
        return normalized

    @model_validator(mode="after")
    def reject_null_required_updates(self) -> "UpdateMedicationNoteRequest":
        if "dosed_at" in self.model_fields_set and self.dosed_at is None:
            raise ValueError("복용 일시는 비워둘 수 없습니다.")
        if "body" in self.model_fields_set and self.body is None:
            raise ValueError("복약 메모 내용을 입력해주세요.")
        return self


class MedicationNoteMedicationResponse(CamelModel):
    id: int
    name: str
    dose: str | None = None


class MedicationNoteResponse(CamelModel):
    id: int
    care_episode_id: int
    care_episode_title: str
    care_episode_alias: str | None = None
    care_episode_start_date: date | None = None
    care_episode_status: CareEpisodeStatus
    available_medications: list[MedicationNoteMedicationResponse] = Field(default_factory=list)
    medication_id: int | None = None
    medication: MedicationNoteMedicationResponse | None = None
    dosed_at: datetime
    body: str
    created_at: datetime
    updated_at: datetime | None = None


class MedicationNoteListResponse(CamelModel):
    items: list[MedicationNoteResponse]
    total: int = Field(ge=0)
    next_cursor: str | None = None


# 이름을 명시적으로 풀어 쓴 코드와 짧은 코드가 모두 읽기 쉽도록 호환 별칭을 둔다.
MedicationNoteCreateRequest = CreateMedicationNoteRequest
MedicationNoteUpdateRequest = UpdateMedicationNoteRequest
