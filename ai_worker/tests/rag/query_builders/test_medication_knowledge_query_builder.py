from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


def test_build_expands_supplement_function_question() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "마그네슘은 왜 먹어?",
    )

    assert plan.original_query == "마그네슘은 왜 먹어?"
    assert "마그네슘" in plan.entity_names
    assert "기능성" in plan.expanded_query
    assert plan.section_types == [KnowledgeSectionType.FUNCTION]
    assert plan.has_medication_product_cue is False


def test_build_detects_daily_intake_intent() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "비타민 D는 하루에 얼마나 먹어?",
    )

    assert "비타민 D" in plan.entity_names
    assert plan.section_types == [KnowledgeSectionType.DAILY_INTAKE]
    assert "일일섭취량" in plan.expanded_query


def test_build_keeps_explicit_medication_product_cue() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "마그밀정 500mg 주의사항",
    )

    assert plan.has_medication_product_cue is True
    assert plan.section_types == [KnowledgeSectionType.CAUTION]


def test_build_detects_calcium_iron_pair_and_adds_separate_english_query() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "칼슘제와 철분제는 시간을 띄워 먹어야 하나요?",
    )

    assert plan.entity_names == ["칼슘", "철분"]
    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert plan.alternate_queries == ["calcium iron absorption interaction"]
    assert plan.interaction_pair is not None
    assert plan.interaction_pair.canonical_names == ("칼슘", "철분")


def test_build_treats_pair_effect_question_as_interaction_without_explicit_keyword() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "칼슘이 철분 흡수에 미치는 영향은 일시적인가요?",
    )

    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert plan.interaction_pair is not None
