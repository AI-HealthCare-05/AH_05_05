from ai_worker.llm.assemblers.medication_answer_assembler import (
    MedicationAnswerAssembler,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationGuideFact,
)
from ai_worker.schemas.medication_search import SupplementIngredientFamily


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


def test_assemble_omits_empty_product_guide_fields() -> None:
    answer = MedicationAnswerAssembler().assemble(
        context=ActiveIntakeContext(user_id=1),
        guide=build_guide(),
        rules=[],
        chunks=[],
        interaction_question=False,
    )

    assert "사용법: 1일 1~2캡슐" in answer
    assert "함께 주의할 약·음식" not in answer


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
