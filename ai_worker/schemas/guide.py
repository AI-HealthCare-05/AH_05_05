#LLM에 반환할 최종 구현(최종 회복 가이드 구조)

from pydantic import BaseModel, Field

from ai_worker.schemas.enums import SourceType, SafetyStatus


class GuideSource(BaseModel):#통합 출처 추적
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


class RecoveryGuideContent(BaseModel):#회복 안내서 본문 내용
    medication_guide: list[str] = Field(default_factory=list)
    patient_instructions: list[str] = Field(default_factory=list)
    public_information: list[str] = Field(default_factory=list)
    lifestyle_guide: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    follow_up_schedule: list[str] = Field(default_factory=list)
    safety_notice: str


class RecoveryGuideResult(BaseModel):#최종결과 래퍼 클래스
    care_episode_id: int
    guide_content: RecoveryGuideContent
    sources: list[GuideSource] = Field(default_factory=list)
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)