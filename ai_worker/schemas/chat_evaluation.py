from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    MedicationChatRoute,
    MedicationChatSourceKind,
)


class ChatEvaluationCategory(StrEnum):
    RDB_ONLY = "RDB_ONLY"
    VECTOR_ONLY = "VECTOR_ONLY"
    RDB_AND_VECTOR = "RDB_AND_VECTOR"


class ChatEvaluationFailureCategory(StrEnum):
    QUESTION_CLASSIFICATION = "QUESTION_CLASSIFICATION"
    ENTITY_NORMALIZATION = "ENTITY_NORMALIZATION"
    SOURCE_RETRIEVAL = "SOURCE_RETRIEVAL"
    SAFETY_VALIDATION = "SAFETY_VALIDATION"
    PERFORMANCE = "PERFORMANCE"
    OBSERVABILITY = "OBSERVABILITY"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class ChatExpectedEntity(BaseModel):
    entity_type: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    surface: str | None = None


class ChatEvaluationExpected(BaseModel):
    route: MedicationChatRoute
    intent_tags: list[str] = Field(min_length=1)
    normalized_entities: list[ChatExpectedEntity] = Field(min_length=1)
    section_types: list[KnowledgeSectionType] = Field(min_length=1)
    required_source_kinds: list[MedicationChatSourceKind] = Field(min_length=1)
    safety_status: SafetyStatus = SafetyStatus.SAFE
    require_langsmith_trace: bool = True
    answer_requirements: list[str] = Field(min_length=1)
    forbidden_claims: list[str] = Field(min_length=1)


class ChatEvaluationCase(BaseModel):
    query_id: str = Field(min_length=1)
    category: ChatEvaluationCategory
    question: str = Field(min_length=1)
    preconditions: list[str] = Field(min_length=1)
    expected: ChatEvaluationExpected

    @field_validator("query_id", "question")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query_id와 question은 비어 있을 수 없습니다.")
        return normalized


class ChatEvaluationManifest(BaseModel):
    schema_version: str = "chat-evaluation-v1"
    dataset_version: str = Field(min_length=1)
    frontend_preset: bool = False
    description: str = ""
    usage_notes: list[str] = Field(default_factory=list)
    max_case_latency_ms: float = Field(default=30_000.0, gt=0.0)
    cases: list[ChatEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "ChatEvaluationManifest":
        if self.frontend_preset:
            raise ValueError("Chat 평가 질문은 프론트 프리셋으로 사용하지 않습니다.")
        query_ids = [case.query_id for case in self.cases]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("평가 query_id는 중복될 수 없습니다.")
        for case in self.cases:
            source_kinds = set(case.expected.required_source_kinds)
            has_vector = MedicationChatSourceKind.PUBLIC_KNOWLEDGE in source_kinds
            has_rdb = bool(source_kinds - {MedicationChatSourceKind.PUBLIC_KNOWLEDGE})
            if has_vector and has_rdb:
                expected_category = ChatEvaluationCategory.RDB_AND_VECTOR
            elif has_vector:
                expected_category = ChatEvaluationCategory.VECTOR_ONLY
            else:
                expected_category = ChatEvaluationCategory.RDB_ONLY
            if case.category != expected_category:
                raise ValueError("category와 required_source_kinds의 데이터 경로가 일치해야 합니다.")
        return self


class ChatEvaluationObservation(BaseModel):
    query_id: str = Field(min_length=1)
    route: MedicationChatRoute | None = None
    normalized_entities: list[str] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    source_kinds: list[MedicationChatSourceKind] = Field(default_factory=list)
    safety_status: SafetyStatus | None = None
    response_time_ms: float = Field(ge=0.0)
    langsmith_trace_id: str | None = None
    query_plan_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    execution_plan_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    answer: str = ""
    error_code: str | None = None


class ChatEvaluationCaseResult(BaseModel):
    query_id: str
    question: str
    category: ChatEvaluationCategory
    expected_route: MedicationChatRoute
    observed_route: MedicationChatRoute | None
    expected_entities: list[str]
    observed_entities: list[str]
    expected_section_types: list[KnowledgeSectionType]
    observed_section_types: list[KnowledgeSectionType]
    required_source_kinds: list[MedicationChatSourceKind]
    observed_source_kinds: list[MedicationChatSourceKind]
    expected_safety_status: SafetyStatus
    observed_safety_status: SafetyStatus | None
    response_time_ms: float
    langsmith_trace_id: str | None
    error_code: str | None
    answer: str
    route_match: bool
    entity_match: bool
    section_match: bool
    source_match: bool
    safety_match: bool
    latency_match: bool
    trace_match: bool
    failure_categories: list[ChatEvaluationFailureCategory]
    failure_details: list[str]
    passed: bool


class ChatEvaluationReport(BaseModel):
    schema_version: str = "chat-evaluation-report-v1"
    dataset_version: str
    query_count: int = Field(ge=1)
    passed_count: int = Field(ge=0)
    route_accuracy: float = Field(ge=0.0, le=1.0)
    entity_accuracy: float = Field(ge=0.0, le=1.0)
    section_accuracy: float = Field(ge=0.0, le=1.0)
    source_contract_rate: float = Field(ge=0.0, le=1.0)
    safety_contract_rate: float = Field(ge=0.0, le=1.0)
    langsmith_trace_coverage: float = Field(ge=0.0, le=1.0)
    timeout_rate: float = Field(ge=0.0, le=1.0)
    response_p50_ms: float = Field(ge=0.0)
    response_p95_ms: float = Field(ge=0.0)
    failure_counts: dict[ChatEvaluationFailureCategory, int]
    passed: bool
    results: list[ChatEvaluationCaseResult]
