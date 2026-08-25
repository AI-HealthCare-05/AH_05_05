import pytest

from ai_worker.rag.splitters.knowledge_splitter import (
    KnowledgeSplitter,
    WordTokenCounter,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgeSectionType,
)


def build_page(
    content: str,
    *,
    document_type: KnowledgeDocumentType = KnowledgeDocumentType.SUPPLEMENT_CODE,
    title: str = "비타민 B6",
    page_number: int = 1,
    source_id: str = "pilot-source",
) -> KnowledgePage:
    return KnowledgePage(
        content=content,
        page_number=page_number,
        metadata=KnowledgeMetadata(
            source_id=source_id,
            document_id="pilot-document",
            title=title,
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=document_type,
            dataset_version="pilot-v1",
            ingredient_names=[title],
        ),
    )


def test_split_uses_supplement_field_headings_before_size_split() -> None:
    page = build_page(
        "비타민 B6\n"
        "제조기준\n"
        "원료 피리독신염산염\n"
        "규격 표시량의 80~150%\n"
        "제품의 요건\n"
        "기능성 내용 단백질 및 아미노산 이용에 필요\n"
        "일일섭취량 0.45~67 mg\n"
        "섭취 시 주의사항 손발 저림이 생기면 전문가와 상담할 것\n"
        "시험법 제4 시험법"
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.INGREDIENT,
        KnowledgeSectionType.STANDARD,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.TEST_METHOD,
    ]
    assert chunks[3].content.startswith("일일섭취량")
    assert "[성분] 비타민 B6" in chunks[3].embedding_text
    assert "[섹션] 일일섭취량" in chunks[3].embedding_text
    assert all(chunk.content.strip() not in {"제조기준", "제품의 요건"} for chunk in chunks)


def test_split_uses_recursive_fallback_and_narrative_overlap() -> None:
    words = [f"단어{index}" for index in range(900)]
    page = build_page(
        "개요 " + " ".join(words),
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="과민성대장증후군 팜리뷰",
    )
    splitter = KnowledgeSplitter(token_counter=WordTokenCounter())

    chunks = splitter.split([page])

    assert len(chunks) > 1
    assert all(chunk.token_count <= 750 for chunk in chunks)
    first_words = set(chunks[0].content.split())
    second_words = set(chunks[1].content.split())
    assert first_words & second_words


def test_split_atomic_case_does_not_add_overlap() -> None:
    words = [f"사례{index}" for index in range(900)]
    page = build_page(
        "상세 사항 " + " ".join(words),
        document_type=KnowledgeDocumentType.ADVERSE_CASE_REPORT,
        title="독사조신 복용 후 어지러움",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) > 1
    assert set(chunks[0].content.split()).isdisjoint(set(chunks[1].content.split()))
    assert all(chunk.token_count <= 700 for chunk in chunks)


def test_split_excludes_research_references() -> None:
    page = build_page(
        "Abstract Calcium can inhibit iron absorption. "
        "Results The effect was temporary. "
        "Conclusion Long-term status did not change. "
        "References Example citation that must not be indexed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Calcium and Iron Absorption",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert all("Example citation" not in chunk.content for chunk in chunks)
    assert KnowledgeSectionType.REFERENCES not in {chunk.metadata.section_type for chunk in chunks}


def test_split_builds_deterministic_chunk_ids() -> None:
    page = build_page("기능성 내용 정상적인 면역기능에 필요")
    splitter = KnowledgeSplitter(token_counter=WordTokenCounter())

    first = splitter.split([page])
    second = splitter.split([page])

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_split_does_not_treat_interaction_word_in_sentence_as_heading() -> None:
    page = build_page(
        "약과 음식의 상호작용을 확인해야 합니다. 의약품과 식품 사이의 상호작용은 약효에 영향을 줄 수 있습니다.",
        document_type=KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        title="약과 음식 상호작용 안내서",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert chunks[0].metadata.section_type == KnowledgeSectionType.OTHER


def test_split_does_not_split_pharm_review_on_treatment_word() -> None:
    page = build_page(
        "개요 과민성대장증후군은 기능성 장애입니다. 치료약물의 선택은 증상에 따라 달라집니다.",
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="과민성대장증후군 팜리뷰",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert chunks[0].metadata.section_type == KnowledgeSectionType.OVERVIEW


def test_split_drops_symbol_only_extraction_artifact() -> None:
    words = " ".join(f"설명{index}" for index in range(800))
    page = build_page(
        f"개요 {words}\n\n◘",
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="팜리뷰",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) > 1
    assert all(chunk.content != "◘" for chunk in chunks)


def test_split_does_not_treat_inline_research_term_as_heading() -> None:
    filler = " ".join(f"설명{index}" for index in range(80))
    page = build_page(
        f"Abstract 연구 요약입니다. {filler} 이전 Results from prior work are mixed with current evidence.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="영양제 상호작용 연구",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.SUMMARY,
    ]


def test_split_recognizes_attached_drug_encyclopedia_headings() -> None:
    page = build_page(
        (
            "A형간염의개요질환에 관한 도입 설명입니다.\n"
            "요약백신의 핵심 정보를 설명합니다.\n"
            "약리작용면역반응을 이용합니다. 효능.효과12개월 이상에서 "
            "감염 예방에 사용됩니다.\n"
            "부작용가장 흔한 이상반응은 주사부위 통증입니다. "
            "주의사항• 이상반응이 있으면 전문가에게 알립니다.\n"
            "다른백신과의동시접종동시 접종 근거를 설명합니다."
        ),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="A형 간염 백신",
        source_id="kpicia_drug_encyclopedia",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.SUMMARY,
        KnowledgeSectionType.OVERVIEW,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.ADVERSE_EVENT,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.INTERACTION,
    ]


def test_split_does_not_treat_inline_attached_term_as_heading() -> None:
    page = build_page(
        ("개요 백신 정보를 설명합니다. 요약하면 접종 전 확인이 필요하고 부작용은 개인에 따라 다를 수 있습니다."),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="백신 안내",
        source_id="kpicia_drug_encyclopedia",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.OVERVIEW,
    ]


@pytest.mark.parametrize(
    "continuation",
    [
        "요약하면 접종 전 확인이 필요합니다.",
        "종류는 대상에 따라 달라집니다.",
        "부작용은 개인에 따라 다를 수 있습니다.",
    ],
)
def test_split_does_not_treat_line_start_prose_as_attached_heading(
    continuation: str,
) -> None:
    page = build_page(
        f"개요 백신 정보를 설명합니다.\n{continuation}",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="백신 안내",
        source_id="kpicia_drug_encyclopedia",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.OVERVIEW,
    ]


@pytest.mark.parametrize("document_type", list(KnowledgeDocumentType))
def test_default_tokenizer_respects_document_type_hard_limit(
    document_type: KnowledgeDocumentType,
) -> None:
    page = build_page(
        "안전한 복용 정보를 확인합니다. " * 1200,
        document_type=document_type,
        title="토큰 경계 검증 문서",
    )
    splitter = KnowledgeSplitter()

    chunks = splitter.split([page])
    hard_max = splitter.policy_for(document_type).hard_max_tokens

    assert len(chunks) > 1
    assert all(chunk.token_count <= hard_max for chunk in chunks)


def test_recursive_chunks_track_their_actual_page_range() -> None:
    first_page = build_page(
        "개요 " + " ".join(f"앞{index}" for index in range(500)),
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="페이지 범위 검증",
        page_number=1,
    )
    second_page = build_page(
        " ".join(f"뒤{index}" for index in range(500)),
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="페이지 범위 검증",
        page_number=2,
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([first_page, second_page])

    assert len(chunks) > 1
    assert chunks[-1].metadata.page_start == 2
    assert chunks[-1].metadata.page_end == 2
