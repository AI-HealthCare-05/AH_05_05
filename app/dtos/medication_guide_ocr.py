from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

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


class MedicationReview(CamelModel):
    row_id: str
    name: str
    dose: str | None = None
    efficacy: str | None = None
    administration: str | None = None
    precautions: str | None = None
    times_per_day: int | None = Field(default=None, ge=1, le=6)
    days: int | None = Field(default=None, ge=1, le=365)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, exclude_if=lambda value: value is None)
    needs_review: bool


class MedicationGuideReviewResult(CamelModel):
    dispensing_date: date | None = None
    dispensing_date_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    next_visit_date: date | None = None
    medications: list[MedicationReview] = Field(default_factory=list)
    review_issues: list[ReviewIssue] = Field(default_factory=list)


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
    temp_id: str | None = Field(default=None, min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    dose: str | None = Field(default=None, max_length=100)
    efficacy: str | None = Field(default=None, max_length=500)
    administration: str | None = Field(default=None, max_length=500)
    precautions: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    times_per_day: int | None = Field(default=None, ge=1, le=6)
    days: int | None = Field(default=None, ge=1, le=365)


class MedicationGuideConfirmRequest(CamelModel):
    dispensing_date: date
    next_visit_date: date | None = None
    medications: list[MedicationConfirmation] = Field(max_length=100)


class OcrConfirmationResponse(CamelModel):
    ocr_job_id: str
    care_episode_id: str
    status: Literal["COMPLETE"] = "COMPLETE"
    confirmed_at: datetime


ConfidenceTier = Literal["high", "medium", "low"]


class DocumentOcrUploadResponse(CamelModel):
    batch_id: str
    document_ids: list[int]
    ocr_status: Literal["queued", "processing", "ready_for_review", "complete", "failed", "cancelled"]


class DocumentOcrField(CamelModel):
    value: str | None = None
    confidence: ConfidenceTier


class DocumentOcrFields(CamelModel):
    dispensed_date: DocumentOcrField


class DocumentOcrMedication(CamelModel):
    temp_id: str
    name: str
    dose: str = ""
    efficacy: str = ""
    administration: str = ""
    precautions: str = ""
    times_per_day: int | None = Field(default=None, ge=1, le=6)
    days: int | None = Field(default=None, ge=1, le=365)
    confidence: ConfidenceTier | None = Field(default=None, exclude_if=lambda value: value is None)


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


class DocumentMedicationConfirmation(CamelModel):
    temp_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    dose: str = Field(max_length=100)
    efficacy: str = Field(max_length=500)
    administration: str = Field(max_length=500)
    precautions: str = Field(max_length=500)
    times_per_day: int | None = Field(default=None, ge=1, le=6)
    days: int | None = Field(default=None, ge=1, le=365)


class DocumentOcrConfirmRequest(CamelModel):
    dispensed_date: date
    medications: list[DocumentMedicationConfirmation] = Field(max_length=100)

    @field_validator("dispensed_date")
    @classmethod
    def reject_future_dispensing_date(cls, value: date) -> date:
        if value > datetime.now(config.TIMEZONE).date():
            raise ValueError("조제일은 오늘 이후일 수 없습니다.")
        return value


class DocumentOcrConfirmResponse(CamelModel):
    record_id: int
    has_medication: bool
    status_code: Literal["active"] = "active"
