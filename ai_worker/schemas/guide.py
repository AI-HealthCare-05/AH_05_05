from typing import Literal

from pydantic import BaseModel, Field

from ai_worker.schemas.enums import SafetyStatus, SourceType


class GuideSource(BaseModel):
    source_type: SourceType
    extracted_field_id: int | None = None

    public_dataset_key: str | None = None
    dataset_version: str | None = None
    vector_chunk_id: str | None = None
    source_record_key: str | None = None
    source_field: str | None = None
    chunk_type: str | None = None

    source_title: str | None = None
    source_organization: str | None = None
    source_url: str | None = None
    similarity_score: float | None = None


class RecoveryGuideSupplement(BaseModel):
    """LLM이 생성할 수 있는 보충정보."""

    public_information: list[str] = Field(default_factory=list)
    lifestyle_guide: list[str] = Field(default_factory=list)


class RecoveryGuideContent(BaseModel):
    medication_guide: list[str] = Field(
        default_factory=list
    )
    patient_instructions: list[str] = Field(
        default_factory=list
    )
    public_information: list[str] = Field(
        default_factory=list
    )
    lifestyle_guide_label: Literal[
        "AI 생성 일반 안내"
    ] = "AI 생성 일반 안내"
    lifestyle_guide: list[str] = Field(
        default_factory=list
    )
    warning_signs: list[str] = Field(
        default_factory=list
    )
    follow_up_schedule: list[str] = Field(
        default_factory=list
    )
    safety_notice: str


class RecoveryGuideResult(BaseModel):
    care_episode_id: int
    guide_content: RecoveryGuideContent
    sources: list[GuideSource] = Field(default_factory=list)
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)
