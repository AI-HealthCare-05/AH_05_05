from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.knowledge import (
    KnowledgeSearchMode,
    KnowledgeSectionType,
)
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationQuestionScope,
)


class MedicationExpressionCategory(StrEnum):
    EXACT_PRODUCT = "EXACT_PRODUCT"
    PRODUCT_TYPO = "PRODUCT_TYPO"
    INGREDIENT_TYPO = "INGREDIENT_TYPO"
    KEYBOARD_TYPO = "KEYBOARD_TYPO"
    SPACING_VARIATION = "SPACING_VARIATION"
    COMMON_NAME = "COMMON_NAME"
    AMBIGUOUS = "AMBIGUOUS"
    SHORT_EXPRESSION = "SHORT_EXPRESSION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    IN_SCOPE_NO_EVIDENCE = "IN_SCOPE_NO_EVIDENCE"
    DRUG_DRUG = "DRUG_DRUG"
    DRUG_SUPPLEMENT = "DRUG_SUPPLEMENT"
    SUPPLEMENT_SUPPLEMENT = "SUPPLEMENT_SUPPLEMENT"
    DRUG_FOOD = "DRUG_FOOD"


class MedicationSearchBaselineCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    expression_category: MedicationExpressionCategory = MedicationExpressionCategory.COMMON_NAME
    question: str = Field(min_length=1)
    expected_scope: MedicationQuestionScope
    expected_resolution_status: MedicationExpressionResolutionStatus
    expected_resolved_question: str | None = None
    expected_entity_names: list[str] = Field(default_factory=list)
    expected_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    expect_no_evidence: bool = False

    @field_validator("query_id", "question")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query_id와 question은 비어 있을 수 없습니다.")
        return normalized

    @field_validator(
        "expected_entity_names",
        "expected_document_ids",
        "forbidden_document_ids",
    )
    @classmethod
    def normalize_unique_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def require_consistent_evidence_expectation(self):
        if self.expect_no_evidence and self.expected_document_ids:
            raise ValueError(
                "expect_no_evidence와 expected_document_ids는 함께 지정할 수 없습니다."
            )
        return self


class MedicationSearchBaselineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "medication-search-baseline-v1"
    dataset_version: str = Field(min_length=1)
    collection_name: str = Field(min_length=1)
    frontend_preset: bool = False
    min_similarity_score: float = Field(default=0.65, ge=0.0, le=1.0)
    final_top_k: Literal[5] = 5
    candidate_top_k: Literal[20] = 20
    cases: list[MedicationSearchBaselineCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "MedicationSearchBaselineManifest":
        if self.frontend_preset:
            raise ValueError("검색 평가 질문은 프론트 프리셋으로 사용하지 않습니다.")
        if self.candidate_top_k < self.final_top_k:
            raise ValueError("candidate_top_k는 final_top_k보다 작을 수 없습니다.")
        query_ids = [case.query_id for case in self.cases]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("평가 query_id는 중복될 수 없습니다.")
        return self


class MedicationSearchBaselineCaseResult(BaseModel):
    query_id: str
    expression_category: MedicationExpressionCategory
    observed_scope: MedicationQuestionScope
    observed_resolution_status: MedicationExpressionResolutionStatus
    observed_resolved_question: str
    observed_entity_names: list[str] = Field(default_factory=list)
    observed_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    retrieval_executed: bool
    attempted_search_tiers: list[str] = Field(default_factory=list)
    candidate_count: int = Field(ge=0)
    candidate_first_relevant_rank: int | None = Field(default=None, ge=1)
    selected_document_ids: list[str] = Field(default_factory=list)
    selected_chunk_ids: list[str] = Field(default_factory=list)
    hit_at_5: bool | None = None
    recall_at_20: bool | None = None
    reciprocal_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_coverage_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    fallback_used: bool = False
    search_latency_ms: float = Field(ge=0.0)
    failure_reasons: list[str] = Field(default_factory=list)
    passed: bool


class MedicationSearchBaselineReport(BaseModel):
    schema_version: str = "medication-search-baseline-report-v1"
    dataset_version: str
    collection_name: str
    search_mode: KnowledgeSearchMode = KnowledgeSearchMode.DENSE
    embedding_model_name: str | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    min_similarity_score: float = Field(ge=0.0, le=1.0)
    final_top_k: int = Field(ge=1)
    candidate_top_k: int = Field(ge=1)
    git_commit: str
    working_tree_dirty: bool
    evaluation_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_count: int = Field(ge=1)
    resolution_accuracy: float = Field(ge=0.0, le=1.0)
    scope_accuracy: float = Field(ge=0.0, le=1.0)
    correction_accuracy: float = Field(ge=0.0, le=1.0)
    false_correction_rate: float = Field(ge=0.0, le=1.0)
    ambiguity_accuracy: float = Field(ge=0.0, le=1.0)
    recall_at_20: float = Field(ge=0.0, le=1.0)
    hit_at_5: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    source_accuracy: float = Field(ge=0.0, le=1.0)
    evidence_coverage_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    wrong_target_mixing_count: int = Field(ge=0)
    duplicate_retrieval_rate: float = Field(ge=0.0, le=1.0)
    fallback_rate: float = Field(ge=0.0, le=1.0)
    search_p50_ms: float = Field(ge=0.0)
    search_p95_ms: float = Field(ge=0.0)
    passed: bool
    results: list[MedicationSearchBaselineCaseResult]


class MedicationSearchModeDecision(StrEnum):
    KEEP_DENSE = "KEEP_DENSE"
    ACTIVATE_HYBRID = "ACTIVATE_HYBRID"


class MedicationSearchModeComparisonReport(BaseModel):
    dense_collection_name: str
    bm25_collection_name: str
    hybrid_collection_name: str
    decision: MedicationSearchModeDecision
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    metric_deltas: dict[str, float] = Field(default_factory=dict)
