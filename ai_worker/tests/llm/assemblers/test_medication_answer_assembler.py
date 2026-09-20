from datetime import date

from ai_worker.llm.assemblers.medication_answer_assembler import (
    MedicationAnswerAssembler,
)
from ai_worker.schemas.interaction import InteractionPairType
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    OMEGA_NUTRIENT_NAME,
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    InteractionRuleFact,
    MedicationEvidenceCoverage,
    MedicationGuideFact,
    SupplementNutrientAmount,
)
from ai_worker.schemas.medication_search import (
    MedicationInteractionQueryPair,
    SupplementIngredientFamily,
)


def test_overview_groups_drugs_and_supplements_without_contradictory_missing_notice() -> None:
    rules = [
        InteractionRuleFact(
            interaction_rule_id=1,
            pair_key="a" * 64,
            pair_type="DRUG_DRUG",
            left_name="이그라티모드",
            right_name="와파린",
            risk_level="CAUTION",
            effect_texts=["항응고 작용이 증가할 수 있습니다."],
        ),
        InteractionRuleFact(
            interaction_rule_id=2,
            pair_key="b" * 64,
            pair_type="DRUG_SUPPLEMENT",
            left_name="와파린",
            right_name="비타민 K",
            risk_level="HIGH_CAUTION",
            effect_texts=["항응고 효과가 감소할 수 있습니다."],
        ),
    ]
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=rules,
        chunks=[],
        interaction_question=True,
        interaction_overview_subject="와파린",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.INTERACTION],
            missing_section_types=[KnowledgeSectionType.INTERACTION],
        ),
    )
    assert "🔁 **약물 상호작용**" in answer
    assert "🔁 **영양제 상호작용**" in answer
    assert answer.count("**주의가 필요한 조합**") == 2
    assert "이그라티모드" in answer.split("🔁 **영양제 상호작용**")[0]
    assert "비타민 K" in answer.split("🔁 **영양제 상호작용**")[1]
    assert "도움이 확인된" not in answer
    assert "근거를 확인하지 못한 항목" not in answer
    assert "확인하지 못한 조합" not in answer


def test_assembler_labels_approved_class_evidence_as_class_level() -> None:
    chunk = RetrievedKnowledgeChunk(
        point_id="omega-3-interaction",
        chunk_id="h" * 64,
        content="경구제를 항응고제와 함께 투여하면 작용이 증가되어 부작용이 나타날 수 있다.",
        embedding_text="오메가-3 항응고제 상호작용",
        token_count=30,
        similarity_score=0.9,
        metadata=KnowledgeChunkMetadata(
            source_id="kpicia",
            document_id="omega-3-guide",
            title="오메가-3",
            provider="약학정보원",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
            dataset_version="knowledge-full-v17",
            drug_names=["오메가-3"],
            section_type=KnowledgeSectionType.INTERACTION,
            page_start=4,
            page_end=4,
            chunk_index=0,
            content_hash="h" * 64,
        ),
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[chunk],
        interaction_question=True,
        interaction_overview_subject="와파린",
        approved_therapeutic_class_names=["항응고제"],
    )

    assert "[약물 계열 수준 근거: 항응고제]" in answer


def build_guide(**updates: str) -> MedicationGuideFact:
    values = {
        "medication_guide_id": 12,
        "item_seq": "100",
        "product_name": "마그오캡슐500mg",
        "manufacturer_name": "테스트제약",
        "efficacy": "위산 과다 증상 완화와 변비 치료에 사용합니다.",
        "usage_instructions": "1일 1~2캡슐을 수회 분할 복용합니다.",
        "pre_use_warning": "신장 질환이 있으면 복용 전 상담합니다.",
        "precautions": "정해진 용법을 지킵니다.",
        "drug_food_interactions": "",
        "adverse_reactions": "설사 등이 나타날 수 있습니다.",
        "storage_instructions": "실온에 보관합니다.",
    }
    values.update(updates)
    return MedicationGuideFact(**values)


def test_interaction_overview_separates_drugs_from_supplements_and_food() -> None:
    rules = [
        InteractionRuleFact(
            interaction_rule_id=index,
            pair_key=str(index) * 64,
            pair_type=kind,
            left_name="와파린",
            right_name=name,
            risk_level="CAUTION",
            effect_texts=[fact],
        )
        for index, (kind, name, fact) in enumerate(
            [
                ("DRUG_DRUG", "약 A", "상호작용 근거 A"),
                ("DRUG_SUPPLEMENT", "성분 B", "상호작용 근거 B"),
                ("DRUG_FOOD", "음식 C", "상호작용 근거 C"),
            ],
            start=1,
        )
    ]
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=rules,
        chunks=[],
        interaction_question=True,
        interaction_overview=True,
    )
    drugs, others = answer.split("🍗 **그 외 상호작용**")
    assert "🧬 **약과 상호작용**" in drugs
    assert "약 A" in drugs and "성분 B" not in drugs
    assert "성분 B" in others and "음식 C" in others
    assert "확인하지 못한" not in answer


def test_assemble_omits_empty_product_guide_fields() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "✅ **복용법**\n- 1일 1~2캡슐" in answer
    assert "함께 주의할 약·음식" not in answer
    assert "이 안내는 보유한 자료를 바탕으로 한 참고 정보" not in answer


def test_assemble_omits_no_information_markers() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(
            drug_food_interactions="해당 없음",
        ),
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "함께 주의할 약·음식" not in answer


def test_assemble_only_includes_guide_sections_with_requested_evidence() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.DAILY_INTAKE,
            ],
            covered_section_types=[KnowledgeSectionType.FUNCTION],
            missing_section_types=[KnowledgeSectionType.DAILY_INTAKE],
        ),
    )

    assert "✅ **효능**\n- 위산 과다 증상 완화" in answer
    assert "✅ **복용법**" not in answer
    assert "복용법: 현재 근거에서 확인하지 못했습니다" in answer


def test_assemble_groups_product_guide_into_only_requested_sections() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
            covered_section_types=[
                KnowledgeSectionType.FUNCTION,
                KnowledgeSectionType.CAUTION,
            ],
        ),
    )

    assert answer.startswith("**마그오캡슐500mg**")
    assert "✅ **효능**\n- 위산 과다 증상 완화와 변비 치료에 사용합니다." in answer
    assert "⚠️ **주의사항**\n- 신장 질환이 있으면 복용 전 상담합니다." in answer
    assert "🚨 **이상반응**" not in answer
    assert "✅ **복용법**" not in answer


def test_assemble_product_guide_returns_only_requested_caution_section() -> None:
    """주의사항 질문은 이상반응·복용법을 함께 노출하지 않는다."""

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.CAUTION],
            covered_section_types=[KnowledgeSectionType.CAUTION],
        ),
    )

    assert "⚠️ **주의사항**" in answer
    assert "🚨 **이상반응**" not in answer
    assert "✅ **복용법**" not in answer
    assert "✅ **효능**" not in answer


def test_assemble_product_guide_returns_only_adverse_reaction_section() -> None:
    """이상반응 질문은 공식 이상반응 필드만 사용한다."""

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
        adverse_reaction_question=True,
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.CAUTION],
            covered_section_types=[KnowledgeSectionType.CAUTION],
        ),
    )

    assert "🚨 **이상반응**\n- 설사 등이 나타날 수 있습니다." in answer
    assert "⚠️ **주의사항**" not in answer
    assert "✅ **복용법**" not in answer
    assert "✅ **효능**" not in answer


def test_assemble_groups_magnesium_form_cautions_under_each_formulation() -> None:
    """일반 마그네슘 요청은 각 제형의 RDB 경고를 구분해 보인다."""

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
        form_caution_guides={
            "수산화마그네슘": [
                build_guide(
                    product_name="마그밀정(수산화마그네슘)",
                    pre_use_warning="신장 질환이 있으면 복용 전 상담합니다.",
                    precautions="다른 약과의 복용 간격을 확인합니다.",
                    adverse_reactions="설사가 나타날 수 있습니다.",
                )
            ],
            "산화마그네슘": [
                build_guide(
                    product_name="마그오캡슐500mg(산화마그네슘)",
                    pre_use_warning="신장 질환이 있으면 복용 전 상담합니다.",
                    precautions="정해진 용법을 지킵니다.",
                    adverse_reactions="묽은 변이 나타날 수 있습니다.",
                )
            ],
        },
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.CAUTION],
            covered_section_types=[KnowledgeSectionType.CAUTION],
        ),
        response_subject="마그네슘",
    )

    assert answer == (
        "**마그네슘**\n\n"
        "⚠️ **주의사항**\n\n"
        "**수산화마그네슘**\n"
        "- 신장 질환이 있으면 복용 전 상담합니다.\n"
        "- 다른 약과의 복용 간격을 확인합니다.\n"
        "- 설사가 나타날 수 있습니다.\n\n"
        "**산화마그네슘**\n"
        "- 신장 질환이 있으면 복용 전 상담합니다.\n"
        "- 정해진 용법을 지킵니다.\n"
        "- 묽은 변이 나타날 수 있습니다."
    )


def test_assemble_cleans_rdb_delimited_efficacy_into_readable_list() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(
            product_name="타이레놀산500밀리그램(아세트아미노펜)",
            efficacy=(
                "감기로인한발열및동통(통증)|두통|신경통|근육통|월경통|"
                "염좌통(삔통증)|치통|관절통|류마티양동통(통증)에사용합니다."
            ),
        ),
        rules=[],
        chunks=[],
        interaction_question=False,
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.FUNCTION],
            covered_section_types=[KnowledgeSectionType.FUNCTION],
        ),
    )

    assert answer.startswith("**타이레놀산500밀리그램(아세트아미노펜)**")
    assert "- 감기로 인한 발열 및 통증, 두통, 신경통, 근육통, 월경통" in answer
    assert "|" not in answer
    assert "(통증)" not in answer


def test_assemble_does_not_claim_missing_when_interaction_evidence_exists() -> None:
    chunk = RetrievedKnowledgeChunk(
        point_id="calcium-iron-point",
        chunk_id="a" * 64,
        content=(
            "인체 연구에서는 칼슘이 철분 흡수를 일시적으로 낮출 수 있으나 장기 철분 상태에는 적응이 관찰됐습니다."
        ),
        embedding_text="calcium iron absorption interaction",
        token_count=30,
        similarity_score=0.69,
        metadata=KnowledgeChunkMetadata(
            source_id="research_supplement_interactions",
            document_id="calcium-iron",
            title="Calcium and Iron Absorption",
            provider="학술 논문 발행처",
            access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version="knowledge-full-v1",
            ingredient_names=["칼슘", "철분"],
            section_type=KnowledgeSectionType.SUMMARY,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[chunk],
        interaction_question=True,
    )

    assert "확인하지 못했습니다" not in answer
    assert "검색된 상호작용 연구 근거" in answer
    assert "칼슘이 철분 흡수를" in answer


def test_assemble_uses_resolved_subject_and_section_for_public_drug_evidence() -> None:
    chunk = RetrievedKnowledgeChunk(
        point_id="doxazosin-point",
        chunk_id="d" * 64,
        content="독사조신 복용 후 심한 어지러움이 보고된 사례가 있습니다.",
        embedding_text="독사조신 심한 어지러움",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="drug-encyclopedia",
            document_id="doxazosin",
            title="독사조신 안전성 정보",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
            dataset_version="knowledge-full-v16-te3large",
            drug_names=["독사조신"],
            section_type=KnowledgeSectionType.CAUTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="e" * 64,
        ),
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[chunk],
        interaction_question=False,
        response_subject="독사조신",
        adverse_reaction_question=True,
    )

    assert answer.startswith("**독사조신**")
    assert "🚨 **이상반응**" in answer
    assert "공공자료 추가 설명" not in answer


def test_assemble_uses_named_functional_ingredient_as_the_public_knowledge_title() -> None:
    chunk = RetrievedKnowledgeChunk(
        point_id="melatonin-function",
        chunk_id="h" * 64,
        content="멜라토닌은 수면의 질 개선에 도움을 줄 수 있습니다.",
        embedding_text="멜라토닌 수면의 질 개선",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="supplement-function-guide",
            document_id="melatonin-sleep",
            title="멜라토닌 기능성 정보",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            dataset_version="knowledge-full-v16-te3large",
            ingredient_names=["멜라토닌"],
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="i" * 64,
        ),
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[chunk],
        interaction_question=False,
        response_subject=None,
    )

    assert answer.startswith("**멜라토닌**")
    assert "공공자료 추가 설명" not in answer


def test_assemble_groups_functional_ingredients_under_the_requested_health_goal() -> None:
    base_chunk = RetrievedKnowledgeChunk(
        point_id="joint-function-0",
        chunk_id="i" * 64,
        content="발효우슬등복합물은 관절 건강에 도움을 줄 수 있습니다.",
        embedding_text="발효우슬등복합물 관절 건강",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="supplement-function-guide",
            document_id="joint-health",
            title="관절 건강 기능성 정보",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            ingredient_names=["발효우슬등복합물"],
            dataset_version="knowledge-full-v17-function-ingredients",
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="j" * 64,
        ),
    )
    chunks = [
        base_chunk.model_copy(
            update={
                "chunk_id": chr(ord("i") + index) * 64,
                "metadata": base_chunk.metadata.model_copy(update={"ingredient_names": [ingredient_name]}),
            }
        )
        for index, ingredient_name in enumerate(
            [
                "발효우슬등복합물",
                "타마린드강황주정추출복합물",
                "구절초추출물",
                "가자추출물",
            ]
        )
    ]

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=chunks,
        interaction_question=False,
        functional_goal_title="관절 건강",
    )

    assert answer == (
        "**관절 건강**\n\n🧬 **성분**\n- 발효우슬등복합물\n- 타마린드강황주정추출복합물\n- 구절초추출물\n- 가자추출물"
    )


def test_assemble_functional_goal_uses_named_ingredients_even_when_topic_is_resolved() -> None:
    """기능성 목표는 TOPIC이 잡혀도 공공자료 원문 대신 성분명만 보여 준다."""

    base = RetrievedKnowledgeChunk(
        point_id="eye-function-0",
        chunk_id="q" * 64,
        content="(제2022-44호) 분류: 기능성 내용 기능성 내용: 눈 건강에 도움을 줄 수 있음",
        embedding_text="눈 건강 기능성 내용",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="supplement-function-guide",
            document_id="eye-health",
            title="눈 건강 기능성 정보",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            ingredient_names=["루테인지아잔틴복합추출물"],
            dataset_version="knowledge-full-v17-function-ingredients",
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="q" * 64,
        ),
    )
    chunks = [
        base,
        base.model_copy(
            update={
                "chunk_id": "r" * 64,
                "metadata": base.metadata.model_copy(update={"ingredient_names": ["감잎주정추출분말"]}),
            }
        ),
        base.model_copy(update={"chunk_id": "s" * 64}),
    ]

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=chunks,
        interaction_question=False,
        response_subject="눈 건강",
        functional_goal_title="눈 건강",
    )

    assert answer == "**눈 건강**\n\n🧬 **성분**\n- 루테인지아잔틴복합추출물\n- 감잎주정추출분말"
    assert "제2022" not in answer
    assert "기능성 내용" not in answer


def test_assemble_lists_up_to_three_ingredients_with_function_for_broad_health_goal() -> None:
    base = RetrievedKnowledgeChunk(
        point_id="health-function-0",
        chunk_id="z" * 64,
        content="복분자동결건조분말은 항산화에 도움을 줄 수 있습니다.",
        embedding_text="복분자동결건조분말 항산화",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="supplement-function-guide",
            document_id="health-goal",
            title="건강 기능성 정보",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            ingredient_names=["복분자동결건조분말"],
            dataset_version="knowledge-full-v17-function-ingredients",
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="z" * 64,
        ),
    )
    chunks = [
        base,
        base.model_copy(
            update={
                "chunk_id": "y" * 64,
                "content": "작약추출물등복합물은 위 건강에 도움을 줄 수 있습니다.",
                "metadata": base.metadata.model_copy(update={"ingredient_names": ["작약추출물등복합물"]}),
            }
        ),
    ]

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=chunks,
        interaction_question=False,
        functional_goal_title="건강 증진",
    )

    assert answer == (
        "**건강 증진**\n\n🧬 **성분**\n"
        "- 복분자동결건조분말: 항산화에 도움을 줄 수 있음\n"
        "- 작약추출물등복합물: 위 건강에 도움을 줄 수 있음"
    )


def test_assemble_omits_unverified_notice_for_active_intake_interaction() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=True,
        active_intake_interaction=True,
        unsupported_pairs=["등록약 ↔ 비타민 D"],
    )

    assert "확인하지 못한 조합" not in answer


def test_supplement_goal_details_keep_each_ingredient_attached_to_its_function() -> None:
    base = RetrievedKnowledgeChunk(
        point_id="sleep-function",
        chunk_id="z" * 64,
        content="원료 A는 수면의 질 개선에 도움을 줄 수 있습니다.",
        embedding_text="원료 A 수면",
        token_count=20,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="public",
            document_id="sleep",
            title="수면 기능",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            ingredient_names=["원료 A"],
            dataset_version="test",
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="z" * 64,
        ),
    )
    second = base.model_copy(
        update={
            "content": "원료 B는 긴장 완화에 도움을 줄 수 있습니다.",
            "metadata": base.metadata.model_copy(update={"ingredient_names": ["원료 B"]}),
        }
    )
    background = base.model_copy(
        update={
            "content": "수면은 중요한 생리 현상입니다.",
            "metadata": base.metadata.model_copy(update={"ingredient_names": []}),
        }
    )
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[background, base, base, second],
        interaction_question=False,
        functional_goal_title="숙면",
        functional_goal_details=True,
    )
    assert answer == (
        "**수면의 질 개선 관련 기능성 원료**\n\n💪🏻 **영양제 정보**\n"
        "- 원료 A: 수면의 질 개선에 도움을 줄 수 있음\n"
        "- 원료 B: 긴장 완화에 도움을 줄 수 있음"
    )


def test_assemble_groups_adverse_case_report_into_event_and_detail_sections() -> None:
    event_chunk = RetrievedKnowledgeChunk(
        point_id="doxazosin-event",
        chunk_id="f" * 64,
        content="독사조신 복용 뒤 심한 어지러움이 보고됐습니다.",
        embedding_text="독사조신 심한 어지러움 이상사례",
        token_count=20,
        similarity_score=0.83,
        metadata=KnowledgeChunkMetadata(
            source_id="drug-safety-report",
            document_id="doxazosin-case",
            title="독사조신 이상사례 보고",
            provider="의약품 안전기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.ADVERSE_CASE_REPORT,
            dataset_version="knowledge-full-v16-te3large",
            drug_names=["독사조신"],
            section_type=KnowledgeSectionType.ADVERSE_EVENT,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="f" * 64,
        ),
    )
    detail_chunk = event_chunk.model_copy(
        update={
            "point_id": "doxazosin-detail",
            "chunk_id": "g" * 64,
            "content": "증상 발생 시점과 함께 복용한 약을 검토했습니다.",
            "metadata": event_chunk.metadata.model_copy(
                update={
                    "section_type": KnowledgeSectionType.ASSESSMENT,
                    "chunk_index": 1,
                    "content_hash": "g" * 64,
                }
            ),
        }
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[event_chunk, detail_chunk],
        interaction_question=False,
        response_subject="독사조신",
        adverse_reaction_question=True,
    )

    assert answer.startswith("🩻 **부작용 보고서**")
    assert "**이상사례**\n- 독사조신 복용 뒤 심한 어지러움이 보고됐습니다." in answer
    assert "**추가설명**\n- 증상 발생 시점과 함께 복용한 약을 검토했습니다." in answer
    assert "공공자료 추가 설명" not in answer


def test_assemble_adds_specific_member_choices_for_ingredient_family() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
        ingredient_family=SupplementIngredientFamily(
            canonical_name="비타민 B",
            member_names=[
                "비타민 B1(티아민)",
                "비타민 B6(피리독신)",
                "비타민 B12(코발라민)",
            ],
            search_terms=["비타민 B군"],
        ),
    )

    assert "비타민 B는 여러 성분을 묶어 부르는 이름" in answer
    assert "비타민 B1(티아민), 비타민 B6(피리독신), 비타민 B12(코발라민)" in answer
    assert "성분명을 포함해 다시 질문" in answer


def test_assemble_separates_medication_and_supplement_information_with_a_blank_line() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=10,
                    name="와파린",
                    dose="1정",
                    times_per_day=1,
                    days=7,
                )
            ],
            supplements=[
                ActiveSupplement(
                    registration_id=1,
                    supplement_nutrient_id=1,
                    name="비타민 K",
                    dose_amount="1",
                    dose_unit="정",
                    start_date="2026-09-09",
                )
            ],
        ),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "사용자 확정 복약정보" not in answer
    assert "💊 **복약정보**\n- 와파린\n\n💪🏻 **영양제 정보**\n- 비타민 K · 1정" in answer
    assert "1정" not in answer.split("💪🏻 **영양제 정보**", maxsplit=1)[0]
    assert "1일 1회" not in answer
    assert "7일" not in answer


def test_context_header_keeps_every_registration_even_when_names_collide() -> None:
    """머리말은 확정 사실이다. 이름이 같다고 합치면 등록 하나의 복용량이 통째로 사라진다."""
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            supplements=[
                ActiveSupplement(
                    registration_id=index,
                    supplement_nutrient_id=index,
                    name=name,
                    dose_amount=dose,
                    dose_unit="정",
                    start_date="2026-09-09",
                )
                for index, (name, dose) in enumerate(
                    [("비타 D 2000(120캡슐)", "1"), ("비타 D 2000(60캡슐)", "2")], start=1
                )
            ],
        ),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "- 비타 D 2000(120캡슐) · 1정" in answer
    assert "- 비타 D 2000(60캡슐) · 2정" in answer


def test_assemble_formats_active_intake_as_markdown_sections() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=10,
                    name="와파린",
                    dose="1정",
                )
            ],
            supplements=[
                ActiveSupplement(
                    registration_id=1,
                    supplement_nutrient_id=1,
                    name="비타민 K",
                    dose_amount="1",
                    dose_unit="정",
                    start_date="2026-09-09",
                )
            ],
        ),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert answer.startswith("💊 **복약정보**\n- 와파린")
    assert "와파린 · 1정" not in answer
    assert "\n\n💪🏻 **영양제 정보**\n- 비타민 K · 1정" in answer


def test_assemble_labels_active_intake_interactions_separately() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[
            InteractionRuleFact(
                interaction_rule_id=1,
                pair_key="DRUG:와파린|SUPPLEMENT:비타민 K",
                pair_type="DRUG_SUPPLEMENT",
                left_name="와파린",
                right_name="비타민 K",
                risk_level="CAUTION",
                effect_texts=["약효에 영향을 줄 수 있어 섭취량을 일정하게 유지해야 합니다."],
            )
        ],
        chunks=[],
        interaction_question=True,
    )

    assert "🔁 **복약정보와 상호작용**" in answer
    assert "- 와파린 ↔ 비타민 K: 약효에 영향을 줄 수 있어 섭취량을 일정하게 유지해야 합니다." in answer
    assert "☑️ **확인하지 못한 조합**" not in answer


def test_assemble_labels_unverified_interaction_without_confirmed_heading() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=True,
    )

    assert "🔁 **확인된 상호작용**" not in answer
    assert "☑️ **확인하지 못한 조합**" in answer
    assert "현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다." in answer
    assert "확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다." in answer


def test_assemble_separates_question_interaction_from_active_medication_names() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            medications=[
                ActiveMedication(
                    medication_id=1,
                    care_episode_id=10,
                    name="세레콕시브캡슐200mg",
                )
            ],
        ),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=True,
        question_interaction_pairs=[
            MedicationInteractionQueryPair(
                left_name="타이레놀",
                right_name="마그네슘",
                pair_type="DRUG_SUPPLEMENT",
                pair_key="a" * 64,
            )
        ],
    )

    assert "💊 **복약정보**\n- 세레콕시브캡슐200mg\n\n---\n\n🔁 **질문 상호작용**" in answer
    assert "**[타이레놀-마그네슘]**" in answer
    assert "- 현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 못했습니다." in answer
    assert "세레콕시브캡슐200mg ↔" not in answer


def test_assemble_places_verified_question_interaction_content_under_its_pair() -> None:
    pair = MedicationInteractionQueryPair(
        left_name="타이레놀",
        right_name="마그네슘",
        pair_type="DRUG_SUPPLEMENT",
        pair_key="a" * 64,
    )
    chunk = RetrievedKnowledgeChunk(
        point_id="tylenol-magnesium-point",
        chunk_id="c" * 64,
        content="두 대상의 병용과 관련된 직접 근거입니다.",
        embedding_text="tylenol magnesium interaction",
        token_count=20,
        similarity_score=0.7,
        metadata=KnowledgeChunkMetadata(
            source_id="interaction-study",
            document_id="tylenol-magnesium",
            title="Tylenol and Magnesium Interaction",
            provider="학술 논문 발행처",
            access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version="knowledge-full-v1",
            drug_names=["타이레놀"],
            ingredient_names=["마그네슘"],
            interaction_pair_keys=[pair.pair_key],
            section_type=KnowledgeSectionType.INTERACTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="d" * 64,
        ),
    )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[chunk],
        interaction_question=True,
        question_interaction_pairs=[pair],
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.INTERACTION],
            covered_section_types=[KnowledgeSectionType.INTERACTION],
            verified_interaction_pair_keys=[pair.pair_key],
        ),
    )

    assert "**[타이레놀-마그네슘]**\n- 두 대상의 병용과 관련된 직접 근거입니다." in answer
    assert "검색된 상호작용 연구 근거" not in answer
    assert "확인하지 못했습니다" not in answer


def test_assemble_does_not_repeat_unverified_interaction_notice_as_missing_evidence() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=True,
        unsupported_pairs=["마그네슘 ↔ 아연"],
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.INTERACTION],
            missing_section_types=[KnowledgeSectionType.INTERACTION],
        ),
    )

    assert answer.count("☑️ **확인하지 못한 조합**") == 1
    assert "근거를 확인하지 못한 항목" not in answer


def test_assemble_uses_one_generic_notice_when_every_multi_entity_pair_is_unverified() -> None:
    pairs = [
        MedicationInteractionQueryPair(
            left_name=left_name,
            right_name=right_name,
            pair_type="SUPPLEMENT_SUPPLEMENT",
            pair_key=pair_key * 64,
        )
        for left_name, right_name, pair_key in (
            ("마그네슘", "아연", "a"),
            ("마그네슘", "칼슘", "b"),
            ("아연", "칼슘", "c"),
        )
    ]

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=True,
        question_interaction_pairs=pairs,
    )

    assert answer == (
        "☑️ **확인하지 못한 조합**\n"
        "현재 보유한 승인 규칙과 검색 근거에서는 해당 조합을 확인하지 "
        "못했습니다. 확인되지 않았다는 뜻이지 안전하다는 뜻은 아닙니다."
    )


def test_assemble_limits_public_chunks_to_requested_sections() -> None:
    """질문이 주의사항만 요청하면 검색된 효능 청크는 초안에 싣지 않는다."""

    def build_chunk(suffix: str, content: str, section_type: KnowledgeSectionType) -> RetrievedKnowledgeChunk:
        return RetrievedKnowledgeChunk(
            point_id=f"tylenol-{suffix}",
            chunk_id=suffix * 64,
            content=content,
            embedding_text=content,
            token_count=20,
            similarity_score=0.8,
            metadata=KnowledgeChunkMetadata(
                source_id="drug-encyclopedia",
                document_id=f"tylenol-{suffix}",
                title="타이레놀",
                provider="공공자료 제공기관",
                access_scope=KnowledgeAccessScope.PUBLIC,
                document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                dataset_version="knowledge-full-v1",
                ingredient_names=["아세트아미노펜"],
                section_type=section_type,
                page_start=1,
                page_end=1,
                chunk_index=0,
                content_hash=suffix * 64,
            ),
        )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[
            build_chunk("e", "감기로 인한 발열과 통증 완화에 사용합니다.", KnowledgeSectionType.FUNCTION),
            build_chunk("f", "음주 중에는 복용하지 마십시오.", KnowledgeSectionType.CAUTION),
        ],
        interaction_question=False,
        response_subject="타이레놀",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.CAUTION],
            covered_section_types=[KnowledgeSectionType.CAUTION],
        ),
    )

    assert "음주 중에는 복용하지 마십시오." in answer
    assert "발열과 통증 완화" not in answer


def test_assemble_keeps_cautions_even_when_only_efficacy_is_requested() -> None:
    """효능만 물었다는 이유로 금기를 지우면 주의사항이 없다는 뜻으로 읽힌다."""

    def build_chunk(suffix: str, content: str, section_type: KnowledgeSectionType) -> RetrievedKnowledgeChunk:
        return RetrievedKnowledgeChunk(
            point_id=f"tylenol-{suffix}",
            chunk_id=suffix * 64,
            content=content,
            embedding_text=content,
            token_count=20,
            similarity_score=0.8,
            metadata=KnowledgeChunkMetadata(
                source_id="drug-encyclopedia",
                document_id=f"tylenol-{suffix}",
                title="타이레놀",
                provider="공공자료 제공기관",
                access_scope=KnowledgeAccessScope.PUBLIC,
                document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
                dataset_version="knowledge-full-v1",
                ingredient_names=["아세트아미노펜"],
                section_type=section_type,
                page_start=1,
                page_end=1,
                chunk_index=0,
                content_hash=suffix * 64,
            ),
        )

    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[
            build_chunk("e", "감기로 인한 발열과 통증 완화에 사용합니다.", KnowledgeSectionType.FUNCTION),
            build_chunk("f", "중증 간장애 환자는 복용하지 마십시오.", KnowledgeSectionType.CAUTION),
        ],
        interaction_question=False,
        response_subject="타이레놀",
        evidence_coverage=MedicationEvidenceCoverage(
            requested_section_types=[KnowledgeSectionType.FUNCTION],
            covered_section_types=[KnowledgeSectionType.FUNCTION],
        ),
    )

    assert "발열과 통증 완화" in answer
    assert "중증 간장애 환자는 복용하지 마십시오." in answer


CROSSCHECK_PAIR = MedicationInteractionQueryPair(
    left_name="와파린",
    right_name="비타민 K",
    pair_type=InteractionPairType.DRUG_SUPPLEMENT,
    pair_key="d" * 64,
)


def test_verified_crosscheck_pair_is_reported_with_its_approved_rule() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[
            InteractionRuleFact(
                interaction_rule_id=1,
                pair_key=CROSSCHECK_PAIR.pair_key,
                pair_type="DRUG_SUPPLEMENT",
                left_name="와파린",
                right_name="비타민 K",
                risk_level="CONTRAINDICATED",
                effect_texts=["비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다."],
            )
        ],
        chunks=[],
        interaction_question=False,
        crosscheck_pairs=[CROSSCHECK_PAIR],
        evidence_coverage=MedicationEvidenceCoverage(
            verified_crosscheck_pair_keys=[CROSSCHECK_PAIR.pair_key],
        ),
    )

    assert "🔁 **복약정보와 상호작용**" in answer
    assert "비타민 K는 와파린의 항응고 효과를 감소시킬 수 있습니다." in answer


def test_unverified_crosscheck_pair_is_not_mentioned_at_all() -> None:
    """확인하지 못한 조합을 언급하면 사용자가 묻지 않은 추측이 된다."""
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
        crosscheck_pairs=[CROSSCHECK_PAIR],
        evidence_coverage=MedicationEvidenceCoverage(verified_crosscheck_pair_keys=[]),
    )

    assert "복약정보와 상호작용" not in answer
    assert "와파린" not in answer


def test_supplement_lines_state_the_scope_of_the_public_nutrient_data() -> None:
    """자료가 담는 성분은 제품 표시사항의 일부다. 밝히지 않으면 표시된 것이 전부로 읽힌다."""
    supplement = ActiveSupplement(
        registration_id=1,
        supplement_nutrient_id=1,
        name="코랄칼슘",
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 9, 1),
        nutrients=[SupplementNutrientAmount(name="칼슘", amount="400", unit="mg")],
    )

    lines = MedicationAnswerAssembler.supplement_intake_lines([supplement])

    assert lines[0] == "- 코랄칼슘 · 칼슘 400mg"
    # 기준을 밝히지 않으면 400mg이 라벨 함량인지 하루 섭취량인지 알 수 없다.
    assert "등록한 1회 복용량과 하루 복용 횟수로 환산한 값" in lines[-1]
    assert "제품 표시사항을 확인하세요" in lines[-1]


def test_supplement_lines_stay_unchanged_without_recorded_amounts() -> None:
    supplement = ActiveSupplement(
        registration_id=1,
        supplement_nutrient_id=1,
        name="루테인",
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 9, 1),
    )

    lines = MedicationAnswerAssembler.supplement_intake_lines([supplement])

    assert lines == ["- 루테인"]


def build_supplement(name: str, *, nutrients: list[SupplementNutrientAmount] | None = None) -> ActiveSupplement:
    return ActiveSupplement(
        registration_id=1,
        supplement_nutrient_id=1,
        name=name,
        dose_amount="1",
        dose_unit="정",
        start_date=date(2026, 9, 1),
        nutrients=nutrients or [],
    )


def test_intake_header_never_carries_nutrient_amounts() -> None:
    """머리말은 상호작용·복약 질문에도 붙는다. 성분을 넣으면 묻지 않은 정보가 따라간다."""
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(
            user_id=1,
            supplements=[
                build_supplement("코랄칼슘", nutrients=[SupplementNutrientAmount(name="칼슘", amount="400", unit="mg")])
            ],
        ),
        guide=None,
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "칼슘 400mg" not in answer
    assert "제품 표시사항을 확인하세요" not in answer


def test_same_named_products_are_listed_once_without_shifting_amounts() -> None:
    """괄호만 다른 동명 제품이 있으면, 한 제품의 함량이 다른 이름 옆에 붙을 수 있다."""
    lines = MedicationAnswerAssembler.supplement_intake_lines(
        [
            build_supplement(
                "비타 D 2000(120캡슐)",
                nutrients=[SupplementNutrientAmount(name="비타민 D", amount="50", unit="μg")],
            ),
            build_supplement(
                "비타 D 2000(60캡슐)",
                nutrients=[SupplementNutrientAmount(name="비타민 D", amount="25", unit="μg")],
            ),
        ]
    )

    assert lines[0] == "- 비타 D 2000 · 비타민 D 50μg"
    assert len([line for line in lines if line.startswith("- 비타 D 2000")]) == 1


def test_omega_amounts_state_that_they_come_from_total_fat() -> None:
    lines = MedicationAnswerAssembler.supplement_intake_lines(
        [
            build_supplement(
                "프리미엄 오메가-3",
                nutrients=[SupplementNutrientAmount(name="오메가-3", amount="1", unit="g")],
            )
        ]
    )

    assert "총지방으로 기록된 값" in lines[-1]


def test_omega_notice_is_bound_to_the_shared_nutrient_name() -> None:
    """이름이 어긋나면 `총지방으로 기록된 값` 안내가 조용히 사라진다."""
    lines = MedicationAnswerAssembler.supplement_intake_lines(
        [
            build_supplement(
                "프리미엄 오메가-3",
                nutrients=[SupplementNutrientAmount(name=OMEGA_NUTRIENT_NAME, amount="1", unit="g")],
            )
        ]
    )

    assert "총지방으로 기록된 값" in lines[-1]
