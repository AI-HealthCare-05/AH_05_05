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

MEDICATION_QUESTION_INTERPRETATION_VERSION = "medication-question-interpretation-v1"


class MedicationQueryEntityType(StrEnum):
    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND_ALIAS = "BRAND_ALIAS"
    INGREDIENT_NAME = "INGREDIENT_NAME"
    INGREDIENT_FAMILY = "INGREDIENT_FAMILY"
    FOOD_CATEGORY = "FOOD_CATEGORY"
    TOPIC = "TOPIC"


class MedicationQueryEntitySource(StrEnum):
    CATALOG = "CATALOG"
    ALIAS = "ALIAS"
    REGEX = "REGEX"
    RDBMS = "RDBMS"
    QDRANT = "QDRANT"
    PATIENT_CONTEXT = "PATIENT_CONTEXT"
    SESSION_MEMORY = "SESSION_MEMORY"


class MedicationQueryResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"


class MedicationQuestionScope(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    GREETING = "GREETING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MedicationExpressionResolutionStatus(StrEnum):
    UNCHANGED = "UNCHANGED"
    AUTO_CORRECTED = "AUTO_CORRECTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    UNRESOLVED = "UNRESOLVED"


class MedicationExpressionNormalizationStrategy(StrEnum):
    """Source-backed 표현 정규화가 선택한 안전한 해석 방법."""

    NONE = "NONE"
    EXACT = "EXACT"
    SPACING = "SPACING"
    LETTER_PRONUNCIATION = "LETTER_PRONUNCIATION"
    COMPATIBILITY_JAMO = "COMPATIBILITY_JAMO"
    EDIT_DISTANCE = "EDIT_DISTANCE"
    RELATION_CUE = "RELATION_CUE"


class MedicationRelationResolutionStatus(StrEnum):
    """병용·회피 관계 표현의 해석 상태."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNCHANGED = "UNCHANGED"
    AUTO_CORRECTED = "AUTO_CORRECTED"


class MedicationQuestionIntent(StrEnum):
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    SUPPLEMENT_GUIDE = "SUPPLEMENT_GUIDE"
    INTERACTION = "INTERACTION"
    GENERAL_GUIDANCE = "GENERAL_GUIDANCE"
    CLARIFICATION = "CLARIFICATION"
    GREETING = "GREETING"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MedicationQuestionConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MedicationQuestionReasonCode(StrEnum):
    QUESTION_RESOLUTION_UNAVAILABLE = "QUESTION_RESOLUTION_UNAVAILABLE"
    EXPRESSION_AUTO_CORRECTED = "EXPRESSION_AUTO_CORRECTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    ENTITY_IDENTIFIED = "ENTITY_IDENTIFIED"
    NO_ENTITY_IDENTIFIED = "NO_ENTITY_IDENTIFIED"
    INTERACTION_PAIR_IDENTIFIED = "INTERACTION_PAIR_IDENTIFIED"


class MedicationExpressionCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original: str = Field(min_length=1)
    replacement: str = Field(min_length=1)


class InteractionRuleLookupStatus(StrEnum):
    MATCHED = "MATCHED"
    NO_APPROVED_RULE = "NO_APPROVED_RULE"
    RULE_REPOSITORY_UNAVAILABLE = "RULE_REPOSITORY_UNAVAILABLE"


class MedicationQueryEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    surface: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    # 검수된 카탈로그에서 확인된 검색용 동의어다. 답변 대상·필터는
    # canonical_name으로 고정하고, 벡터 질의 표현에만 함께 사용한다.
    search_aliases: list[str] = Field(default_factory=list)
    # 상호작용 검색을 위해 성분으로 정규화하더라도, e약은요 제품 가이드를
    # 조회할 수 있도록 원래 검수된 제품명을 보존한다.
    product_lookup_name: str | None = None
    entity_type: MedicationQueryEntityType
    candidate_types: list[MedicationQueryEntityType] = Field(
        default_factory=list,
    )
    kind: InteractionEntityKind | None = None
    source: MedicationQueryEntitySource = MedicationQueryEntitySource.REGEX
    resolution_status: MedicationQueryResolutionStatus = MedicationQueryResolutionStatus.RESOLVED

    @field_validator("search_aliases")
    @classmethod
    def normalize_search_aliases(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("product_lookup_name")
    @classmethod
    def normalize_product_lookup_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class MedicationCatalogEntry(BaseModel):
    """DB·Qdrant·등록 복용정보에서 확인된 질문 해석 대상."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    entity_type: MedicationQueryEntityType
    kind: InteractionEntityKind | None = None
    source: MedicationQueryEntitySource

    @field_validator("canonical_name")
    @classmethod
    def strip_canonical_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("카탈로그 정식명은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(alias.strip() for alias in values if alias.strip()))

    @property
    def expressions(self) -> list[str]:
        return list(dict.fromkeys([self.canonical_name, *self.aliases]))


class MedicationQuestionResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    original_question: str = Field(min_length=1)
    resolved_question: str = Field(min_length=1)
    scope: MedicationQuestionScope
    status: MedicationExpressionResolutionStatus
    corrections: list[MedicationExpressionCorrection] = Field(
        default_factory=list,
    )
    candidate_names: list[str] = Field(default_factory=list)
    # True이면 resolver가 실제 카탈로그를 조회했으므로 빈 entities도
    # "인식 대상 없음"이라는 의미다. False는 하위 호환용 미해석 입력이다.
    entity_resolution_available: bool = False
    entities: list[MedicationQueryEntity] = Field(default_factory=list)
    normalization_strategy: MedicationExpressionNormalizationStrategy = MedicationExpressionNormalizationStrategy.NONE
    confidence_tier: MedicationQuestionConfidence = MedicationQuestionConfidence.LOW
    shortlisted_candidate_count: int = Field(default=0, ge=0)
    tie_count: int = Field(default=0, ge=0)
    relation_resolution_status: MedicationRelationResolutionStatus = MedicationRelationResolutionStatus.NOT_APPLICABLE
    # 질문 본문이나 제품명을 남기지 않고, 해석에 사용 가능한 어휘의 출처·유형
    # 분포만 LangSmith 진단용으로 기록한다.
    catalog_source_counts: dict[str, int] = Field(default_factory=dict)
    catalog_type_counts: dict[str, int] = Field(default_factory=dict)


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


class SupplementIngredientFamily(BaseModel):
    """사용자가 통칭으로 질문하는 영양성분군과 세부 선택지 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_name: str = Field(min_length=1)
    member_names: list[str] = Field(min_length=1)
    search_names: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)


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
    ingredient_family: SupplementIngredientFamily | None = None
    interaction_pairs: list[MedicationInteractionQueryPair] = Field(
        default_factory=list,
    )
    interaction_types: list[InteractionPairType] = Field(default_factory=list)
    interaction_pair_keys: list[str] = Field(default_factory=list)
    medication_product_lookup_names: list[str] = Field(default_factory=list)
    has_medication_product_cue: bool = False

    @field_validator("medication_product_lookup_names")
    @classmethod
    def normalize_medication_product_lookup_names(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = value.strip()
            key = candidate.casefold()
            if candidate and key not in seen:
                normalized.append(candidate)
                seen.add(key)
        return normalized

    @property
    def query_plan_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MedicationQuestionInterpretation(BaseModel):
    """자유 형식 CoT 없이 질문 해석 결과를 설명하는 통합 계약."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation_version: str = Field(
        default=MEDICATION_QUESTION_INTERPRETATION_VERSION,
        min_length=1,
    )
    original_question: str = Field(min_length=1)
    resolved_question: str = Field(min_length=1)
    scope: MedicationQuestionScope
    resolution_status: MedicationExpressionResolutionStatus
    intent: MedicationQuestionIntent
    confidence: MedicationQuestionConfidence
    normalized_entity_names: list[str] = Field(default_factory=list)
    normalized_entities: list[MedicationQueryEntity] = Field(
        default_factory=list,
    )
    requested_section_types: list[KnowledgeSectionType] = Field(
        default_factory=list,
    )
    interaction_types: list[InteractionPairType] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    correction_count: int = Field(default=0, ge=0)
    candidate_count: int = Field(default=0, ge=0)
    reason_codes: list[MedicationQuestionReasonCode] = Field(
        default_factory=list,
    )
    query_plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("clarification_question")
    @classmethod
    def normalize_clarification_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


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
                and entity.entity_type != MedicationQueryEntityType.INGREDIENT_FAMILY
            ],
            [
                *(
                    self.query_plan.ingredient_family.search_names
                    if self.query_plan.ingredient_family is not None
                    else []
                ),
                *(self.patient_supplement_names if self.include_patient_context else []),
            ],
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
