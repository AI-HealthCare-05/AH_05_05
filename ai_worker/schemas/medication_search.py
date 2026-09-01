import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeSectionType,
)


class MedicationQueryEntityType(StrEnum):
    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND_ALIAS = "BRAND_ALIAS"
    INGREDIENT_NAME = "INGREDIENT_NAME"
    FOOD_CATEGORY = "FOOD_CATEGORY"
    TOPIC = "TOPIC"


class MedicationQueryEntitySource(StrEnum):
    CATALOG = "CATALOG"
    ALIAS = "ALIAS"
    REGEX = "REGEX"


class MedicationQueryResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class InteractionRuleLookupStatus(StrEnum):
    MATCHED = "MATCHED"
    NO_APPROVED_RULE = "NO_APPROVED_RULE"
    RULE_REPOSITORY_UNAVAILABLE = "RULE_REPOSITORY_UNAVAILABLE"


class MedicationQueryEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    entity_type: MedicationQueryEntityType
    candidate_types: list[MedicationQueryEntityType] = Field(
        default_factory=list,
    )
    kind: InteractionEntityKind | None = None
    source: MedicationQueryEntitySource = MedicationQueryEntitySource.REGEX
    resolution_status: MedicationQueryResolutionStatus = MedicationQueryResolutionStatus.RESOLVED


class MedicationInteractionQueryPair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    left_name: str = Field(min_length=1)
    right_name: str = Field(min_length=1)
    pair_type: InteractionPairType
    pair_key: str = Field(min_length=64, max_length=64)


class SupplementInteractionPair(BaseModel):
    """현재 코퍼스에서 검색 가능한 영양성분 조합의 어휘 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_names: tuple[str, str]
    alias_groups: tuple[tuple[str, ...], tuple[str, ...]]
    english_query: str = Field(min_length=1)

    @property
    def pair_key(self) -> str:
        left, right = (
            InteractionEntity(
                kind=InteractionEntityKind.SUPPLEMENT,
                display_name=name,
            )
            for name in self.canonical_names
        )
        return build_interaction_pair_key(left, right)


class MedicationKnowledgeQueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_query: str = Field(min_length=1)
    expanded_query: str = Field(min_length=1)
    entity_names: list[str] = Field(default_factory=list)
    entities: list[MedicationQueryEntity] = Field(default_factory=list)
    document_types: list[KnowledgeDocumentType] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    alternate_queries: list[str] = Field(default_factory=list)
    interaction_pair: SupplementInteractionPair | None = None
    interaction_pairs: list[MedicationInteractionQueryPair] = Field(
        default_factory=list,
    )
    interaction_types: list[InteractionPairType] = Field(default_factory=list)
    interaction_pair_keys: list[str] = Field(default_factory=list)
    has_medication_product_cue: bool = False

    @property
    def query_plan_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MedicationSearchExecutionPlan(BaseModel):
    """질문·환자 컨텍스트·승인 규칙을 출처별로 보존한 검색 실행 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_plan: MedicationKnowledgeQueryPlan
    patient_medication_names: list[str] = Field(default_factory=list)
    patient_supplement_names: list[str] = Field(default_factory=list)
    approved_rule_pair_keys: list[str] = Field(default_factory=list)
    approved_rule_status: InteractionRuleLookupStatus = InteractionRuleLookupStatus.NO_APPROVED_RULE
    include_patient_context: bool = False
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_rules_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator(
        "patient_medication_names",
        "patient_supplement_names",
        "approved_rule_pair_keys",
    )
    @classmethod
    def normalize_source_values(cls, values: list[str]) -> list[str]:
        normalized = {value.strip() for value in values if value.strip()}
        return sorted(normalized, key=str.casefold)

    @property
    def query_plan_hash(self) -> str:
        return self.query_plan.query_plan_hash

    @property
    def medication_names(self) -> list[str]:
        return self._merge_names(
            [entity.canonical_name for entity in self.query_plan.entities if entity.kind == InteractionEntityKind.DRUG],
            (self.patient_medication_names if self.include_patient_context else []),
        )

    @property
    def supplement_names(self) -> list[str]:
        return self._merge_names(
            [
                entity.canonical_name
                for entity in self.query_plan.entities
                if entity.kind == InteractionEntityKind.SUPPLEMENT
            ],
            (self.patient_supplement_names if self.include_patient_context else []),
        )

    @property
    def interaction_pair_keys(self) -> list[str]:
        return self._merge_names(
            self.query_plan.interaction_pair_keys,
            self.approved_rule_pair_keys,
        )

    @property
    def execution_plan_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _merge_names(primary: list[str], secondary: list[str]) -> list[str]:
        return list(dict.fromkeys([*primary, *secondary]))


class MedicationSearchExecutionObservation(BaseModel):
    """평가·추적용 비공개 검색 관측값."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_plan: MedicationKnowledgeQueryPlan
    query_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_execution_plan(
        cls,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> "MedicationSearchExecutionObservation":
        return cls(
            query_plan=execution_plan.query_plan,
            query_plan_hash=execution_plan.query_plan_hash,
            execution_plan_hash=execution_plan.execution_plan_hash,
        )
