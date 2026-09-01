import pytest

from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
    MedicationQueryEntityType,
)
from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
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


def test_build_preserves_vitamin_b_as_ingredient_family() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "비타민 B는 왜 먹나요?",
    )

    assert plan.entity_names == ["비타민 B"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_FAMILY
    assert plan.ingredient_family is not None
    assert plan.ingredient_family.canonical_name == "비타민 B"
    assert plan.ingredient_family.member_names == [
        "비타민 B1(티아민)",
        "비타민 B2(리보플라빈)",
        "비타민 B3(나이아신)",
        "비타민 B5(판토텐산)",
        "비타민 B6(피리독신)",
        "비타민 B7(비오틴)",
        "비타민 B9(엽산)",
        "비타민 B12(코발라민)",
    ]
    assert plan.section_types == [KnowledgeSectionType.FUNCTION]
    assert "비타민 B군" in plan.expanded_query


def test_build_keeps_specific_vitamin_b_member_as_ingredient() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "비타민 B6는 하루에 얼마나 먹나요?",
    )

    assert plan.entity_names == ["비타민 B6"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_NAME
    assert plan.ingredient_family is None
    assert plan.section_types == [KnowledgeSectionType.DAILY_INTAKE]


def test_build_keeps_disease_topic_without_predicate_noise() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "과민성대장증후군은 어떤 증상이 나타나고 어떻게 관리하나요?",
    )

    assert plan.entity_names == ["과민성대장증후군"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.TOPIC


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
    assert plan.entity_names == ["칼슘", "철분"]


def test_build_removes_measurement_and_predicate_noise_from_pair_question() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "아연을 복용하면 철분 수치가 낮아질 수 있나요?",
    )

    assert plan.entity_names == ["아연", "철분"]
    assert plan.alternate_queries == [
        "zinc iron status interaction supplementation",
    ]


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


def test_build_adds_concise_entity_query_for_unregistered_interaction_pair() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
    )

    assert plan.alternate_queries == [
        "펙소페나딘 과일주스 상호작용",
    ]


def test_build_does_not_treat_drug_form_descriptor_as_separate_entity() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "로사르탄 복합제의 주의사항을 알려줘",
    )

    assert plan.entity_names == ["로사르탄"]


def test_build_classifies_general_drug_usage_without_filler_entities() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "로사르탄은 일반적으로 어떻게 복용하나요?",
    )

    assert plan.entity_names == ["로사르탄"]
    assert plan.section_types == [KnowledgeSectionType.DAILY_INTAKE]


def test_build_preserves_every_entity_when_known_pair_is_part_of_larger_question() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "내가 복용 중인 와파린, 비타민 K, 칼슘, 철분의 상호작용을 우선순위로 요약해줘.",
    )

    assert plan.entity_names == ["와파린", "비타민 K", "칼슘", "철분"]
    assert set(plan.interaction_types) == {
        InteractionPairType.DRUG_SUPPLEMENT,
        InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    }
    assert {(pair.left_name, pair.right_name) for pair in plan.interaction_pairs} == {
        ("와파린", "비타민 K"),
        ("와파린", "칼슘"),
        ("와파린", "철분"),
        ("비타민 K", "칼슘"),
        ("비타민 K", "철분"),
        ("칼슘", "철분"),
    }
    assert "와파린 비타민 K 상호작용" in plan.alternate_queries
    assert "와파린 칼슘 상호작용" in plan.alternate_queries
    assert "calcium iron absorption interaction" in plan.alternate_queries


def test_build_limits_multi_entity_pairs_and_prioritizes_drug_drug() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "아스피린, 와파린, 비타민 K, 칼슘, 철분의 상호작용을 알려줘.",
    )

    assert len(plan.interaction_pairs) == 6
    assert plan.interaction_pairs[0].pair_type == InteractionPairType.DRUG_DRUG
    assert (
        plan.interaction_pairs[0].left_name,
        plan.interaction_pairs[0].right_name,
    ) == ("아스피린", "와파린")


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
    assert plan.entities[0].candidate_types == [
        MedicationQueryEntityType.PRODUCT_NAME,
        MedicationQueryEntityType.BRAND_ALIAS,
        MedicationQueryEntityType.INGREDIENT_NAME,
    ]
    assert plan.section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.CAUTION,
    ]
    assert plan.entities[0].source.value == "ALIAS"
    assert plan.entities[0].resolution_status.value == "AMBIGUOUS"


def test_build_resolves_common_brand_to_ingredient_for_interaction_search() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "타이레놀과 와파린을 같이 먹어도 되나요?",
    )

    assert plan.entity_names == ["아세트아미노펜", "와파린"]
    assert plan.entities[0].surface == "타이레놀"
    assert plan.entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_NAME
    assert plan.entities[0].candidate_types == [
        MedicationQueryEntityType.PRODUCT_NAME,
        MedicationQueryEntityType.BRAND_ALIAS,
        MedicationQueryEntityType.INGREDIENT_NAME,
    ]
    assert plan.alternate_queries == [
        "아세트아미노펜 와파린 상호작용",
    ]


def test_build_keeps_exact_tylenol_product_as_product_name() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "타이레놀정500밀리그람의 복용법을 알려줘.",
    )

    assert plan.entity_names == ["타이레놀정500밀리그람"]
    assert plan.entities[0].entity_type == MedicationQueryEntityType.PRODUCT_NAME
    assert plan.entities[0].candidate_types == [
        MedicationQueryEntityType.PRODUCT_NAME,
    ]


def test_build_adds_concise_ingredient_query_for_general_drug_question() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "내가 복용 중인 로사르탄의 복용법과 주의사항을 알려줘.",
    )

    assert plan.alternate_queries == [
        "로사르탄 용법 용량",
        "로사르탄 주의사항 부작용",
    ]


def test_build_uses_drug_terms_for_ingredient_function_and_caution() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "로사르탄의 효능과 주의사항을 알려줘.",
    )

    assert plan.alternate_queries == [
        "로사르탄 효능 효과",
        "로사르탄 주의사항 부작용",
    ]
    assert "건강기능식품" not in plan.expanded_query
    assert "기능성" not in plan.expanded_query
    assert "섭취 목적" not in plan.expanded_query


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


def test_build_recognizes_catalogued_single_character_ingredient() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "철은 왜 먹나요?",
    )

    assert plan.entity_names == ["철"]
    assert plan.entities[0].source.value == "CATALOG"


def test_build_ignores_uncatalogued_single_character_word() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "물은 언제 마시나요?",
    )

    assert "물" not in plan.entity_names


def test_build_does_not_classify_disease_topic_as_ingredient() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "과민성대장증후군의 생활 관리 방법을 알려줘.",
    )

    topic_entities = [entity for entity in plan.entities if entity.canonical_name == "과민성대장증후군"]
    assert topic_entities
    assert topic_entities[0].entity_type != MedicationQueryEntityType.INGREDIENT_NAME
    assert topic_entities[0].entity_type.value == "TOPIC"
    assert topic_entities[0].kind is None


@pytest.mark.parametrize(
    ("question", "expected_names", "expected_pair_type"),
    [
        (
            "칼슘과 철분을 같이 먹어도 되나요?",
            ["칼슘", "철분"],
            InteractionPairType.SUPPLEMENT_SUPPLEMENT,
        ),
        (
            "펙소페나딘과 과일주스를 같이 먹어도 되나요?",
            ["펙소페나딘", "과일주스"],
            InteractionPairType.DRUG_FOOD,
        ),
        (
            "와파린과 비타민 K 영양제를 같이 먹어도 되나요?",
            ["와파린", "비타민 K"],
            InteractionPairType.DRUG_SUPPLEMENT,
        ),
        (
            "와파린과 메트로니다졸을 같이 먹어도 되나요?",
            ["와파린", "메트로니다졸"],
            InteractionPairType.DRUG_DRUG,
        ),
    ],
)
def test_build_preserves_natural_language_interaction_pair_contract(
    question: str,
    expected_names: list[str],
    expected_pair_type: InteractionPairType,
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert plan.entity_names == expected_names
    assert len(plan.interaction_pairs) == 1
    assert plan.interaction_pairs[0].pair_type == expected_pair_type
    assert plan.section_types == [KnowledgeSectionType.INTERACTION]


def test_build_uses_standard_pair_key_factory() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "펙소페나딘과 과일주스를 같이 먹어도 되나요?",
    )
    expected_pair_key = build_interaction_pair_key(
        InteractionEntity(
            kind=InteractionEntityKind.DRUG,
            display_name="펙소페나딘",
        ),
        InteractionEntity(
            kind=InteractionEntityKind.FOOD,
            display_name="과일주스",
        ),
    )

    assert plan.interaction_pairs[0].pair_key == expected_pair_key
    assert plan.interaction_pair_keys == [expected_pair_key]


def test_build_is_deterministic_for_serialization_and_hash() -> None:
    builder = MedicationKnowledgeQueryBuilder()

    first = builder.build("와파린과 비타민 K를 같이 먹어도 되나요?")
    second = builder.build("와파린과 비타민 K를 같이 먹어도 되나요?")

    assert first.model_dump_json() == second.model_dump_json()
    assert first.query_plan_hash == second.query_plan_hash
    assert len(first.query_plan_hash) == 64


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


def test_build_preserves_ingredient_name_that_ends_with_e() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "알로에는 왜 먹어?",
    )

    assert plan.entity_names == ["알로에"]


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


@pytest.mark.parametrize(
    ("question", "expected_names"),
    [
        (
            "비타민 B6의 일일 섭취량 기준은 얼마인가요?",
            ["비타민 B6"],
        ),
        (
            "비타민 A의 일일 섭취량 기준은 어떻게 되나요?",
            ["비타민 A"],
        ),
        (
            "독사조신 복용 후 심한 어지러움이 보고된 사례가 있나요?",
            ["독사조신"],
        ),
        (
            "와파린과 메트로니다졸을 같이 복용해도 되나요?",
            ["와파린", "메트로니다졸"],
        ),
    ],
)
def test_build_removes_general_language_noise_from_evaluation_questions(
    question: str,
    expected_names: list[str],
) -> None:
    plan = MedicationKnowledgeQueryBuilder().build(question)

    assert plan.entity_names == expected_names


def test_build_preserves_multiword_vaccine_name_as_one_entity() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "A형 간염 백신은 어떤 역할을 하나요?",
    )

    assert plan.entity_names == ["A형 간염 백신"]
    assert plan.entities[0].kind == InteractionEntityKind.DRUG
    assert plan.section_types == [KnowledgeSectionType.FUNCTION]


def test_build_detects_supplement_absorption_effect_as_interaction() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "칼슘 섭취가 철 흡수에 어떤 영향을 줄 수 있나요?",
    )

    assert plan.entity_names == ["칼슘", "철분"]
    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert plan.interaction_types == [
        InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    ]


def test_build_detects_drug_food_usage_as_interaction() -> None:
    plan = MedicationKnowledgeQueryBuilder().build(
        "알렌드로네이트는 음식이나 물과 어떻게 복용해야 하나요?",
    )

    assert plan.entity_names == ["알렌드로네이트", "음식"]
    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert plan.interaction_types == [InteractionPairType.DRUG_FOOD]
