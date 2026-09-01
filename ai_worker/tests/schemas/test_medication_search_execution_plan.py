from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.medication_search import (
    InteractionRuleLookupStatus,
    MedicationSearchExecutionObservation,
    MedicationSearchExecutionPlan,
)


def build_plan(
    *,
    question: str = "와파린과 비타민 K 영양제를 같이 먹어도 되나요?",
    medications: list[str] | None = None,
    supplements: list[str] | None = None,
    rule_pair_keys: list[str] | None = None,
) -> MedicationSearchExecutionPlan:
    return MedicationSearchExecutionPlan(
        query_plan=MedicationKnowledgeQueryBuilder().build(question),
        patient_medication_names=medications or [],
        patient_supplement_names=supplements or [],
        approved_rule_pair_keys=rule_pair_keys or [],
        context_hash="a" * 64,
        approved_rules_hash="b" * 64,
        include_patient_context=bool(medications or supplements),
        limit=5,
    )


def test_execution_plan_preserves_question_signals_without_context_or_rules() -> None:
    plan = build_plan()

    assert plan.medication_names == ["와파린"]
    assert plan.supplement_names == ["비타민 K"]
    assert plan.interaction_pair_keys == plan.query_plan.interaction_pair_keys


def test_execution_plan_augments_question_signals_with_context_and_rules() -> None:
    plan = build_plan(
        medications=["아스피린"],
        supplements=["칼슘"],
        rule_pair_keys=["c" * 64],
    )

    assert plan.medication_names == ["와파린", "아스피린"]
    assert plan.supplement_names == ["비타민 K", "칼슘"]
    assert plan.interaction_pair_keys == [
        *plan.query_plan.interaction_pair_keys,
        "c" * 64,
    ]


def test_execution_plan_preserves_but_does_not_apply_unrequested_patient_context() -> None:
    plan = build_plan(
        question="마그네슘은 왜 먹나요?",
        medications=["아스피린"],
        supplements=["칼슘"],
    ).model_copy(update={"include_patient_context": False})

    assert plan.patient_medication_names == ["아스피린"]
    assert plan.patient_supplement_names == ["칼슘"]
    assert plan.medication_names == []
    assert plan.supplement_names == ["마그네슘"]


def test_execution_plan_hash_is_deterministic_and_source_sensitive() -> None:
    first = build_plan(medications=["아스피린"])
    same = build_plan(medications=["아스피린"])
    changed = build_plan(medications=["로사르탄"])

    assert first.execution_plan_hash == same.execution_plan_hash
    assert first.execution_plan_hash != changed.execution_plan_hash
    assert first.query_plan_hash == changed.query_plan_hash

    unavailable = first.model_copy(
        update={"approved_rule_status": (InteractionRuleLookupStatus.RULE_REPOSITORY_UNAVAILABLE)}
    )
    assert first.execution_plan_hash != unavailable.execution_plan_hash


def test_execution_observation_preserves_ambiguous_candidates() -> None:
    plan = build_plan(question="타이레놀의 효능을 알려줘")

    observation = MedicationSearchExecutionObservation.from_execution_plan(
        plan,
    )

    assert observation.query_plan.entities[0].resolution_status.value == "AMBIGUOUS"
    assert observation.query_plan_hash == plan.query_plan_hash
    assert observation.execution_plan_hash == plan.execution_plan_hash
