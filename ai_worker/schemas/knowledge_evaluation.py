from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeSectionType,
    normalize_interaction_pair_keys,
)


class KnowledgeEvaluationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_hit_at_5: float = Field(default=0.90, ge=0.0, le=1.0)
    min_citation_accuracy: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
    )
    max_wrong_entity_mixing_count: int = Field(default=0, ge=0)
    max_search_p95_ms: float = Field(default=300.0, gt=0.0)


class KnowledgeEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_document_ids: list[str] = Field(min_length=1)
    expected_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    expected_drug_names: list[str] = Field(default_factory=list)
    expected_ingredient_names: list[str] = Field(default_factory=list)
    expected_interaction_pair_keys: list[str] = Field(default_factory=list)
    forbidden_document_ids: list[str] = Field(default_factory=list)
    forbidden_drug_names: list[str] = Field(default_factory=list)
    forbidden_ingredient_names: list[str] = Field(default_factory=list)
    document_types: list[KnowledgeDocumentType] = Field(default_factory=list)
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    interaction_type: str | None = None
    interaction_pair_keys: list[str] = Field(default_factory=list)
    special_populations: list[str] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=50)

    @field_validator("query_id", "query")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query_id와 query는 비어 있을 수 없습니다.")
        return normalized

    @field_validator(
        "expected_document_ids",
        "expected_drug_names",
        "expected_ingredient_names",
        "forbidden_document_ids",
        "forbidden_drug_names",
        "forbidden_ingredient_names",
        "drug_names",
        "ingredient_names",
        "special_populations",
    )
    @classmethod
    def normalize_unique_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = value.strip()
            if item and item not in seen:
                normalized.append(item)
                seen.add(item)
        return normalized

    @field_validator(
        "expected_interaction_pair_keys",
        "interaction_pair_keys",
    )
    @classmethod
    def normalize_pair_keys(cls, values: list[str]) -> list[str]:
        return normalize_interaction_pair_keys(values)


class KnowledgeEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "knowledge-retrieval-evaluation-v1"
    dataset_version: str = Field(min_length=1)
    thresholds: KnowledgeEvaluationThresholds = Field(default_factory=KnowledgeEvaluationThresholds)
    cases: list[KnowledgeEvaluationCase] = Field(min_length=1)

    @field_validator("dataset_version")
    @classmethod
    def normalize_dataset_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("dataset_version은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def require_unique_query_ids(self) -> Self:
        query_ids = [case.query_id for case in self.cases]
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("평가 cases의 query_id는 중복될 수 없습니다.")
        return self


class KnowledgeQueryEvaluationResult(BaseModel):
    query_id: str
    retrieved_document_ids: list[str]
    hit_at_5: bool
    reciprocal_rank: float = Field(ge=0.0, le=1.0)
    relevant_count: int = Field(ge=0)
    retrieved_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    wrong_entity_mixing_count: int = Field(ge=0)
    search_latency_ms: float = Field(ge=0.0)


class KnowledgeEvaluationReport(BaseModel):
    schema_version: str = "knowledge-retrieval-report-v1"
    dataset_version: str
    collection_name: str
    query_count: int = Field(ge=1)
    hit_at_5: float = Field(ge=0.0, le=1.0)
    mrr: float = Field(ge=0.0, le=1.0)
    citation_accuracy: float = Field(ge=0.0, le=1.0)
    duplicate_retrieval_rate: float = Field(ge=0.0, le=1.0)
    wrong_entity_mixing_count: int = Field(ge=0)
    search_p95_ms: float = Field(ge=0.0)
    evaluation_contract_hash: str | None = None
    accuracy_passed: bool | None = None
    latency_passed: bool | None = None
    passed: bool
    query_results: list[KnowledgeQueryEvaluationResult]


class KnowledgeReleaseDecision(StrEnum):
    ACTIVATE = "ACTIVATE"
    KEEP_BASELINE = "KEEP_BASELINE"


class KnowledgeReleaseComparisonReport(BaseModel):
    schema_version: str = "knowledge-release-comparison-v1"
    baseline_dataset_version: str
    baseline_collection_name: str
    candidate_dataset_version: str
    candidate_collection_name: str
    decision: KnowledgeReleaseDecision
    accuracy_improved: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warning_reasons: list[str] = Field(default_factory=list)
    metric_deltas: dict[str, float] = Field(default_factory=dict)
