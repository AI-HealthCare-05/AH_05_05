from typing import Any, Protocol

from langchain_core.runnables import RunnableConfig, RunnableLambda
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQuestionConfidence,
    MedicationQuestionIntent,
    MedicationQuestionInterpretation,
    MedicationQuestionReasonCode,
    MedicationQuestionResolution,
    MedicationQuestionScope,
)


class MedicationQueryPlanChainInput(BaseModel):
    """결정론적 질문 분류·검색 계획 체인이 받는 구조화 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    supplement_names: list[str] = Field(default_factory=list)
    resolution: MedicationQuestionResolution | None = None
    allow_legacy_entity_inference: bool = False

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("supplement_names")
    @classmethod
    def normalize_supplement_names(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _validate_query_input(
    value: MedicationQueryPlanChainInput | dict[str, Any],
) -> MedicationQueryPlanChainInput:
    if isinstance(value, MedicationQueryPlanChainInput):
        return value
    return MedicationQueryPlanChainInput.model_validate(value)


def _build_query_plan(
    value: MedicationQueryPlanChainInput,
) -> "MedicationQuestionPlanResult":
    if value.resolution is not None and value.resolution.entity_resolution_available:
        catalog_entities: list[MedicationQueryEntity] | None = value.resolution.entities
    elif value.allow_legacy_entity_inference:
        catalog_entities = None
    else:
        catalog_entities = _supplement_catalog_entities(value)
    query_plan = MedicationKnowledgeQueryBuilder(
        supplement_names=value.supplement_names,
        catalog_entities=catalog_entities,
    ).build(value.question)
    return MedicationQuestionPlanResult(
        interpretation=_build_interpretation(
            value=value,
            query_plan=query_plan,
        ),
        query_plan=query_plan,
    )


def _supplement_catalog_entities(
    value: MedicationQueryPlanChainInput,
) -> list[MedicationQueryEntity]:
    """Resolver를 사용할 수 없는 경우에도 동적 영양성분 카탈로그만 사용한다."""
    normalized_question = "".join(value.question.casefold().split())
    return [
        MedicationQueryEntity(
            surface=name,
            canonical_name=name,
            entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
            kind=InteractionEntityKind.SUPPLEMENT,
            source=MedicationQueryEntitySource.CATALOG,
        )
        for name in value.supplement_names
        if "".join(name.casefold().split()) in normalized_question
    ]


class MedicationQuestionPlanResult(BaseModel):
    """질문 해석 결과와 실제 검색 계획을 함께 보존한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    interpretation: MedicationQuestionInterpretation
    query_plan: MedicationKnowledgeQueryPlan


class MedicationQueryPlanChain(Protocol):
    async def ainvoke(
        self,
        input: MedicationQueryPlanChainInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> MedicationQuestionPlanResult | dict[str, Any]: ...


def _build_interpretation(
    *,
    value: MedicationQueryPlanChainInput,
    query_plan: MedicationKnowledgeQueryPlan,
) -> MedicationQuestionInterpretation:
    resolution = value.resolution
    scope = resolution.scope if resolution is not None else MedicationQuestionScope.IN_SCOPE
    resolution_status = resolution.status if resolution is not None else MedicationExpressionResolutionStatus.UNRESOLVED
    intent = _question_intent(
        scope=scope,
        resolution_status=resolution_status,
        query_plan=query_plan,
    )
    confidence = _question_confidence(
        scope=scope,
        resolution_available=resolution is not None,
        resolution_status=resolution_status,
        query_plan=query_plan,
    )
    reason_codes: list[MedicationQuestionReasonCode] = []
    if resolution is None:
        reason_codes.append(
            MedicationQuestionReasonCode.QUESTION_RESOLUTION_UNAVAILABLE,
        )
    elif resolution_status == MedicationExpressionResolutionStatus.AUTO_CORRECTED:
        reason_codes.append(
            MedicationQuestionReasonCode.EXPRESSION_AUTO_CORRECTED,
        )
    elif resolution_status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED:
        reason_codes.append(
            MedicationQuestionReasonCode.CLARIFICATION_REQUIRED,
        )
    if query_plan.entity_names:
        reason_codes.append(MedicationQuestionReasonCode.ENTITY_IDENTIFIED)
    else:
        reason_codes.append(MedicationQuestionReasonCode.NO_ENTITY_IDENTIFIED)
    if query_plan.interaction_pairs or query_plan.interaction_pair is not None:
        reason_codes.append(
            MedicationQuestionReasonCode.INTERACTION_PAIR_IDENTIFIED,
        )
    return MedicationQuestionInterpretation(
        original_question=(resolution.original_question if resolution is not None else value.question),
        resolved_question=value.question,
        scope=scope,
        resolution_status=resolution_status,
        intent=intent,
        confidence=confidence,
        normalized_entity_names=query_plan.entity_names,
        normalized_entities=query_plan.entities,
        requested_section_types=query_plan.section_types,
        interaction_types=query_plan.interaction_types,
        needs_clarification=(resolution_status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
        correction_count=(len(resolution.corrections) if resolution else 0),
        candidate_count=(len(resolution.candidate_names) if resolution else 0),
        reason_codes=reason_codes,
        query_plan_hash=query_plan.query_plan_hash,
    )


def _question_intent(
    *,
    scope: MedicationQuestionScope,
    resolution_status: MedicationExpressionResolutionStatus,
    query_plan: MedicationKnowledgeQueryPlan,
) -> MedicationQuestionIntent:
    if scope == MedicationQuestionScope.GREETING:
        return MedicationQuestionIntent.GREETING
    if scope == MedicationQuestionScope.OUT_OF_SCOPE:
        return MedicationQuestionIntent.OUT_OF_SCOPE
    if resolution_status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED:
        return MedicationQuestionIntent.CLARIFICATION
    if KnowledgeSectionType.INTERACTION in query_plan.section_types:
        return MedicationQuestionIntent.INTERACTION
    if any(entity.kind == InteractionEntityKind.SUPPLEMENT for entity in query_plan.entities):
        return MedicationQuestionIntent.SUPPLEMENT_GUIDE
    if any(entity.kind == InteractionEntityKind.DRUG for entity in query_plan.entities):
        return MedicationQuestionIntent.MEDICATION_GUIDE
    return MedicationQuestionIntent.GENERAL_GUIDANCE


def _question_confidence(
    *,
    scope: MedicationQuestionScope,
    resolution_available: bool,
    resolution_status: MedicationExpressionResolutionStatus,
    query_plan: MedicationKnowledgeQueryPlan,
) -> MedicationQuestionConfidence:
    if scope in {
        MedicationQuestionScope.GREETING,
        MedicationQuestionScope.OUT_OF_SCOPE,
    }:
        return MedicationQuestionConfidence.LOW
    if not resolution_available:
        return MedicationQuestionConfidence.LOW
    if resolution_status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED:
        return MedicationQuestionConfidence.LOW
    if resolution_status == MedicationExpressionResolutionStatus.AUTO_CORRECTED:
        return MedicationQuestionConfidence.MEDIUM
    if query_plan.entity_names:
        return MedicationQuestionConfidence.HIGH
    return MedicationQuestionConfidence.LOW


def build_medication_query_plan_chain() -> MedicationQueryPlanChain:
    """규칙 기반 해석을 구조화 입력·출력으로 감싼 LCEL 체인을 만든다."""

    input_validator = RunnableLambda(_validate_query_input).with_config(
        run_name="medication.query.input",
    )
    query_planner = RunnableLambda(_build_query_plan).with_config(
        run_name="medication.query.classify",
    )
    return (input_validator | query_planner).with_types(
        input_type=MedicationQueryPlanChainInput,
        output_type=MedicationQuestionPlanResult,
    )
