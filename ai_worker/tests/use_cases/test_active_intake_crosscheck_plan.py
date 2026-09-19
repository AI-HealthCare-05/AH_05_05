from ai_worker.schemas.interaction import InteractionEntityKind, InteractionPairType
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import ActiveIntakeContext, ActiveMedication
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationInteractionQueryPair,
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntityType,
    MedicationQuestionConfidence,
    MedicationQuestionIntent,
    MedicationQuestionInterpretation,
    MedicationQuestionScope,
    MedicationSearchExecutionPlan,
)
from ai_worker.use_cases.answer_medication_question import (
    AnswerMedicationQuestionUseCase,
    MedicationQuestionPlanResult,
)

CONTEXT = ActiveIntakeContext(
    user_id=1,
    medications=[ActiveMedication(medication_id=1, care_episode_id=1, name="와파린")],
)


def build_planning(
    *,
    entities: list[MedicationQueryEntity],
    interaction_pairs: list[MedicationInteractionQueryPair] | None = None,
) -> MedicationQuestionPlanResult:
    query_plan = MedicationKnowledgeQueryPlan(
        original_query="비타민K 먹어도 돼?",
        expanded_query="비타민K",
        entity_names=[entity.canonical_name for entity in entities],
        entities=entities,
        section_types=[KnowledgeSectionType.FUNCTION],
        interaction_pairs=interaction_pairs or [],
    )
    interpretation = MedicationQuestionInterpretation(
        original_question="비타민K 먹어도 돼?",
        resolved_question="비타민K 먹어도 돼?",
        intent=MedicationQuestionIntent.SUPPLEMENT_GUIDE,
        confidence=MedicationQuestionConfidence.HIGH,
        scope=MedicationQuestionScope.IN_SCOPE,
        resolution_status=MedicationExpressionResolutionStatus.UNCHANGED,
        query_plan_hash=query_plan.query_plan_hash,
    )
    return MedicationQuestionPlanResult(query_plan=query_plan, interpretation=interpretation)


def vitamin_k() -> MedicationQueryEntity:
    return MedicationQueryEntity(
        surface="비타민K",
        canonical_name="비타민 K",
        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
        kind=InteractionEntityKind.SUPPLEMENT,
    )


def test_registered_intake_is_paired_with_the_named_target() -> None:
    planning = AnswerMedicationQuestionUseCase._with_active_intake_crosscheck_pairs(
        context=CONTEXT,
        planning=build_planning(entities=[vitamin_k()]),
    )

    assert [(pair.left_name, pair.right_name) for pair in planning.query_plan.crosscheck_pairs] == [
        ("와파린", "비타민 K")
    ]


def test_crosscheck_pairs_never_reclassify_the_question_as_an_interaction_question() -> None:
    """`interaction_pairs`에 넣으면 경로·제품 조회·답변 구성이 모두 바뀐다."""
    planning = AnswerMedicationQuestionUseCase._with_active_intake_crosscheck_pairs(
        context=CONTEXT,
        planning=build_planning(entities=[vitamin_k()]),
    )
    plan = planning.query_plan

    assert plan.interaction_pairs == []
    assert plan.interaction_pair_keys == []
    assert plan.section_types == [KnowledgeSectionType.FUNCTION]


def test_question_that_already_asks_about_an_interaction_is_left_alone() -> None:
    existing = MedicationInteractionQueryPair(
        left_name="와파린",
        right_name="비타민 K",
        pair_type=InteractionPairType.DRUG_SUPPLEMENT,
        pair_key="c" * 64,
    )

    planning = AnswerMedicationQuestionUseCase._with_active_intake_crosscheck_pairs(
        context=CONTEXT,
        planning=build_planning(entities=[vitamin_k()], interaction_pairs=[existing]),
    )

    assert planning.query_plan.crosscheck_pairs == []


def test_crosscheck_search_plan_does_not_demand_a_pair_match() -> None:
    """전용 검색은 느슨하게 둔다. 쌍 일치를 요구하면 제품명 기반 쌍이 전부 탈락한다."""
    planning = AnswerMedicationQuestionUseCase._with_active_intake_crosscheck_pairs(
        context=CONTEXT,
        planning=build_planning(entities=[vitamin_k()]),
    )
    execution_plan = MedicationSearchExecutionPlan(
        query_plan=planning.query_plan,
        context_hash="0" * 64,
        approved_rules_hash="0" * 64,
    )

    crosscheck = AnswerMedicationQuestionUseCase._crosscheck_execution_plan(
        execution_plan=execution_plan,
    )

    assert crosscheck.query_plan.interaction_pairs == []
    assert crosscheck.query_plan.section_types == []
    assert crosscheck.query_plan.alternate_queries == ["와파린 비타민 K 상호작용"]
    assert crosscheck.query_plan.crosscheck_pairs == []
