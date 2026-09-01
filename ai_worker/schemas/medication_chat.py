from collections.abc import Awaitable, Callable
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_worker.domain.chat_content_compactor import CHAT_CONTENT_MAX_LENGTH
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_search import (
    MedicationSearchExecutionObservation,
)


class MedicationChatRoute(StrEnum):
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    SUPPLEMENT_GUIDE = "SUPPLEMENT_GUIDE"
    ACTIVE_INTAKE = "ACTIVE_INTAKE"
    INTERACTION = "INTERACTION"
    GENERAL_GUIDANCE = "GENERAL_GUIDANCE"
    CLARIFICATION = "CLARIFICATION"
    RESTRICTED = "RESTRICTED"


class MedicationChatProgressStage(StrEnum):
    QUESTION_CHECKING = "QUESTION_CHECKING"
    EVIDENCE_SEARCHING = "EVIDENCE_SEARCHING"
    ANSWER_GENERATING = "ANSWER_GENERATING"
    SAFETY_CHECKING = "SAFETY_CHECKING"


class MedicationAnswerRewriteStatus(StrEnum):
    REWRITTEN = "REWRITTEN"
    DRAFT_FALLBACK = "DRAFT_FALLBACK"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class MedicationAnswerFallbackReason(StrEnum):
    GENERATED_DOSAGE_NOT_IN_DRAFT = "GENERATED_DOSAGE_NOT_IN_DRAFT"
    UNSUPPORTED_SAFETY_ASSERTION = "UNSUPPORTED_SAFETY_ASSERTION"
    NO_GROUNDED_SOURCES = "NO_GROUNDED_SOURCES"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    CLIENT_ERROR = "CLIENT_ERROR"


class MedicationChatProgress(BaseModel):
    stage: MedicationChatProgressStage
    message: str = Field(min_length=1)

    @classmethod
    def for_stage(
        cls,
        stage: MedicationChatProgressStage,
    ) -> "MedicationChatProgress":
        messages = {
            MedicationChatProgressStage.QUESTION_CHECKING: "질문 확인 중",
            MedicationChatProgressStage.EVIDENCE_SEARCHING: "근거 검색 중",
            MedicationChatProgressStage.ANSWER_GENERATING: "답변 정리 중",
            MedicationChatProgressStage.SAFETY_CHECKING: "안전 확인 중",
        }
        return cls(stage=stage, message=messages[stage])


MedicationChatProgressCallback = Callable[
    [MedicationChatProgress],
    Awaitable[None],
]


class MedicationChatSourceKind(StrEnum):
    PATIENT_MEDICATION = "PATIENT_MEDICATION"
    PATIENT_SUPPLEMENT = "PATIENT_SUPPLEMENT"
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    INTERACTION_RULE = "INTERACTION_RULE"
    PUBLIC_KNOWLEDGE = "PUBLIC_KNOWLEDGE"


class MedicationChatRequest(BaseModel):
    request_id: UUID
    user_id: int = Field(ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    question: str = Field(
        min_length=1,
        max_length=CHAT_CONTENT_MAX_LENGTH,
    )
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class ActiveMedication(BaseModel):
    medication_id: int = Field(ge=1)
    care_episode_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    dose: str | None = None
    efficacy: str | None = None
    administration: str | None = None
    precautions: str | None = None
    times_per_day: int | None = Field(default=None, ge=1)
    note: str | None = None
    days: int | None = Field(default=None, ge=1)
    prescribed_at: date | None = None


class ActiveSupplement(BaseModel):
    registration_id: int = Field(ge=1)
    supplement_nutrient_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    dose_amount: str
    dose_unit: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    note: str | None = None


class ActiveIntakeContext(BaseModel):
    user_id: int = Field(ge=1)
    preferred_care_episode_id: int | None = Field(default=None, ge=1)
    medications: list[ActiveMedication] = Field(default_factory=list)
    supplements: list[ActiveSupplement] = Field(default_factory=list)


class MedicationGuideFact(BaseModel):
    medication_guide_id: int = Field(ge=1)
    item_seq: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    manufacturer_name: str = Field(min_length=1)
    efficacy: str
    usage_instructions: str
    pre_use_warning: str
    precautions: str
    drug_food_interactions: str
    adverse_reactions: str
    storage_instructions: str


class MedicationGuideLookup(BaseModel):
    guide: MedicationGuideFact | None = None
    representative_guide: MedicationGuideFact | None = None
    is_ambiguous: bool = False
    candidate_names: list[str] = Field(default_factory=list)


class InteractionRuleFact(BaseModel):
    interaction_rule_id: int = Field(ge=1)
    pair_key: str = Field(min_length=1)
    pair_type: str = Field(min_length=1)
    left_name: str = Field(min_length=1)
    right_name: str = Field(min_length=1)
    risk_level: str = Field(min_length=1)
    effect_texts: list[str] = Field(min_length=1)
    source_titles: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class MedicationChatSource(BaseModel):
    kind: MedicationChatSourceKind
    title: str = Field(min_length=1)
    organization: str | None = None
    url: str | None = None
    medication_id: int | None = Field(default=None, ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    user_supplement_id: int | None = Field(default=None, ge=1)
    medication_guide_id: int | None = Field(default=None, ge=1)
    interaction_rule_id: int | None = Field(default=None, ge=1)
    dataset_key: str | None = None
    dataset_version: str | None = None
    vector_chunk_id: str | None = None
    source_page_number: int | None = Field(default=None, ge=1)
    similarity_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class MedicationChatResult(BaseModel):
    request_id: UUID
    answer: str = Field(min_length=1)
    route: MedicationChatRoute
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)
    sources: list[MedicationChatSource] = Field(default_factory=list)
    model_name: str | None = None
    model_version: str | None = None
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    context_hash: str | None = Field(default=None, min_length=64, max_length=64)
    search_observation: MedicationSearchExecutionObservation | None = Field(
        default=None,
        exclude=True,
    )


class MedicationAnswerGenerationObservation(BaseModel):
    status: MedicationAnswerRewriteStatus
    fallback_used: bool
    fallback_reason: MedicationAnswerFallbackReason | None = None
    draft_answer_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_answer_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_status_contract(self) -> "MedicationAnswerGenerationObservation":
        if self.status == MedicationAnswerRewriteStatus.DRAFT_FALLBACK:
            if not self.fallback_used or self.fallback_reason is None:
                raise ValueError("DRAFT_FALLBACK은 fallback_reason이 필요합니다.")
        elif self.status == MedicationAnswerRewriteStatus.REWRITTEN:
            if self.fallback_used or self.fallback_reason is not None:
                raise ValueError("REWRITTEN에는 fallback_reason을 사용할 수 없습니다.")
            if self.generated_answer_hash is None:
                raise ValueError("REWRITTEN은 generated_answer_hash가 필요합니다.")
        return self


class MedicationAnswerGenerationOutcome(BaseModel):
    result: MedicationChatResult
    observation: MedicationAnswerGenerationObservation
