from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.interaction import InteractionEntityKind, InteractionPairType
from ai_worker.schemas.knowledge import KnowledgeSearchMode, KnowledgeSectionType
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQuestionScope,
)

REQUIRED_METRIC_RATIONALE_KEYS = frozenset(
    {
        "recall_at_20",
        "hit_at_5",
        "mrr",
        "source_accuracy",
        "evidence_coverage_rate",
        "wrong_target_mixing_count",
        "duplicate_retrieval_rate",
        "search_p95_ms",
    }
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


class MedicationEvaluationEvidenceKind(StrEnum):
    RDBMS_GUIDE = "RDBMS_GUIDE"
    QDRANT_GOLD = "QDRANT_GOLD"
    NO_EVIDENCE = "NO_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MedicationEvaluationPhase(StrEnum):
    """이번 변경의 차단 기준에 포함되는 질문 범위를 구분한다."""

    ACTIVE_PHASE = "ACTIVE_PHASE"
    DEFERRED_MEMORY = "DEFERRED_MEMORY"
    DEFERRED_CONTEXT = "DEFERRED_CONTEXT"
    DEFERRED_SAFETY = "DEFERRED_SAFETY"


class MedicationHistoricalOutcome(StrEnum):
    """코드 변경 전 프론트·LangSmith 관측의 판정값이다."""

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class MedicationExpectedEntity(BaseModel):
    """고정 평가에서 기대하는 정식명·타입·kind·출처 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_name: str = Field(min_length=1)
    entity_type: MedicationQueryEntityType
    kind: InteractionEntityKind
    expected_sources: list[MedicationQueryEntitySource] = Field(min_length=1)

    @field_validator("canonical_name")
    @classmethod
    def normalize_canonical_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("기대 엔터티 정식명은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("expected_sources")
    @classmethod
    def normalize_sources(
        cls,
        values: list[MedicationQueryEntitySource],
    ) -> list[MedicationQueryEntitySource]:
        return list(dict.fromkeys(values))


class MedicationSearchBaselineCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    expression_category: MedicationExpressionCategory = MedicationExpressionCategory.COMMON_NAME
    question: str = Field(min_length=1)
    expected_scope: MedicationQuestionScope
    expected_resolution_status: MedicationExpressionResolutionStatus
    phase: MedicationEvaluationPhase = MedicationEvaluationPhase.ACTIVE_PHASE
    expected_resolved_question: str | None = None
    expected_entity_names: list[str] = Field(default_factory=list)
    expected_entities: list[MedicationExpectedEntity] = Field(default_factory=list)
    expected_interaction_types: list[InteractionPairType] = Field(default_factory=list)
    expected_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    expected_document_ids: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    expect_no_evidence: bool = False
    expect_no_entity: bool = False
    expect_no_guide_lookup: bool = False
    expect_no_rag: bool = False
    evidence_kind: MedicationEvaluationEvidenceKind | None = None
    evaluation_rationale: str | None = None
    historical_outcome: MedicationHistoricalOutcome | None = None
    gold_document_rationales: dict[str, str] = Field(default_factory=dict)

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

    @field_validator("evaluation_rationale")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("gold_document_rationales")
    @classmethod
    def normalize_document_rationales(
        cls,
        values: dict[str, str],
    ) -> dict[str, str]:
        return {
            document_id.strip(): rationale.strip()
            for document_id, rationale in values.items()
            if document_id.strip() and rationale.strip()
        }

    @model_validator(mode="after")
    def require_consistent_evidence_expectation(self):
        if self.expect_no_evidence and self.expected_document_ids:
            raise ValueError("expect_no_evidence와 expected_document_ids는 함께 지정할 수 없습니다.")
        if self.expect_no_entity and (self.expected_entity_names or self.expected_entities):
            raise ValueError("expect_no_entity에는 기대 엔터티를 지정할 수 없습니다.")
        if self.expected_entities and {entity.canonical_name for entity in self.expected_entities} != set(
            self.expected_entity_names
        ):
            raise ValueError("expected_entities와 expected_entity_names는 같은 정식명을 가져야 합니다.")
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
    experiment_goal: str | None = None
    activation_rule: str | None = None
    baseline_observed_at: str | None = None
    baseline_environment: str | None = None
    trace_reference_policy: str | None = None
    metric_rationales: dict[str, str] = Field(default_factory=dict)
    cases: list[MedicationSearchBaselineCase] = Field(min_length=1)

    @field_validator(
        "experiment_goal",
        "activation_rule",
        "baseline_observed_at",
        "baseline_environment",
        "trace_reference_policy",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("metric_rationales")
    @classmethod
    def normalize_metric_rationales(
        cls,
        values: dict[str, str],
    ) -> dict[str, str]:
        return {
            name.strip(): rationale.strip() for name, rationale in values.items() if name.strip() and rationale.strip()
        }

    @model_validator(mode="after")
    def validate_contract(self) -> "MedicationSearchBaselineManifest":
        if self.frontend_preset:
            raise ValueError("검색 평가 질문은 프론트 프리셋으로 사용하지 않습니다.")
        if self.candidate_top_k < self.final_top_k:
            raise ValueError("candidate_top_k는 final_top_k보다 작을 수 없습니다.")
        query_ids = [case.query_id for case in self.cases]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("평가 query_id는 중복될 수 없습니다.")
        if self.schema_version in {
            "medication-search-baseline-v2",
            "medication-search-baseline-v3",
        }:
            self._validate_v2_contract()
        if self.schema_version == "medication-search-baseline-v3":
            self._validate_v3_contract()
        return self

    def _validate_v2_contract(self) -> None:
        if not self.experiment_goal:
            raise ValueError("v2 평가에는 실험 목적이 필요합니다.")
        if not self.activation_rule:
            raise ValueError("v2 평가에는 검색 방식 채택 기준이 필요합니다.")
        missing_metrics = REQUIRED_METRIC_RATIONALE_KEYS.difference(self.metric_rationales)
        if missing_metrics:
            raise ValueError("v2 평가에는 모든 지표 선정 근거가 필요합니다: " + ", ".join(sorted(missing_metrics)))
        for case in self.cases:
            if case.evidence_kind is None or not case.evaluation_rationale:
                raise ValueError(f"{case.query_id}: 근거 유형과 질문별 실험 근거가 필요합니다.")
            expected_documents = set(case.expected_document_ids)
            explained_documents = set(case.gold_document_rationales)
            if case.evidence_kind == MedicationEvaluationEvidenceKind.QDRANT_GOLD:
                if not expected_documents or expected_documents != explained_documents:
                    raise ValueError(f"{case.query_id}: 모든 정답 문서에 골드 문서 선정 근거가 필요합니다.")
            elif expected_documents or explained_documents:
                raise ValueError(f"{case.query_id}: QDRANT_GOLD가 아닌 항목에는 정답 문서 ID를 지정할 수 없습니다.")

    def _validate_v3_contract(self) -> None:
        if not self.baseline_observed_at or not self.baseline_environment:
            raise ValueError("v3 평가에는 기준선 관측 시점과 환경이 필요합니다.")
        for case in self.cases:
            if case.historical_outcome is None:
                raise ValueError(f"{case.query_id}: v3 평가에는 변경 전 판정이 필요합니다.")
            if case.expected_entity_names and not case.expected_entities:
                raise ValueError(
                    f"{case.query_id}: v3 평가의 활성 엔터티에는 type·kind·source 계약이 필요합니다.",
                )
            if case.expected_interaction_types and len(case.expected_entities) < 2:
                raise ValueError(
                    f"{case.query_id}: v3 평가의 상호작용 pair에는 두 개 이상의 typed entity가 필요합니다.",
                )
            if case.expect_no_rag and case.expected_document_ids:
                raise ValueError(
                    f"{case.query_id}: expect_no_rag에는 정답 문서 ID를 지정할 수 없습니다.",
                )


class MedicationSearchBaselineCaseResult(BaseModel):
    query_id: str
    expression_category: MedicationExpressionCategory
    phase: MedicationEvaluationPhase = MedicationEvaluationPhase.ACTIVE_PHASE
    historical_outcome: MedicationHistoricalOutcome | None = None
    evidence_kind: MedicationEvaluationEvidenceKind | None = None
    evaluation_rationale: str | None = None
    expected_document_ids: list[str] = Field(default_factory=list)
    gold_document_rationales: dict[str, str] = Field(default_factory=dict)
    observed_scope: MedicationQuestionScope
    observed_resolution_status: MedicationExpressionResolutionStatus
    observed_resolved_question: str
    observed_entity_names: list[str] = Field(default_factory=list)
    observed_entities: list[MedicationExpectedEntity] = Field(default_factory=list)
    observed_interaction_types: list[InteractionPairType] = Field(default_factory=list)
    observed_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    retrieval_executed: bool
    guide_lookup_eligible: bool = False
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
    experiment_goal: str | None = None
    activation_rule: str | None = None
    baseline_observed_at: str | None = None
    baseline_environment: str | None = None
    trace_reference_policy: str | None = None
    metric_rationales: dict[str, str] = Field(default_factory=dict)
    embedding_model_name: str | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    vector_distance: str = "COSINE"
    embedding_vectors_normalized: bool = False
    min_similarity_score: float = Field(ge=0.0, le=1.0)
    final_top_k: int = Field(ge=1)
    candidate_top_k: int = Field(ge=1)
    git_commit: str
    working_tree_dirty: bool
    evaluation_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    query_count: int = Field(ge=1)
    active_query_count: int = Field(ge=0)
    active_pass_count: int = Field(ge=0)
    active_pass_rate: float = Field(ge=0.0, le=1.0)
    deferred_query_count: int = Field(ge=0)
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


class RerankerEvaluationEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    ALREADY_IN_TOP_5 = "ALREADY_IN_TOP_5"
    GOLD_NOT_IN_TOP_30 = "GOLD_NOT_IN_TOP_30"


class RerankerActivationDecision(StrEnum):
    """평가 결과일 뿐, 이 값만으로 런타임 경로를 활성화하지 않는다."""

    KEEP_RUNTIME_DISABLED = "KEEP_RUNTIME_DISABLED"
    ELIGIBLE_FOR_CONTROLLED_ACTIVATION = "ELIGIBLE_FOR_CONTROLLED_ACTIVATION"


class RerankerEvaluationCandidate(BaseModel):
    """Top 30 검색 후보와 오프라인 reranker 점수 관측값이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    wrong_target: bool = False
    reranker_score: float | None = None

    @field_validator("document_id")
    @classmethod
    def normalize_document_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reranker 후보 document_id는 비어 있을 수 없습니다.")
        return normalized


class RerankerEvaluationCase(BaseModel):
    """정답 문서가 Top 30 안에 있는지 확인할 수 있는 A/B 평가 입력이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_document_ids: list[str] = Field(min_length=1)
    baseline_candidates: list[RerankerEvaluationCandidate] = Field(min_length=1, max_length=30)
    search_latency_ms: float = Field(ge=0.0)
    reranker_latency_ms: float = Field(ge=0.0)

    @field_validator("query_id", "question")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("reranker 평가 query_id와 question은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("expected_document_ids")
    @classmethod
    def normalize_expected_document_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not normalized:
            raise ValueError("reranker 평가에는 정답 문서 ID가 하나 이상 필요합니다.")
        return normalized

    @model_validator(mode="after")
    def require_unique_baseline_document_ids(self) -> "RerankerEvaluationCase":
        document_ids = [candidate.document_id for candidate in self.baseline_candidates]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("reranker 평가 후보의 document_id는 중복될 수 없습니다.")
        return self


class RerankerEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_count: int = Field(ge=1)
    hit_at_5: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    source_precision: float = Field(ge=0.0, le=1.0)
    wrong_target_mixing_rate: float = Field(ge=0.0, le=1.0)
    search_p95_ms: float = Field(ge=0.0)


class RerankerEvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    eligibility: RerankerEvaluationEligibility
    baseline_first_relevant_rank: int | None = Field(default=None, ge=1)
    reranked_first_relevant_rank: int | None = Field(default=None, ge=1)
    baseline_hit_at_5: bool | None = None
    reranked_hit_at_5: bool | None = None
    baseline_reciprocal_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    reranked_reciprocal_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_wrong_target_mixing_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    reranked_wrong_target_mixing_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    baseline_search_latency_ms: float = Field(ge=0.0)
    reranked_search_latency_ms: float = Field(ge=0.0)


class RerankerABReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "reranker-ab-evaluation-v1"
    final_top_k: int = Field(default=5, ge=1)
    candidate_top_k: int = Field(default=30, ge=1)
    max_p95_increase_ms: float = Field(ge=0.0)
    eligible_query_count: int = Field(ge=0)
    excluded_query_count: int = Field(ge=0)
    baseline: RerankerEvaluationMetrics | None = None
    reranked: RerankerEvaluationMetrics | None = None
    decision: RerankerActivationDecision
    blocking_reasons: list[str] = Field(default_factory=list)
    results: list[RerankerEvaluationCaseResult]
