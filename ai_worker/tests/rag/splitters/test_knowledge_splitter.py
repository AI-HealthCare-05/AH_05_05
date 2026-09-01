from pathlib import Path

import pytest

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.parsers.supplement_code_parser import (
    SupplementCodeParser,
)
from ai_worker.rag.splitters.knowledge_splitter import (
    ChunkingPolicy,
    KnowledgeSplitter,
    WordTokenCounter,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
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
        "원료 (가) 피리독신염산염 (Pyridoxine Hydrochloride)\n"
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
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
    ]
    assert "분류: 제품의 요건 > 일일섭취량" in chunks[2].content
    assert "일일섭취량: 0.45~67 mg" in chunks[2].content
    assert "[성분] 비타민 B6" in chunks[2].embedding_text
    assert "[섹션] 제품의 요건 > 일일섭취량" in chunks[2].embedding_text
    assert all("성분: 비타민 B6" in chunk.content for chunk in chunks)
    assert all(chunk.content.strip() not in {"제조기준", "제품의 요건"} for chunk in chunks)


def test_split_supplement_code_separates_extracted_hierarchy() -> None:
    page = build_page(
        "1-10\n"
        "비타민 B6\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 피리독신염산염( ) Pyridoxine Hydrochloride)(\n"
        "나( ) 식품원료를 사용하여 비타민 B6를 보충할 수 있도록 제조 ・ 가공한 것\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가지며 이미(1) : ・ 이취가 없어야 함\n"
        "비타민 (2) B 6 표시량의 : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 단백질 및 아미노산 이용에 필요( )\n"
        "나 혈액의 호모시스테인 수준을 정상으로 유지하는데 필요( )\n"
        "일일섭취량 (2) : 0.45 ~ 67 mg\n"
        "섭취 시 주의사항 (3)\n"
        ": 손발 따끔거림 작열감 또는 저림 등의 이상사례 발생 시 섭취를 중단하고 전문가와 상담할 것\n"
        "시험법4)\n"
        "성상 제 성상시험법(1) : 4. 2-7"
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.INGREDIENT,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
    ]
    assert all("성분: 비타민 B6" in chunk.content for chunk in chunks)
    assert all("분류: 규격" not in chunk.content for chunk in chunks)
    assert "시험법" not in chunks[-1].content
    assert "단백질 및 아미노산 이용에 필요" in chunks[1].content
    assert "일일섭취량: :" not in chunks[2].content
    assert "섭취 시 주의사항: :" not in chunks[3].content


def test_parse_supplement_code_restores_standard_numbered_items() -> None:
    page = build_page(
        "비타민 B6\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가지며 이미(1) : ・ 이취가 없어야 함\n"
        "비타민 (2) B 6 표시량의 : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 단백질 및 아미노산 이용에 필요\n"
        "일일섭취량 (2) : 0.45 ~ 67 mg\n"
        "시험법4)\n"
        "성상 제4 시험법"
    )

    sections, _ = SupplementCodeParser().parse([page])

    standard = next(section for section in sections if section.section_type == KnowledgeSectionType.STANDARD)
    assert "규격:\n(1) 성상: 고유의 색택과 향미를 가지며 이미·이취가 없어야 함" in standard.content
    assert "(2) 비타민 B6: 표시량의 80 ~ 150%" in standard.content
    assert "(3) 대장균군: 음성" in standard.content


def test_parse_supplement_code_restores_displaced_ingredient_in_standard() -> None:
    page = build_page(
        "비타민 A\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가지며 이미(1) : ・ 이취가 없어야 함\n"
        "비타민 표시량의 (2) A : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요\n"
        "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
        "시험법4)\n"
        "성상 제4 시험법",
        title="비타민 A",
    )

    sections, _ = SupplementCodeParser().parse([page])

    standard = next(section for section in sections if section.section_type == KnowledgeSectionType.STANDARD)
    assert "(2) 비타민 A: 표시량의 80 ~ 150%" in standard.content
    assert "표시량의 A:" not in standard.content


def test_split_supplement_code_repairs_safe_parenthesis_and_punctuation() -> None:
    page = build_page(
        "비타민 B6\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 피리독신염산염( ) Pyridoxine Hydrochloride)(\n"
        "나 식품원료를 사용하여 제조 ・\n"
        "가공한 것\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐(1) :\n"
        "비타민 B6 표시량의 80 ~ 150%(2) :\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 단백질 및 아미노산 이용에 필요( )\n"
        "일일섭취량 (2) : 0.45 ~ 67 mg\n"
        "섭취 시 주의사항 (3)\n"
        "손발 저림 발생 시 섭취를 ,\n"
        "중단하고 전문가와 상담할 것\n"
        "시험법4)\n"
        "성상 제4 시험법"
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    ingredient = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.INGREDIENT)
    function = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.FUNCTION)
    caution = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.CAUTION)
    assert "피리독신염산염 (Pyridoxine Hydrochloride)" in ingredient.content
    assert "제조·가공한 것" not in ingredient.content
    assert "( )" not in function.content
    assert "섭취를 중단하고" in caution.content
    assert "섭취를 ," not in caution.content


def test_split_supplement_code_restores_verified_vitamin_a_ingredient_text() -> None:
    page = build_page(
        "비타민 A\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 레티닐 팔미트산염 (Retinyl Palmitate)\n"
        "다 식품원료를 사용하여 비타민 를 보충할 수 있도록 제조( ) A ･ 가공\n"
        "한 것\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐(1) :\n"
        "비타민 표시량의 (2) A : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요\n"
        "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
        "시험법4)\n"
        "성상 제4 시험법",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    ingredient = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.INGREDIENT)
    assert "(가) 레티닐 팔미트산염 (Retinyl Palmitate)" in ingredient.content
    assert "식품원료를 사용하여" not in ingredient.content
    assert "비타민 를" not in ingredient.content
    assert "제조 A·가공" not in ingredient.content


def test_split_supplement_code_does_not_convert_ordinary_korean_to_item_label() -> None:
    page = build_page(
        "비타민 A\n"
        "제조기준1)\n"
        "원료(1)\n"
        "나 유성비타민 A (Vitamin A in Oil)\n"
        "의 형태로 사용\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐(1) :\n"
        "비타민 표시량의 (2) A : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요\n"
        "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
        "시험법4)\n"
        "성상 제4 시험법",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    ingredient = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.INGREDIENT)
    assert "(나) 유성비타민 A (Vitamin A in Oil)" in ingredient.content
    assert "의 형태로 사용" not in ingredient.content
    assert "(의) 형태로 사용" not in ingredient.content


def test_split_supplement_code_keeps_only_named_ingredient_pairs() -> None:
    page = build_page(
        "비타민 A\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 레티닐 팔미트산염 (Retinyl Palmitate)\n"
        "나 레티닐 아세트산염 (Retinyl Acetate)\n"
        "참고 설명은 검색 대상이 아님\n"
        "다 식품원료를 사용하여 비타민 A를 보충할 수 있도록 제조·가공한 것\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐(1) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요\n"
        "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
        "시험법4)\n"
        "성상 제4 시험법",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    ingredient = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.INGREDIENT)
    assert ingredient.content.splitlines()[3:] == [
        "(가) 레티닐 팔미트산염 (Retinyl Palmitate)",
        "(나) 레티닐 아세트산염 (Retinyl Acetate)",
    ]


def test_split_supplement_code_excludes_manufacturing_rules_and_standard() -> None:
    page = build_page(
        "비타민 A\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 레티닐 팔미트산염 (Retinyl Palmitate)\n"
        "나 레티닐 아세트산염 (Retinyl Acetate)\n"
        "다 식품원료를 사용하여 비타민 A를 보충할 수 있도록 제조·가공한 것\n"
        "비타민 보충의 목적으로 비타민 원료를 (2) A A\n"
        "혼합하여 사용할 수 있음\n"
        "(3) 베타카로틴의 비타민 전환계수\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐(1) :\n"
        "비타민 표시량의 (2) A : 80 ~ 150%\n"
        "대장균군 음성(3) :\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요\n"
        "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
        "시험법4)\n"
        "성상 제4 시험법",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.INGREDIENT,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
    ]
    ingredient = chunks[0]
    assert "(가) 레티닐 팔미트산염 (Retinyl Palmitate)" in ingredient.content
    assert "(나) 레티닐 아세트산염 (Retinyl Acetate)" in ingredient.content
    assert "(다) 식품원료" not in ingredient.content
    assert "A A" not in ingredient.content
    assert "전환계수" not in ingredient.content
    assert all("분류: 규격" not in chunk.content for chunk in chunks)


def test_split_supplement_code_repairs_displaced_microgram_symbol() -> None:
    page = build_page(
        "비타민 A\n"
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 어두운 곳에서 시각 적응을 위해 필요( )\n"
        "일일섭취량 (2) : 210 ~ 1,000 g RAE (699.93μ ~ 3,333 IU)\n"
        "시험법4)\n"
        "성상 제 성상시험법(1) : 4. 2-7",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    daily_intake = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.DAILY_INTAKE)
    assert "210 ~ 1,000 μg RAE (699.93 ~ 3,333 IU)" in daily_intake.content


def test_split_supplement_code_resolves_numbered_references() -> None:
    page = build_page(
        "비타민 A\n"
        "1) 제조기준\n"
        "(1) 원료\n"
        "(가) 레티닐 팔미트산염 (Retinyl Palmitate)\n"
        "(나) 레티닐 아세트산염 (Retinyl Acetate)\n"
        "3) 제품의 요건\n"
        "(2) 일일섭취량\n"
        "(가) 1). (1). (가) 및 (나)의 경우: 0.42~7 mg\n"
        "4) 시험법\n"
        "(1) 성상시험법",
        title="비타민 A",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    daily_intake = next(chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.DAILY_INTAKE)
    assert "참조 내용:" in daily_intake.content
    assert "레티닐 팔미트산염" in daily_intake.content
    assert "레티닐 아세트산염" in daily_intake.content


def test_split_supplement_code_preserves_source_page_ranges() -> None:
    first_page = build_page(
        "비타민 B6\n"
        "제조기준1)\n"
        "원료(1)\n"
        "가 피리독신염산염 (Pyridoxine Hydrochloride)\n"
        "규격2)\n"
        "성상 고유의 색택과 향미를 가짐",
        page_number=1,
    )
    second_page = build_page(
        "제품의 요건3)\n"
        "기능성 내용(1)\n"
        "가 단백질 및 아미노산 이용에 필요\n"
        "일일섭취량 (2) : 0.45 ~ 67 mg\n"
        "시험법4)\n"
        "성상 제4 시험법",
        page_number=2,
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([first_page, second_page])

    page_ranges = {
        chunk.metadata.section_type: (
            chunk.metadata.page_start,
            chunk.metadata.page_end,
        )
        for chunk in chunks
    }
    assert page_ranges[KnowledgeSectionType.INGREDIENT] == (1, 1)
    assert page_ranges[KnowledgeSectionType.FUNCTION] == (2, 2)
    assert page_ranges[KnowledgeSectionType.DAILY_INTAKE] == (2, 2)


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


def test_recursive_split_merges_tiny_tail_when_union_fits_hard_limit() -> None:
    previous = " ".join(f"본문{index}" for index in range(580))
    tail = " ".join(f"꼬리{index}" for index in range(18))
    content = f"{previous} {tail}"
    tail_start = len(previous) + 1
    splitter = KnowledgeSplitter(token_counter=WordTokenCounter())

    merged = splitter._merge_small_fragments(
        content,
        [
            (previous, 0, len(previous)),
            (tail, tail_start, len(content)),
        ],
        ChunkingPolicy(
            target_min_tokens=250,
            hard_max_tokens=600,
            overlap_tokens=40,
        ),
    )

    assert merged == [(content, 0, len(content))]


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


def test_split_excludes_decorated_korean_references() -> None:
    page = build_page(
        "개요 과민성대장증후군의 주요 내용을 설명합니다.\n◘ 참고문헌 ◘\n1. 검색 근거로 사용하지 않을 참고문헌입니다.",
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="과민성대장증후군 팜리뷰",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert "참고문헌" not in chunks[0].content


def test_split_excludes_drug_food_publication_colophon() -> None:
    page = build_page(
        "의약품-식품간 상호작용 요약서\n"
        "와파린과 비타민 K 섭취량의 관계를 설명합니다.\n"
        "발 행 일\n"
        "2016년 9월 30일\n"
        "발행기관 식품의약품안전평가원",
        document_type=KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        title="약과 음식 상호작용 안내서",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert "와파린" in chunks[0].content
    assert "발행기관" not in chunks[0].content


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


def test_split_adds_interaction_evidence_metadata_to_embedding_text() -> None:
    page = build_page(
        ("Results A crossover single-meal study measured calcium and iron absorption in postmenopausal women."),
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Calcium and iron absorption--mechanisms and public health relevance",
    )

    chunk = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])[0]

    assert chunk.metadata.ingredient_names == ["칼슘", "철분"]
    assert chunk.metadata.interaction_type == "SUPPLEMENT_SUPPLEMENT"
    assert chunk.metadata.evidence_level == KnowledgeEvidenceLevel.CLINICAL_STUDY
    assert chunk.metadata.study_population == KnowledgeStudyPopulation.HUMAN
    assert "[상호작용] 영양제-영양제" in chunk.embedding_text
    assert "[근거 수준] 임상시험" in chunk.embedding_text
    assert "[연구 대상] 사람" in chunk.embedding_text


def test_split_uses_korean_label_for_drug_food_interaction() -> None:
    page = build_page(
        "펙소페나딘은 과일주스 대신 물과 함께 복용합니다.",
        document_type=KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        title="약과 음식 상호작용 안내서",
    )
    page = page.model_copy(
        update={
            "metadata": page.metadata.model_copy(
                update={
                    "drug_names": ["펙소페나딘"],
                    "ingredient_names": [],
                    "interaction_type": "DRUG_FOOD",
                    "interaction_pair_keys": ["f" * 64],
                }
            )
        }
    )

    chunk = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])[0]

    assert "[상호작용] 약-음식" in chunk.embedding_text


def test_split_applies_curated_interaction_annotation_end_to_end(
    tmp_path: Path,
) -> None:
    annotation_path = tmp_path / "interaction-annotations.yaml"
    annotation_path.write_text(
        """
schema_version: knowledge-interaction-annotations-v1
documents:
  - document_id: pilot-document
    pairs:
      - pair_type: DRUG_SUPPLEMENT
        left:
          kind: DRUG
          display_name: 와파린
          aliases: [와파린, warfarin]
        right:
          kind: SUPPLEMENT
          display_name: 비타민 K
          aliases: [비타민 K, vitamin k]
""".strip(),
        encoding="utf-8",
    )
    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(annotation_path)
    page = build_page(
        "Results Warfarin use requires attention to vitamin K intake.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin and vitamin K",
    )

    chunk = KnowledgeSplitter(
        token_counter=WordTokenCounter(),
        interaction_annotations=registry,
    ).split([page])[0]

    assert chunk.metadata.drug_names == ["와파린"]
    assert chunk.metadata.ingredient_names == ["비타민 K"]
    assert chunk.metadata.interaction_type == "DRUG_SUPPLEMENT"
    assert len(chunk.metadata.interaction_pair_keys) == 1
    assert "[상호작용] 약-영양제" in chunk.embedding_text


def test_split_preserves_curated_evidence_when_auto_classifier_is_unknown() -> None:
    page = build_page(
        "Results 근거 문장을 설명합니다.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="근거 수준 수동 검수 문서",
    )
    page = page.model_copy(
        update={
            "metadata": page.metadata.model_copy(
                update={
                    "evidence_level": KnowledgeEvidenceLevel.REVIEW_ARTICLE,
                    "study_population": KnowledgeStudyPopulation.NOT_APPLICABLE,
                }
            )
        }
    )

    chunk = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])[0]

    assert chunk.metadata.evidence_level == KnowledgeEvidenceLevel.REVIEW_ARTICLE
    assert chunk.metadata.study_population == KnowledgeStudyPopulation.NOT_APPLICABLE


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


def test_split_restores_attached_losartan_usage_and_caution_headings() -> None:
    page = build_page(
        (
            "요약로사르탄은 안지오텐신 수용체 차단제입니다.\n"
            "효능.효과고혈압 치료에 사용됩니다.\n"
            "용법제품과 환자 상태에 따라 용법이 달라집니다.\n"
            "경고임신 중에는 전문가에게 알려야 합니다.\n"
            "금기특정 환자에게 투여하지 않습니다.\n"
            "주의사항어지러움이 나타날 수 있습니다.\n"
            "부작용저혈압 등이 나타날 수 있습니다."
        ),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="로사르탄(losartan)",
        source_id="kpicia_drug_encyclopedia",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.SUMMARY,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.ADVERSE_EVENT,
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
