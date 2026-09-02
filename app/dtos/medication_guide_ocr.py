from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from app.core import config
from app.dtos.base import CamelModel


class ReviewIssue(CamelModel):
    code: str
    path: str


class OcrErrorResponse(CamelModel):
    code: str
    message: str
    field: str | None = None


class OcrField(CamelModel):
    name: str
    text: str
    confidence: float = Field(ge=0.0, le=1.0)


class DoseComponents(CamelModel):
    dose_quantity: str | None = None
    dose_unit: str | None = None
    times_per_day: int | None = Field(default=None, ge=1)
    days: int | None = Field(default=None, ge=1)


class Medication(CamelModel):
    row_id: str
    name: str
    strength: str | None = None
    category: str | None = None
    efficacy: str | None = None
    dose_line: str | None = None
    dose_quantity: str | None = None
    dose_unit: str | None = None
    times_per_day: int | None = Field(default=None, ge=1)
    days: int | None = Field(default=None, ge=1)
    administration: str | None = None
    precautions: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool
    source_field_names: list[str]


class MedicationGuideResult(CamelModel):
    schema_version: Literal["medication-guide-template/v2"] = "medication-guide-template/v2"
    dispensing_date: date | None = None
    next_visit_date: date | None = None
    medications: list[Medication] = Field(default_factory=list)
    review_issues: list[ReviewIssue] = Field(default_factory=list)
    ocr_fields: list[OcrField] = Field(default_factory=list)


ConfidenceTier = Literal["high", "medium", "low"]


class DocumentOcrField(CamelModel):
    value: date
    confidence: ConfidenceTier


class DocumentOcrFields(CamelModel):
    dispensed_date: DocumentOcrField = Field(default=MISSING)


class MedicationReview(CamelModel):
    temp_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    strength: str = Field(default=MISSING, min_length=1, max_length=50)
    dose_quantity: str = Field(default=MISSING, min_length=1, max_length=50)
    times_per_day: int = Field(default=MISSING, ge=1, le=6)
    days: int = Field(default=MISSING, ge=1, le=365)
    confidence: ConfidenceTier | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medication name must not be blank")
        return value


class MedicationGuideReviewResult(CamelModel):
    fields: DocumentOcrFields = Field(default_factory=DocumentOcrFields)
    medications: list[MedicationReview] = Field(default_factory=list)
    low_confidence_count: int = Field(default=0, ge=0)


class MedicationGuideOcrJobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OcrJobAcceptedResponse(CamelModel):
    ocr_job_id: str
    status: MedicationGuideOcrJobStatus
    status_url: str


class OcrJobStatusResponse(CamelModel):
    ocr_job_id: str
    status: MedicationGuideOcrJobStatus
    expires_at: datetime | None = None
    result: MedicationGuideReviewResult | None = None
    error_code: str | None = None


class MedicationConfirmation(CamelModel):
    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"],
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    temp_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    strength: str = Field(default=MISSING, min_length=1, max_length=50)
    dose_quantity: str = Field(default=MISSING, min_length=1, max_length=50)
    times_per_day: int | None = Field(default=MISSING, ge=1, le=6)
    days: int = Field(default=MISSING, ge=1, le=365)

    @field_validator("name", "strength")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medication text must not be blank")
        return value

    @field_validator("dose_quantity")
    @classmethod
    def normalize_dose_quantity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("dose quantity must not be blank")
        return normalized


class MedicationGuideConfirmRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"],
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    dispensing_date: date
    medications: list[MedicationConfirmation] = Field(max_length=100)

    @field_validator("dispensing_date")
    @classmethod
    def validate_dispensing_date(cls, value: date) -> date:
        return _validate_confirmation_date(value)


class OcrConfirmationResponse(CamelModel):
    ocr_job_id: str
    care_episode_id: str
    status: Literal["COMPLETE"] = "COMPLETE"
    confirmed_at: datetime


class DocumentOcrUploadResponse(CamelModel):
    batch_id: str
    document_ids: list[int]
    ocr_status: Literal["queued", "processing", "ready_for_review", "complete", "failed", "cancelled"]


class DocumentOcrMedication(MedicationReview):
    pass


class DocumentOcrPendingResponse(CamelModel):
    batch_id: str
    ocr_status: Literal["queued", "processing", "cancelled"]


class DocumentOcrFailedResponse(CamelModel):
    batch_id: str
    ocr_status: Literal["failed"] = "failed"
    error_code: str


class DocumentOcrReadyResponse(CamelModel):
    batch_id: str
    ocr_status: Literal["ready_for_review", "complete"]
    document_image_url: str
    fields: DocumentOcrFields
    medications: list[DocumentOcrMedication]
    low_confidence_count: int = Field(ge=0)


DocumentOcrStatusResponse = Annotated[
    DocumentOcrPendingResponse | DocumentOcrFailedResponse | DocumentOcrReadyResponse,
    Field(discriminator="ocr_status"),
]


class DocumentMedicationConfirmation(MedicationConfirmation):
    pass


class DocumentOcrConfirmRequest(CamelModel):
    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"],
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )

    dispensed_date: date
    medications: list[DocumentMedicationConfirmation] = Field(max_length=100)

    @field_validator("dispensed_date")
    @classmethod
    def reject_future_dispensing_date(cls, value: date) -> date:
        return _validate_confirmation_date(value)


class DocumentOcrConfirmResponse(CamelModel):
    record_id: int
    has_medication: bool
    status_code: Literal["active"] = "active"


def _validate_confirmation_date(value: date) -> date:
    if value > datetime.now(config.TIMEZONE).date() + timedelta(days=31):
        raise ValueError("조제일은 오늘로부터 31일 이후일 수 없습니다.")
    return value
