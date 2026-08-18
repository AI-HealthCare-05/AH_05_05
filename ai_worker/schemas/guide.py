from typing import Literal, Self

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

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
    source_page_number: int | None = Field(
        default=None,
        ge=1,
    )
    source_license: str | None = None
    similarity_score: float | None = None

    @model_validator(mode="after")
    def validate_source_fields(
        self,
    ) -> Self:
        if self.source_type == SourceType.PATIENT_SAVED_FIELD:
            if self.extracted_field_id is None:
                raise ValueError("환자 출처에는 extracted_field_id가 필요합니다.")

            forbidden_public_fields = (
                "public_dataset_key",
                "dataset_version",
                "vector_chunk_id",
                "source_record_key",
                "source_field",
                "chunk_type",
                "source_title",
                "source_organization",
                "source_url",
                "source_page_number",
                "source_license",
                "similarity_score",
            )

            for field_name in forbidden_public_fields:
                if (
                    getattr(
                        self,
                        field_name,
                    )
                    is not None
                ):
                    raise ValueError(f"환자 출처에는 {field_name}를 사용할 수 없습니다.")

        if self.source_type == SourceType.PUBLIC_RAG_CHUNK:
            if self.extracted_field_id is not None:
                raise ValueError("공공 출처에는 extracted_field_id를 사용할 수 없습니다.")

            required_public_fields = (
                "public_dataset_key",
                "vector_chunk_id",
                "source_record_key",
            )

            for field_name in required_public_fields:
                if (
                    getattr(
                        self,
                        field_name,
                    )
                    is None
                ):
                    raise ValueError(f"공공 출처에는 {field_name}가 필요합니다.")

        return self


class RecoveryGuideSupplement(BaseModel):
    """LLM이 생성할 수 있는 보충정보."""

    public_information: list[str] = Field(default_factory=list)
    lifestyle_guide: list[str] = Field(default_factory=list)


class RecoveryGuideContent(BaseModel):
    medication_guide: list[str] = Field(default_factory=list)
    patient_instructions: list[str] = Field(default_factory=list)
    public_information: list[str] = Field(default_factory=list)
    lifestyle_guide_label: Literal["AI 생성 일반 안내"] = "AI 생성 일반 안내"
    lifestyle_guide: list[str] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    follow_up_schedule: list[str] = Field(default_factory=list)
    safety_notice: str


class RecoveryGuideResult(BaseModel):
    care_episode_id: int
    guide_content: RecoveryGuideContent
    sources: list[GuideSource] = Field(default_factory=list)
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)
