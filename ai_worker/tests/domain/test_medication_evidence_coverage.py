from ai_worker.domain.medication_evidence_coverage import (
    MedicationEvidenceCoverageEvaluator,
)
from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionPairType,
    build_interaction_pair_key,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    InteractionRuleFact,
    MedicationGuideFact,
    MedicationGuideLookup,
)
from ai_worker.schemas.medication_search import (
    MedicationInteractionQueryPair,
    MedicationKnowledgeQueryPlan,
)


def test_single_entity_approved_rule_covers_interaction_for_llm_rewrite() -> None:
    plan = build_plan(KnowledgeSectionType.INTERACTION).model_copy(update={"entity_names": ["와파린"]})
    rule = InteractionRuleFact(
        interaction_rule_id=1,
        pair_key="a" * 64,
        pair_type="DRUG_DRUG",
        left_name="와파린",
        right_name="이그라티모드",
        risk_level="CAUTION",
        effect_texts=["warfarin의항응고효과증가"],
    )
    evaluator = MedicationEvidenceCoverageEvaluator()
    coverage = evaluator.evaluate(query_plan=plan, guide_lookup=MedicationGuideLookup(), rules=[rule], chunks=[])
    assert coverage.covered_section_types == [KnowledgeSectionType.INTERACTION]
    unrelated = rule.model_copy(update={"left_name": "아스피린"})
    assert (
        evaluator.evaluate(
            query_plan=plan, guide_lookup=MedicationGuideLookup(), rules=[unrelated], chunks=[]
        ).covered_section_types
        == []
    )


def test_approved_class_evidence_covers_overview_without_verifying_a_pair() -> None:
    plan = build_plan(KnowledgeSectionType.INTERACTION).model_copy(
        update={"original_query": "와파린 상호작용 알려줘", "entity_names": ["와파린"]}
    )
    chunk = build_interaction_chunk(pair_keys=[]).model_copy(
        update={
            "content": "상호작용경구제를 항응고제와 함께 투여 시 작용이 증가되어 부작용이 나타날 수 있다.",
            "metadata": build_interaction_chunk(pair_keys=[]).metadata.model_copy(
                update={
                    "document_type": KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                    "section_type": KnowledgeSectionType.ADVERSE_EVENT,
                    "drug_names": ["오메가-3"],
                }
            ),
        }
    )

    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=plan,
        guide_lookup=MedicationGuideLookup(),
        rules=[],
        chunks=[chunk],
        approved_therapeutic_class_names=["항응고제"],
    )

    assert coverage.covered_section_types == [KnowledgeSectionType.INTERACTION]
    assert coverage.verified_interaction_pair_keys == []


def test_unapproved_or_unmatched_class_evidence_does_not_cover_interaction() -> None:
    plan = build_plan(KnowledgeSectionType.INTERACTION).model_copy(
        update={"original_query": "와파린 상호작용 알려줘", "entity_names": ["와파린"]}
    )
    chunk = build_interaction_chunk(pair_keys=[], content="항응고제와 함께 투여 시 주의합니다.")

    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=plan,
        guide_lookup=MedicationGuideLookup(),
        rules=[],
        chunks=[chunk],
    )

    assert coverage.covered_section_types == []


def build_plan(
    *section_types: KnowledgeSectionType,
    pair_key: str | None = None,
) -> MedicationKnowledgeQueryPlan:
    interaction_pairs = []
    interaction_pair_keys = []
    if pair_key is not None:
        interaction_pairs = [
            MedicationInteractionQueryPair(
                left_name="칼슘",
                right_name="철분",
                pair_type=InteractionPairType.SUPPLEMENT_SUPPLEMENT,
                pair_key=pair_key,
            )
        ]
        interaction_pair_keys = [pair_key]
    return MedicationKnowledgeQueryPlan(
        original_query="칼슘과 철분을 같이 먹어도 되나요?",
        expanded_query="칼슘 철분 상호작용",
        section_types=list(section_types),
        interaction_pairs=interaction_pairs,
        interaction_pair_keys=interaction_pair_keys,
    )


def build_guide(**updates: str) -> MedicationGuideLookup:
    values = {
        "medication_guide_id": 1,
        "item_seq": "100",
        "product_name": "시험약",
        "manufacturer_name": "시험제약",
        "efficacy": "통증을 완화합니다.",
        "usage_instructions": "",
        "pre_use_warning": "",
        "precautions": "",
        "drug_food_interactions": "",
        "adverse_reactions": "",
        "storage_instructions": "",
    }
    values.update(updates)
    return MedicationGuideLookup(guide=MedicationGuideFact(**values))


def build_interaction_chunk(
    *,
    pair_keys: list[str],
    content: str = "마그네슘과 아연을 함께 섭취한 연구 결과입니다.",
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="point-1",
        chunk_id="a" * 64,
        content=content,
        embedding_text=content,
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="source-1",
            document_id="document-1",
            title="칼슘과 철분 연구",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version="knowledge-full-v2-interaction-metadata",
            ingredient_names=["칼슘", "철분"],
            interaction_type=InteractionPairType.SUPPLEMENT_SUPPLEMENT.value,
            interaction_pair_keys=pair_keys,
            section_type=KnowledgeSectionType.INTERACTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


def calcium_iron_pair_key() -> str:
    return build_interaction_pair_key(
        InteractionEntity(
            kind=InteractionEntityKind.SUPPLEMENT,
            display_name="칼슘",
        ),
        InteractionEntity(
            kind=InteractionEntityKind.SUPPLEMENT,
            display_name="철분",
        ),
    )


def test_evaluate_keeps_uncovered_requested_guide_section_missing() -> None:
    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=build_plan(
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.DAILY_INTAKE,
        ),
        guide_lookup=build_guide(),
        rules=[],
        chunks=[],
    )

    assert coverage.requested_section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
    ]
    assert coverage.covered_section_types == [KnowledgeSectionType.FUNCTION]
    assert coverage.missing_section_types == [KnowledgeSectionType.DAILY_INTAKE]


def test_evaluate_requires_exact_pair_for_interaction_coverage() -> None:
    requested_pair_key = calcium_iron_pair_key()
    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=build_plan(
            KnowledgeSectionType.INTERACTION,
            pair_key=requested_pair_key,
        ),
        guide_lookup=MedicationGuideLookup(),
        rules=[],
        chunks=[build_interaction_chunk(pair_keys=["c" * 64])],
    )

    assert coverage.covered_section_types == []
    assert coverage.missing_section_types == [KnowledgeSectionType.INTERACTION]
    assert coverage.verified_interaction_pair_keys == []


def test_evaluate_accepts_approved_rule_for_requested_pair() -> None:
    requested_pair_key = calcium_iron_pair_key()
    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=build_plan(
            KnowledgeSectionType.INTERACTION,
            pair_key=requested_pair_key,
        ),
        guide_lookup=MedicationGuideLookup(),
        rules=[
            InteractionRuleFact(
                interaction_rule_id=1,
                pair_key=requested_pair_key,
                pair_type=InteractionPairType.SUPPLEMENT_SUPPLEMENT.value,
                left_name="칼슘",
                right_name="철분",
                risk_level="CAUTION",
                effect_texts=["흡수에 영향을 줄 수 있습니다."],
            )
        ],
        chunks=[],
    )

    assert coverage.covered_section_types == [KnowledgeSectionType.INTERACTION]
    assert coverage.missing_section_types == []
    assert coverage.verified_interaction_pair_keys == [requested_pair_key]


def test_adverse_event_is_covered_only_when_adverse_reactions_has_evidence() -> None:
    """이상반응은 주의사항 근거에 묶여 있지만 자료가 없으면 확보로 세지 않는다.

    묶어서 세면 이상반응 자료가 없는 제품에서 `🚨 **이상반응**` 섹션이 근거 검증을 통과한다.
    """

    evaluator = MedicationEvidenceCoverageEvaluator()
    plan = build_plan()

    without_adverse = evaluator.evaluate(
        query_plan=plan,
        guide_lookup=build_guide(precautions="정해진 용법을 지킵니다."),
        rules=[],
        chunks=[],
    )
    with_adverse = evaluator.evaluate(
        query_plan=plan,
        guide_lookup=build_guide(
            precautions="정해진 용법을 지킵니다.",
            adverse_reactions="드물게 발진이 나타날 수 있습니다.",
        ),
        rules=[],
        chunks=[],
    )

    assert KnowledgeSectionType.CAUTION in without_adverse.covered_section_types
    assert KnowledgeSectionType.ADVERSE_EVENT not in without_adverse.covered_section_types
    assert KnowledgeSectionType.ADVERSE_EVENT in with_adverse.covered_section_types


def test_unspecified_request_covers_available_guide_sections() -> None:
    """항목을 지정하지 않은 질문도 확보한 근거를 covered로 남긴다.

    빈 목록으로 두면 답변이 어떤 섹션을 선언하든 근거 밖으로 판정해 초안이 그대로 나간다.
    """

    coverage = MedicationEvidenceCoverageEvaluator().evaluate(
        query_plan=build_plan(),
        guide_lookup=build_guide(
            usage_instructions="1일 3회 복용합니다.",
            precautions="정해진 용법을 지킵니다.",
        ),
        rules=[],
        chunks=[],
    )

    assert coverage.requested_section_types == []
    assert coverage.covered_section_types == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
    ]


def test_requested_caution_also_covers_adverse_event_when_evidence_exists() -> None:
    """같은 질문이 표현에 따라 다른 섹션 구성으로 나오지 않게 한다.

    화면의 주의사항과 이상반응은 같은 주의사항 근거에서 오므로, 주의사항을 요청했고
    이상반응 자료가 실제로 있으면 함께 확보로 센다.
    """

    evaluator = MedicationEvidenceCoverageEvaluator()
    plan = build_plan(KnowledgeSectionType.CAUTION)

    with_adverse = evaluator.evaluate(
        query_plan=plan,
        guide_lookup=build_guide(
            precautions="정해진 용법을 지킵니다.",
            adverse_reactions="드물게 발진이 나타날 수 있습니다.",
        ),
        rules=[],
        chunks=[],
    )
    without_adverse = evaluator.evaluate(
        query_plan=plan,
        guide_lookup=build_guide(precautions="정해진 용법을 지킵니다."),
        rules=[],
        chunks=[],
    )

    assert KnowledgeSectionType.ADVERSE_EVENT in with_adverse.covered_section_types
    assert KnowledgeSectionType.ADVERSE_EVENT not in without_adverse.covered_section_types
