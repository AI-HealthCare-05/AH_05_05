from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.domain.chat_content_compactor import CHAT_CONTENT_MAX_LENGTH
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import (
    MedicationQueryEntityType,
    MedicationQuestionInterpretation,
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
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MedicationChatRiskFlag(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class MedicationChatAnswerDomain(StrEnum):
    MEDICATION = "MEDICATION"
    SUPPLEMENT = "SUPPLEMENT"
    LIFESTYLE = "LIFESTYLE"


class MedicationChatRiskScope(StrEnum):
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    EVIDENCE_WITH_GENERAL_GUIDANCE = "EVIDENCE_WITH_GENERAL_GUIDANCE"
    GENERAL_GUIDANCE_ONLY = "GENERAL_GUIDANCE_ONLY"
    WARNING_REQUIRED = "WARNING_REQUIRED"


class SupplementRegistrationSafetyStatus(StrEnum):
    SAFE = "SAFE"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


class MedicationChatRiskProfile(BaseModel):
    """사용자 입력에서 온 취약군·고위험 상태. 입력되지 않은 값은 UNKNOWN이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pregnancy: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    breastfeeding: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    minor: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    older_adult: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    kidney_disease: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    liver_disease: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    scheduled_surgery: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN
    anticoagulant_use: MedicationChatRiskFlag = MedicationChatRiskFlag.UNKNOWN

    @classmethod
    def all_no(cls) -> "MedicationChatRiskProfile":
        return cls(**{field: MedicationChatRiskFlag.NO for field in cls.model_fields})


class MedicationChatRiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: MedicationChatAnswerDomain
    scope: MedicationChatRiskScope
    reason_codes: list[str] = Field(default_factory=list)

    @property
    def warning_required(self) -> bool:
        return self.scope == MedicationChatRiskScope.WARNING_REQUIRED


class MedicationChatSessionReferenceEntity(BaseModel):
    """같은 세션의 근거 섹션에서만 추출한 재질문 후보."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    entity_type: MedicationQueryEntityType
    kind: InteractionEntityKind | None = None


class MedicationChatSessionReference(BaseModel):
    """다른 세션과 분리된 최근 확정 대상의 구조화 기억."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entities: list[MedicationChatSessionReferenceEntity] = Field(
        default_factory=list,
        max_length=4,
    )


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
    UNSUPPORTED_EVIDENCE_SECTION = "UNSUPPORTED_EVIDENCE_SECTION"
    NO_GROUNDED_SOURCES = "NO_GROUNDED_SOURCES"
    PATIENT_CONTEXT_ONLY = "PATIENT_CONTEXT_ONLY"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    CLIENT_ERROR = "CLIENT_ERROR"


class MedicationChatReasonCode(StrEnum):
    QUERY_PLAN_FAILED = "QUERY_PLAN_FAILED"
    AMBIGUOUS_QUERY_EXPRESSION = "AMBIGUOUS_QUERY_EXPRESSION"
    IN_SCOPE_NO_EVIDENCE = "IN_SCOPE_NO_EVIDENCE"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    INTERACTION_RULE_REPOSITORY_UNAVAILABLE = "INTERACTION_RULE_REPOSITORY_UNAVAILABLE"
    AMBIGUOUS_MEDICATION_NAME = "AMBIGUOUS_MEDICATION_NAME"
    INGREDIENT_FAMILY_DETAIL_REQUIRED = "INGREDIENT_FAMILY_DETAIL_REQUIRED"
    FATIGUE_FOLLOW_UP_REQUIRED = "FATIGUE_FOLLOW_UP_REQUIRED"
    FATIGUE_URGENT_ASSISTANCE = "FATIGUE_URGENT_ASSISTANCE"
    PERSONAL_DOSE_CHANGE_CONFIRMATION_REQUIRED = "PERSONAL_DOSE_CHANGE_CONFIRMATION_REQUIRED"
    POSSIBLE_OVERDOSE = "POSSIBLE_OVERDOSE"


class MedicationAnswerPayload(BaseModel):
    """LLM 답변 정제 단계의 제한된 구조화 출력."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)


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


class MedicationEvidenceCoverage(BaseModel):
    """질문에서 요청한 답변 항목과 실제 근거의 결정론적 대응 결과."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_section_types: list[KnowledgeSectionType] = Field(
        default_factory=list,
    )
    covered_section_types: list[KnowledgeSectionType] = Field(
        default_factory=list,
    )
    missing_section_types: list[KnowledgeSectionType] = Field(
        default_factory=list,
    )
    verified_interaction_pair_keys: list[str] = Field(default_factory=list)


class MedicationChatRequest(BaseModel):
    request_id: UUID
    user_id: int = Field(ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    question: str = Field(
        min_length=1,
        max_length=CHAT_CONTENT_MAX_LENGTH,
    )
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)
    session_reference: MedicationChatSessionReference = Field(
        default_factory=MedicationChatSessionReference,
    )
    risk_profile: MedicationChatRiskProfile = Field(default_factory=MedicationChatRiskProfile)

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
    scheduled_slots: list[str] = Field(default_factory=list)


class ActiveSupplement(BaseModel):
    registration_id: int = Field(ge=1)
    supplement_nutrient_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    dose_amount: str
    dose_unit: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    note: str | None = None
    scheduled_slots: list[str] = Field(default_factory=list)


class ActiveIntakeContext(BaseModel):
    user_id: int = Field(ge=1)
    preferred_care_episode_id: int | None = Field(default=None, ge=1)
    medications: list[ActiveMedication] = Field(default_factory=list)
    supplements: list[ActiveSupplement] = Field(default_factory=list)


class TherapeuticClassSelectionStatus(StrEnum):
    """등록 복약정보에서 치료군을 찾은 결과 상태."""

    NOT_REQUESTED = "NOT_REQUESTED"
    MATCHED = "MATCHED"
    NO_MATCHING_CLASS = "NO_MATCHING_CLASS"
    NO_APPROVED_ACTIVE_MEDICATION = "NO_APPROVED_ACTIVE_MEDICATION"


class TherapeuticClassSelection(BaseModel):
    """질문 표현과 검수된 치료군으로 선택된 활성 의약품 식별자."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: TherapeuticClassSelectionStatus
    class_codes: list[str] = Field(default_factory=list)
    medication_ids: list[int] = Field(default_factory=list)

    @property
    def requested(self) -> bool:
        return self.status != TherapeuticClassSelectionStatus.NOT_REQUESTED


class SupplementRegistrationIngredient(BaseModel):
    """등록 전 영양제의 성분·함량. 빈 값은 검증 불가 상태로 보존한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    amount: Decimal | None = Field(default=None, ge=0)
    unit: str | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SupplementRegistrationTotalAmount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    amount: Decimal = Field(ge=0)
    unit: str = Field(min_length=1)


class SupplementRegistrationSafetyInput(BaseModel):
    """등록 화면/API가 결정론적 사전 점검에 제공할 최소 입력 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    proposed_ingredients: list[SupplementRegistrationIngredient] = Field(min_length=1)
    existing_ingredients: list[SupplementRegistrationIngredient] = Field(default_factory=list)
    approved_rules: list["InteractionRuleFact"] = Field(default_factory=list)
    risk_profile: MedicationChatRiskProfile = Field(default_factory=MedicationChatRiskProfile)


class SupplementRegistrationSafetyResult(BaseModel):
    """LLM 설명 이전에 확정되는 등록 안전성 판단 결과."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SupplementRegistrationSafetyStatus
    duplicate_ingredient_names: list[str] = Field(default_factory=list)
    total_amounts: list[SupplementRegistrationTotalAmount] = Field(default_factory=list)
    matched_rule_ids: list[int] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


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
    question_interpretation: MedicationQuestionInterpretation | None = Field(
        default=None,
        exclude=True,
    )
    search_observation: MedicationSearchExecutionObservation | None = Field(
        default=None,
        exclude=True,
    )
    evidence_coverage: MedicationEvidenceCoverage | None = Field(
        default=None,
        exclude=True,
    )
    risk_decision: MedicationChatRiskDecision | None = Field(
        default=None,
        exclude=True,
    )
    official_warning_texts: list[str] = Field(
        default_factory=list,
        exclude=True,
    )


class GroundedClaimValidationDiagnostic(BaseModel):
    """안전성 검증의 Trace 전용 비식별 관측값."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_code: str | None = None
    matched_action: str | None = None
    matched_target: str | None = None
    matched_fragment_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    official_warning_allowed: bool = False
    disclaimer_added: bool = False

    def trace_outputs(self) -> dict[str, str | bool]:
        outputs: dict[str, str | bool] = {}
        for field_name in (
            "rule_code",
            "matched_action",
            "matched_target",
            "matched_fragment_hash",
        ):
            value = getattr(self, field_name)
            if value is not None:
                outputs[f"matched_{field_name}" if field_name == "rule_code" else field_name] = value
        if self.disclaimer_added:
            outputs["disclaimer_added"] = True
        if self.official_warning_allowed:
            outputs["official_warning_allowed"] = True
        return outputs


class MedicationAnswerGenerationObservation(BaseModel):
    status: MedicationAnswerRewriteStatus
    fallback_used: bool
    fallback_reason: MedicationAnswerFallbackReason | None = None
    declared_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
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
