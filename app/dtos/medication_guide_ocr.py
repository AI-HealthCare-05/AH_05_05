from datetime import date
from typing import Literal

from pydantic import Field

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
