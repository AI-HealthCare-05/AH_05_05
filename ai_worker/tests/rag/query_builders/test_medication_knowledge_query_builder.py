import pytest

from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
    MedicationQueryEntityType,
)
from ai_worker.schemas.interaction import (
    InteractionEntityKind,
    InteractionPairType,
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


@pytest.mark.parametrize(
    "question",
    [
        "펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
        "케토롤락 복용 중 아스피린을 피해야 하나요?",
        "와파린 복용 중 비타민 K를 피해야 하나요?",
        "마그네슘 복용 중 아연을 피해야 하나요?",
        "약과 함께 피해야 할 음식이 있나요?",
    ],
)
def test_build_treats_avoidance_between_intake_targets_as_interaction(
    question: str,
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert "상호작용" in plan.expanded_query


@pytest.mark.parametrize(
    "question",
    [
        "아스피린은 임신 중 피해야 하나요?",
        "임신 중 피해야 할 약이 있나요?",
    ],
)
def test_build_does_not_treat_single_target_contraindication_as_interaction(
    question: str,
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert KnowledgeSectionType.INTERACTION not in plan.section_types


@pytest.mark.parametrize(
    ("question", "expected_names", "expected_kinds", "expected_pair_types"),
    [
        (
            "내가 복용 중인 케토롤락과 아스피린을 같이 먹어도 되나요?",
            ["케토롤락", "아스피린"],
            [InteractionEntityKind.DRUG, InteractionEntityKind.DRUG],
            [InteractionPairType.DRUG_DRUG],
        ),
        (
            "펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
            ["펙소페나딘", "과일주스"],
            [InteractionEntityKind.DRUG, InteractionEntityKind.FOOD],
            [InteractionPairType.DRUG_FOOD],
        ),
        (
            "내가 복용 중인 와파린과 비타민 K 영양제를 같이 먹어도 되나요?",
            ["와파린", "비타민 K"],
            [InteractionEntityKind.DRUG, InteractionEntityKind.SUPPLEMENT],
            [InteractionPairType.DRUG_SUPPLEMENT],
        ),
        (
            "마그네슘 복용 중 아연을 피해야 하나요?",
            ["마그네슘", "아연"],
            [InteractionEntityKind.SUPPLEMENT, InteractionEntityKind.SUPPLEMENT],
            [InteractionPairType.SUPPLEMENT_SUPPLEMENT],
        ),
    ],
)
def test_build_normalizes_interaction_entities_and_pair_types(
    question: str,
    expected_names: list[str],
    expected_kinds: list[InteractionEntityKind],
    expected_pair_types: list[InteractionPairType],
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert plan.entity_names == expected_names
    assert [entity.kind for entity in plan.entities] == expected_kinds
    assert plan.interaction_types == expected_pair_types


def test_build_preserves_every_entity_when_known_pair_is_part_of_larger_question() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "내가 복용 중인 와파린, 비타민 K, 칼슘, 철분의 상호작용을 우선순위로 요약해줘.",
    )

    assert plan.entity_names == ["와파린", "비타민 K", "칼슘", "철분"]
    assert set(plan.interaction_types) == {
        InteractionPairType.DRUG_SUPPLEMENT,
        InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    }


def test_build_does_not_treat_interaction_instruction_as_drug_entity() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "내가 등록한 칼슘과 철분을 같이 먹을 때 주의할 점을 알려줘.",
    )

    assert plan.entity_names == ["칼슘", "철분"]
    assert plan.interaction_types == [
        InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    ]


def test_build_keeps_multiple_requested_sections() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "타이레놀의 효능과 주의사항을 알려줘.",
    )

    assert plan.entity_names == ["타이레놀"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.BRAND_ALIAS
    assert plan.section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.CAUTION,
    ]


def test_build_preserves_exact_product_name_without_instruction_noise() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "마그오캡슐500mg의 효능과 복용법을 알려줘.",
    )

    assert plan.entity_names == ["마그오캡슐500mg"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.PRODUCT_NAME


def test_build_normalizes_vitamin_spacing() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "와파린과 비타민K 영양제를 같이 먹어도 되나요?",
    )

    assert plan.entity_names == ["와파린", "비타민 K"]


def test_build_removes_choice_particle_from_food_name() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "펙소페나딘을 자몽주스나 사과주스와 함께 먹어도 되나요?",
    )

    assert plan.entity_names == [
        "펙소페나딘",
        "자몽주스",
        "사과주스",
    ]
    assert [entity.kind for entity in plan.entities] == [
        InteractionEntityKind.DRUG,
        InteractionEntityKind.FOOD,
        InteractionEntityKind.FOOD,
    ]
    assert plan.interaction_types == [InteractionPairType.DRUG_FOOD]


def test_build_preserves_entity_name_that_ends_with_na() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "스피루리나는 왜 먹어?",
    )

    assert plan.entity_names == ["스피루리나"]


@pytest.mark.parametrize(
    ("question", "expected_names"),
    [
        (
            "아스피린이랑 와파린을 같이 먹어도 되나요?",
            ["아스피린", "와파린"],
        ),
        (
            "마그네슘하고 아연을 같이 먹어도 되나요?",
            ["마그네슘", "아연"],
        ),
    ],
)
def test_build_removes_conjunction_particles_from_entity_names(
    question: str,
    expected_names: list[str],
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert plan.entity_names == expected_names
