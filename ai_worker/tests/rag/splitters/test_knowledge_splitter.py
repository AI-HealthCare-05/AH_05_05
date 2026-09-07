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
    KnowledgeBoundingBox,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgePageBlock,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
    KnowledgeTableRow,
)


def build_aspirin_warfarin_chunk(
    content: str,
    *,
    chunk_index: int,
    content_kind: KnowledgeContentKind = KnowledgeContentKind.TEXT,
) -> KnowledgeChunk:
    metadata = KnowledgeChunkMetadata(
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-3dd5c1de206c9a88",
        title="Aspirin and warfarin nutrient interactions",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
        section_type=KnowledgeSectionType.INTERACTION,
        page_start=1,
        page_end=1,
        chunk_index=chunk_index,
        content_hash=f"{chunk_index + 1:064x}",
        content_kind=content_kind,
    )
    return KnowledgeChunk(
        chunk_id=f"{chunk_index + 101:064x}",
        content=content,
        embedding_text=content,
        token_count=len(content.split()),
        metadata=metadata,
    )


def build_warfarin_review_chunk(
    content: str,
    *,
    chunk_index: int,
) -> KnowledgeChunk:
    chunk = build_aspirin_warfarin_chunk(
        content,
        chunk_index=chunk_index,
    )
    return chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "document_id": ("research_drug_nutrient_interactions-299edbe35f581616"),
                    "title": "Warfarin and supplement interactions",
                }
            )
        }
    )


def build_drug_vitamin_d_review_chunk(
    content: str,
    *,
    chunk_index: int,
    page_start: int = 1,
    page_end: int = 1,
) -> KnowledgeChunk:
    chunk = build_aspirin_warfarin_chunk(
        content,
        chunk_index=chunk_index,
    )
    return chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "document_id": ("research_drug_nutrient_interactions-80c3d674cbc86d03"),
                    "title": "Drug-vitamin D interactions",
                    "page_start": page_start,
                    "page_end": page_end,
                }
            )
        }
    )


def build_statins_vitamin_d_review_chunk(
    content: str,
    *,
    chunk_index: int,
    page_start: int = 1,
    page_end: int = 13,
) -> KnowledgeChunk:
    chunk = build_aspirin_warfarin_chunk(content, chunk_index=chunk_index)
    return chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "document_id": ("research_drug_nutrient_interactions-186668a2a92b533c"),
                    "title": "Statins, Vitamin D, and Cardiovascular Health",
                    "page_start": page_start,
                    "page_end": page_end,
                }
            )
        }
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


def build_research_page_with_table(
    *,
    table_rows: list[list[str]],
    table_title: str | None = None,
    table_super_headers: list[str] | None = None,
) -> KnowledgePage:
    headers = ["Ingredient", "Result"]
    table_content = "\n".join(
        " | ".join(f"{header}={cell}" for header, cell in zip(headers, row, strict=True)) for row in table_rows
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-table",
        title="Nutrient interaction study",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
        ingredient_names=["철분"],
        interaction_type="SUPPLEMENT_SUPPLEMENT",
    )
    return KnowledgePage(
        content=f"Results\n\n{table_content}",
        page_number=1,
        metadata=metadata,
        blocks=[
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TEXT,
                order=0,
                bbox=KnowledgeBoundingBox(
                    x0=10,
                    top=10,
                    x1=500,
                    bottom=50,
                ),
                content="Results\n본문 결과입니다.",
            ),
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TABLE,
                order=1,
                bbox=KnowledgeBoundingBox(
                    x0=10,
                    top=60,
                    x1=500,
                    bottom=200,
                ),
                content=table_content,
                headers=headers,
                rows=[KnowledgeTableRow(cells=row) for row in table_rows],
                column_count=2,
                table_title=table_title,
                table_super_headers=table_super_headers or [],
            ),
        ],
    )


def test_split_keeps_table_rows_whole_and_marks_content_kind() -> None:
    page = build_research_page_with_table(
        table_rows=[
            ["Calcium", "Reduced iron absorption"],
            ["Zinc", "Lower copper status"],
        ]
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    text_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TEXT]
    table_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
    assert len(text_chunks) == 1
    assert len(table_chunks) == 1
    assert "Ingredient=Calcium | Result=Reduced iron absorption" in (table_chunks[0].content)
    assert "Ingredient=Zinc | Result=Lower copper status" in (table_chunks[0].content)
    assert "Ingredient=Calcium" not in text_chunks[0].content


def test_split_preserves_table_context_as_chunk_metadata() -> None:
    page = build_research_page_with_table(
        table_rows=[["Calcium", "Reduced iron absorption"]],
        table_title="Table 2. Clinically relevant interactions",
        table_super_headers=["Human Studies"],
    )
    page = page.model_copy(update={"metadata": page.metadata.model_copy(update={"interaction_type": None})})

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    table_chunk = next(chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE)
    assert table_chunk.metadata.section_title == ("Table 2. Clinically relevant interactions")
    assert table_chunk.metadata.table_title == ("Table 2. Clinically relevant interactions")
    assert table_chunk.metadata.table_super_headers == ["Human Studies"]
    assert table_chunk.metadata.section_type == KnowledgeSectionType.INTERACTION
    assert "[표 제목] Table 2. Clinically relevant interactions" in (table_chunk.embedding_text)
    assert "[표 설명] Human Studies" in table_chunk.embedding_text


def test_split_uses_dni_table_title_for_every_grouped_chunk() -> None:
    repeated_result = " ".join(["observed"] * 500)
    page = build_research_page_with_table(
        table_rows=[
            ["Magnesium", repeated_result],
            ["Astaxanthin", repeated_result],
        ],
        table_title=("Table 2. Summary of clinically relevant DNIs with warfarin."),
        table_super_headers=["Human Studies"],
    )
    page = page.model_copy(update={"metadata": page.metadata.model_copy(update={"interaction_type": None})})

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    table_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
    assert len(table_chunks) == 2
    assert all(chunk.metadata.section_type == KnowledgeSectionType.INTERACTION for chunk in table_chunks)


def test_split_prioritizes_interaction_table_title_over_dose_column() -> None:
    page = build_research_page_with_table(
        table_rows=[["Pueraria lobata", "Dose dependent=Yes"]],
        table_title="HDS-drug interaction evidence studies (Table 1)",
    )
    page = page.model_copy(update={"metadata": page.metadata.model_copy(update={"interaction_type": None})})

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    table_chunk = next(chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE)
    assert table_chunk.metadata.section_type == KnowledgeSectionType.INTERACTION


def test_split_classifies_contraindication_relationship_table_as_caution() -> None:
    page = build_research_page_with_table(
        table_rows=[["Renal disease", "Magnesium"]],
        table_title=("Contraindication relationships for herbs and dietary supplements"),
    )
    page = page.model_copy(update={"metadata": page.metadata.model_copy(update={"interaction_type": None})})

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    table_chunk = next(chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE)
    assert table_chunk.metadata.section_type == KnowledgeSectionType.CAUTION


def test_split_does_not_break_an_oversized_table_row() -> None:
    oversized_result = " ".join(["result"] * 900)
    page = build_research_page_with_table(
        table_rows=[["Calcium", oversized_result]],
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    table_chunk = next(chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE)
    assert table_chunk.token_count > 800
    assert table_chunk.content.count("Ingredient=Calcium") == 1


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


def test_split_regulatory_drug_label_preserves_safety_sections() -> None:
    page = build_page(
        "1 INDICATIONS AND USAGE\n"
        "LEVO-T is indicated as replacement therapy.\n"
        "2 DOSAGE AND ADMINISTRATION\n"
        "Administer once daily on an empty stomach.\n"
        "5 WARNINGS AND PRECAUTIONS\n"
        "Overtreatment may increase cardiovascular risk.\n"
        "7 DRUG INTERACTIONS\n"
        "Calcium may reduce levothyroxine absorption.\n"
        "17 PATIENT COUNSELING INFORMATION\n"
        "Tell patients to take LEVO-T with water.",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.CAUTION,
    ]
    assert "Calcium may reduce" in chunks[3].content
    assert KnowledgeSplitter.policy_for(KnowledgeDocumentType.REGULATORY_DRUG_LABEL) == ChunkingPolicy(
        target_min_tokens=250,
        hard_max_tokens=600,
        overlap_tokens=40,
    )


def test_split_regulatory_subsections_keep_heading_with_its_body() -> None:
    page = build_page(
        "7 DRUG INTERACTIONS\n"
        "7.9 Anticoagulants (Oral)\nWarfarin response may be affected.\n"
        "7.10 Drug-Laboratory Test Interactions\n"
        "Changes in TBG concentration must be considered.\n"
        "Familial hyper- or hypo-thyroxine binding globulinemias have been described, "
        "with the incidence of TBG deficiency approximating 1 in 9000.\n"
        "8 USE IN SPECIFIC POPULATIONS\nPregnancy information follows.",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    laboratory_chunk = next(chunk for chunk in chunks if "7.10 Drug-Laboratory" in chunk.content)
    assert laboratory_chunk.metadata.section_type == KnowledgeSectionType.INTERACTION
    assert "TBG deficiency approximating 1 in 9000" in laboratory_chunk.content


def test_split_regulatory_pharmacokinetic_subheadings_preserve_boundaries() -> None:
    page = build_page(
        "12 CLINICAL PHARMACOLOGY\n"
        "Absorption\nAbsorption varies by fasting state.\n"
        "Distribution\nThyroid hormones are highly bound to plasma proteins.\n"
        "Elimination\n"
        "Metabolism\nT4 is slowly eliminated through sequential deiodination.\n"
        "Excretion\nThyroid hormones are excreted through bile and gut.",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    metabolism_chunk = next(chunk for chunk in chunks if "Metabolism" in chunk.content)
    assert metabolism_chunk.content.startswith("Elimination\nMetabolism")
    assert "sequential deiodination" in metabolism_chunk.content
    assert "Absorption varies" not in metabolism_chunk.content


def test_split_excludes_regulatory_overdosage_section() -> None:
    page = build_page(
        "10 OVERDOSAGE\nTreatment instructions that are outside chatbot scope.\n"
        "11 DESCRIPTION\nLEVO-T contains levothyroxine sodium.",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    combined = "\n".join(chunk.content for chunk in chunks)
    assert "Treatment instructions" not in combined
    assert "contains levothyroxine sodium" in combined


def test_split_regulatory_drug_label_recognizes_decorated_highlight_headings() -> None:
    page = build_page(
        "HIGHLIGHTS OF PRESCRIBING INFORMATION\n"
        "----------------------------INDICATIONS AND USAGE--------------------------\n"
        "LEVO-T is indicated as replacement therapy.\n"
        "---------------------------------DRUG INTERACTIONS---------------------------\n"
        "Calcium may reduce levothyroxine absorption.",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    section_types = [chunk.metadata.section_type for chunk in chunks]
    assert KnowledgeSectionType.FUNCTION in section_types
    assert KnowledgeSectionType.INTERACTION in section_types
    assert all("----------------" not in chunk.content for chunk in chunks)


def test_split_excludes_research_publication_back_matter() -> None:
    page = build_page(
        "Results\nWarfarin and nutrients require careful interpretation.\n"
        "Conclusions\nThe evidence remains limited.\n"
        "Author Contributions: A.B. wrote the manuscript.\n"
        "Funding: This research received no external funding.\n"
        "Conflicts of Interest: The authors declare no conflict.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    combined = "\n".join(chunk.content for chunk in chunks)
    assert "evidence remains limited" in combined
    assert "Author Contributions" not in combined
    assert "Conflicts of Interest" not in combined


def test_split_excludes_research_back_matter_without_colon() -> None:
    page = build_page(
        "Abstract\nThis systematic review evaluates levothyroxine interactions.\n"
        "Conclusion\nCalcium and iron may reduce levothyroxine absorption.\n"
        "Abbreviations\nLT4, levothyroxine; TSH, thyrotropin.\n"
        "Data Sharing Statement\nAll data are included in this article.\n"
        "Author Contributions\nAll authors reviewed the manuscript.\n"
        "Funding\nThis work was supported by a grant.\n"
        "Disclosure\nThe authors report no conflicts.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Levothyroxine interactions: a systematic review",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    combined = "\n".join(chunk.content for chunk in chunks)
    assert "Calcium and iron" in combined
    assert "Abbreviations" not in combined
    assert "Author Contributions" not in combined
    assert "Funding" not in combined


def test_split_excludes_research_publication_front_matter() -> None:
    page = build_page(
        "Citation: Example et al. Nutrients 2024.\n"
        "Copyright: © 2024 by the authors.\n"
        "Correspondence: author@example.org\n"
        "Abstract\nWarfarin and nutrient interactions were reviewed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert chunks[0].metadata.section_type == KnowledgeSectionType.SUMMARY
    assert "interactions were reviewed" in chunks[0].content
    assert "Citation:" not in chunks[0].content


def test_split_excludes_decorated_research_correspondence_front_matter() -> None:
    page = build_page(
        "David Renaud, Alexander Höller and Miriam Michel\n"
        "Institute of Nutritional Medicine\n"
        "* Correspondence: author@example.org\n"
        "Abstract\nWarfarin and nutrient interactions were reviewed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert chunks[0].metadata.section_type == KnowledgeSectionType.SUMMARY
    assert chunks[0].content.startswith("Abstract")
    assert "author@example.org" not in chunks[0].content


def test_split_keeps_structured_abstract_labels_in_one_summary_section() -> None:
    page = build_page(
        "Medications and Food Interfering with Levothyroxine\n"
        "Abstract\n"
        "Purpose: Levothyroxine bioavailability can be altered.\n"
        "Methods: Human studies were reviewed.\n"
        "Results: Calcium and iron interactions were reported.\n"
        "Conclusion: Clinicians should consider interactions.\n"
        "Keywords: L-T4, drug, interference\n"
        "Introduction\n"
        "Levothyroxine is widely prescribed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Medications and Food Interfering with Levothyroxine",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    summary_chunks = [chunk for chunk in chunks if chunk.metadata.section_type == KnowledgeSectionType.SUMMARY]
    assert len(summary_chunks) == 1
    assert "Purpose:" in summary_chunks[0].content
    assert "Methods:" in summary_chunks[0].content
    assert "Results:" in summary_chunks[0].content
    assert "Conclusion:" in summary_chunks[0].content
    assert "Keywords:" in summary_chunks[0].content
    assert any(
        chunk.metadata.section_type == KnowledgeSectionType.INTRODUCTION and "widely prescribed" in chunk.content
        for chunk in chunks
    )


def test_split_does_not_treat_interaction_phrase_in_keywords_as_heading() -> None:
    page = build_page(
        "Abstract\nDrug and vitamin D evidence was reviewed.\n"
        "Keywords: vitamin D; drug-nutrient interactions\n"
        "Introduction\nVitamin D is a steroid hormone precursor.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Drug-vitamin D interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.SUMMARY,
        KnowledgeSectionType.INTRODUCTION,
    ]
    assert chunks[0].content.endswith("Keywords: vitamin D; drug-nutrient interactions")
    assert chunks[1].content.startswith("Introduction")


def test_split_excludes_regulatory_manufacturer_block() -> None:
    page = build_page(
        "17 PATIENT COUNSELING INFORMATION\n"
        "Tell patients to take LEVO-T with water.\n"
        "Manufactured and Distributed by: Example Pharma LLC\n"
        "Revised: 08/2026",
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        title="LEVO-T prescribing information",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert "take LEVO-T with water" in chunks[0].content
    assert "Example Pharma" not in chunks[0].content


def test_split_recognizes_numbered_interaction_subsection() -> None:
    page = build_page(
        "2 Materials and Methods\nThe review method is described.\n"
        "4.2 Drug-Nutrient Interactions\n"
        "Warfarin and vitamin K evidence is summarized.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.METHODS,
        KnowledgeSectionType.INTERACTION,
    ]


def test_split_recognizes_generic_numbered_dni_heading() -> None:
    page = build_page(
        "2. Methods\nThe review method is described.\n"
        "4. ASA and DNIs\n"
        "Aspirin and nutrient interaction evidence is summarized.\n"
        "6. Discussion\nThe evidence remains limited.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Aspirin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.METHODS,
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.DISCUSSION,
    ]
    assert "Aspirin and nutrient" in chunks[1].content


def test_split_research_numbered_subsections_inherit_parent_section_type() -> None:
    page = build_page(
        "4. Warfarin and DNIs\n"
        "4.1.1. Water-Soluble Vitamins\n"
        "Vitamin B interactions are summarized here.\n"
        "4.1.2. Fat-Soluble Vitamins\n"
        "Vitamin K interactions are summarized here.\n"
        "6. Discussion\n"
        "The evidence remains limited.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.DISCUSSION,
    ]
    assert "Water-Soluble Vitamins" in chunks[0].content
    assert "Fat-Soluble Vitamins" not in chunks[0].content
    assert chunks[1].content.startswith("4.1.2. Fat-Soluble Vitamins")


def test_split_research_unnumbered_subheadings_inherit_parent_section() -> None:
    page = build_page(
        "Results\n"
        "Sucralfate\nSucralfate evidence is summarized. "
        + "Additional absorption evidence is summarized. "
        * 12
        + "Sucralfate was also evaluated in healthy volunteers.\n"
        "Bile Acid Sequestrants\nBile acid evidence is summarized.\n"
        "Phosphate Binders\nPhosphate binder evidence is summarized.\n"
        "Other Medications\nOther medication evidence is summarized.\n"
        "Medications Inducing Alterations in Mucosal Transport Processes\n"
        "Transport evidence is summarized.\n"
        "Discussion\nThe evidence remains limited.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Levothyroxine interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split(
        [page],
        verified_section_headings=[
            "Sucralfate",
            "Bile Acid Sequestrants",
            "Phosphate Binders",
            "Other Medications",
            "Medications Inducing Alterations in Mucosal Transport Processes",
        ],
    )

    assert [chunk.metadata.section_title for chunk in chunks] == [
        "Sucralfate",
        "Bile Acid Sequestrants",
        "Phosphate Binders",
        "Other Medications",
        "Medications Inducing Alterations in Mucosal Transport Processes",
        "Discussion",
    ]
    assert all(chunk.metadata.section_type == KnowledgeSectionType.RESULTS for chunk in chunks[:5])
    assert "Transport evidence" not in chunks[3].content
    assert "healthy volunteers" in chunks[0].content


def test_split_research_matches_verified_heading_wrapped_across_lines() -> None:
    page = build_page(
        "Results and Discussion\n"
        "Form responsible for adverse effects\n"
        "The product description was considered in causality assessment.\n"
        "Case reports and side-effects associated with\n"
        "PFS and botanical ingredients: a review of the\n"
        "top 14\n"
        "Only botanicals supported by at least ten reports were reviewed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Botanical supplement adverse effects",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split(
        [page],
        verified_section_headings=[
            "Form responsible for adverse effects",
            ("Case reports and side-effects associated with PFS and botanical ingredients: a review of the top 14"),
        ],
    )

    assert [chunk.metadata.section_title for chunk in chunks][-2:] == [
        "Form responsible for adverse effects",
        ("Case reports and side-effects associated with PFS and botanical ingredients: a review of the top 14"),
    ]
    assert chunks[-2].content.endswith("causality assessment.")
    assert chunks[-1].content.endswith("at least ten reports were reviewed.")


def test_split_research_separates_nested_other_drugs_from_catabolism() -> None:
    page = build_page(
        "Results\n"
        "Medications Altering the Catabolism of LT4\n"
        "In livers, T4 is degraded through several routes.\n"
        "Carbamazepine\nCarbamazepine is a drug that alters metabolism and may "
        "eliminate hypothyroid symptoms due to these drugs.\n"
        "Other Drugs\nMetformin\n"
        "The TSH suppression by metformin was reported in a case series.\n"
        "Food and Beverages\nFood interactions are summarized.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Levothyroxine interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split(
        [page],
        verified_section_headings=[
            "Medications Altering the Catabolism of LT4",
            "Other Drugs",
            "Food and Beverages",
        ],
    )

    catabolism = next(
        chunk for chunk in chunks if chunk.metadata.section_title == "Medications Altering the Catabolism of LT4"
    )
    other_drugs = next(chunk for chunk in chunks if chunk.metadata.section_title == "Other Drugs")
    assert "Carbamazepine is a drug" in catabolism.content
    assert "Other Drugs" not in catabolism.content
    assert "Metformin" in other_drugs.content
    assert "Food and Beverages" not in other_drugs.content


def test_split_research_top_level_heading_resets_inherited_section_type() -> None:
    page = build_page(
        "2. Methods\nThe review method is described.\n"
        "3. Defining the Hidden Hunger Essentiality\n"
        "Other important nutrients include two macronutrients.\n"
        "4. ASA and DNIs\nAspirin interactions are summarized.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Aspirin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.METHODS,
        KnowledgeSectionType.OTHER,
        KnowledgeSectionType.INTERACTION,
    ]


def test_split_connects_lowercase_sentence_across_page_boundary() -> None:
    first_page = build_page(
        "Other important nutrients include two macronutrients,",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Aspirin nutrient interactions",
        page_number=4,
    )
    second_page = build_page(
        "fatty acids and dietary amino acids, are also critical for metabolism.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Aspirin nutrient interactions",
        page_number=5,
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([first_page, second_page])

    assert len(chunks) == 1
    assert "two macronutrients, fatty acids" in chunks[0].content
    assert (chunks[0].metadata.page_start, chunks[0].metadata.page_end) == (4, 5)


def test_split_research_vitamin_subheadings_before_recursive_fallback() -> None:
    filler = " ".join(f"evidence{index}" for index in range(240))
    page = build_page(
        "4. Warfarin and DNIs\n"
        "4.1.1. Water-Soluble Vitamins\n"
        f"Thiamine (B1)\n{filler}.\n"
        f"Niacin (B3)\n{filler}.\n"
        f"Folate (B9)\n{filler}.\n"
        f"Cobalamins (B12)\n{filler}.\n"
        f"Ascorbic Acid (C)\n{filler}.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) > 1
    assert all(chunk.token_count <= 800 for chunk in chunks)
    assert all(chunk.metadata.section_title == "Water-Soluble Vitamins" for chunk in chunks)
    assert any(chunk.content.startswith("Cobalamins (B12)") for chunk in chunks)
    assert any("Ascorbic Acid (C)" in chunk.content for chunk in chunks)


def test_split_merges_heading_only_research_fragment_into_next_section() -> None:
    page = build_page(
        "1. Introduction\n"
        "1.1. Drug–Nutrient Interactions (DNIs)\n"
        "Medication and nutrients can affect each other through absorption.\n"
        "2. Methods\nThe review method is described.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Drug nutrient interactions",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert [chunk.metadata.section_type for chunk in chunks] == [
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.METHODS,
    ]
    assert chunks[0].content.startswith("1. Introduction")
    assert "Drug–Nutrient Interactions" in chunks[0].content


def test_split_excludes_decorated_korean_references() -> None:
    page = build_page(
        "개요 과민성대장증후군의 주요 내용을 설명합니다.\n◘ 참고문헌 ◘\n1. 검색 근거로 사용하지 않을 참고문헌입니다.",
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        title="과민성대장증후군 팜리뷰",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert "참고문헌" not in chunks[0].content


def test_split_does_not_resume_research_body_inside_references() -> None:
    page = build_page(
        "Conclusion The evidence remains limited.\n"
        "References\n"
        "1. Example A. Abstract P59: aspirin and niacin. Journal 2021.\n"
        "2. Example B. Results from a clinical study. Journal 2022.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Drug nutrient review",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    assert len(chunks) == 1
    assert chunks[0].metadata.section_type == KnowledgeSectionType.CONCLUSION
    assert "Abstract P59" not in chunks[0].content


def test_split_does_not_treat_inline_references_as_back_matter() -> None:
    page = build_page(
        "Results and Discussion\n"
        "Number of\n"
        "references due to interactions with conventional drugs\n"
        "Adverse effects due to interaction with nutrients or conventional drugs\n"
        "The interaction evidence remained available for clinical review.\n"
        "Conclusions\n"
        "Severe reactions were uncommon but were reported.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Botanical supplement adverse effects",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    content = "\n".join(chunk.content for chunk in chunks)
    assert "interaction evidence remained available" in content
    assert "Severe reactions were uncommon" in content


def test_split_accepts_verified_botanical_heading_with_attached_body() -> None:
    page = build_page(
        "Results and Discussion\n"
        "General findings from the review are described here.\n"
        "Ginkgo biloba L. (Ginkgo/maidenhair tree) The review identified bleeding reports.\n"
        "Glycine max (L.) Merr. (soybean) The review identified allergy reports.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Botanical supplement adverse effects",
    )
    page = page.model_copy(
        update={"metadata": page.metadata.model_copy(update={"source_id": "research_supplement_adverse_effects"})}
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split(
        [page],
        verified_section_headings=[
            "Ginkgo biloba L. (Ginkgo/maidenhair tree)",
            "Glycine max (L.) Merr. (soybean)",
        ],
    )

    assert any(chunk.content.startswith("Ginkgo biloba L. (Ginkgo/maidenhair tree)") for chunk in chunks)
    assert any(chunk.content.startswith("Glycine max (L.) Merr. (soybean)") for chunk in chunks)


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


def test_split_keeps_shared_table_substances_as_searchable_ingredients() -> None:
    page = build_research_page_with_table(
        table_rows=[
            [
                "Calcium carbonate; Calcium acetate; Calcium citrate",
                "Calcium supplement",
            ]
        ],
        table_title=("Summary of Mechanisms of Interfering Substances and Recommendations for Clinicians"),
    )

    table_chunk = next(
        chunk
        for chunk in KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])
        if chunk.metadata.content_kind == KnowledgeContentKind.TABLE
    )

    assert table_chunk.metadata.ingredient_names == [
        "Calcium carbonate",
        "Calcium acetate",
        "Calcium citrate",
    ]


def test_split_assigns_one_group_and_sequence_to_continued_table_pages() -> None:
    title = "Summary of Mechanisms of Interfering Substances and Recommendations for Clinicians"
    first = build_research_page_with_table(
        table_rows=[["Calcium carbonate", "Calcium supplement"]],
        table_title=title,
    )
    second = build_research_page_with_table(
        table_rows=[["Ferrous sulfate", "Iron supplement"]],
        table_title=title,
    ).model_copy(update={"page_number": 2})

    table_chunks = [
        chunk
        for chunk in KnowledgeSplitter(token_counter=WordTokenCounter()).split([first, second])
        if chunk.metadata.content_kind == KnowledgeContentKind.TABLE
    ]

    assert len(table_chunks) == 2
    assert table_chunks[0].metadata.table_group_id
    assert {chunk.metadata.table_group_id for chunk in table_chunks} == {table_chunks[0].metadata.table_group_id}
    assert [chunk.metadata.table_sequence for chunk in table_chunks] == [0, 1]


def test_split_connects_body_text_across_table_only_pages() -> None:
    before = build_page(
        "Results\nSamples were collected from the supernatant after",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Levothyroxine interaction review",
        page_number=3,
    )
    before.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=80),
            content=before.content,
        )
    ]
    table_page = build_research_page_with_table(
        table_rows=[["Calcium carbonate", "Calcium supplement"]],
        table_title="Interaction summary",
    ).model_copy(
        update={
            "page_number": 4,
            "metadata": before.metadata,
        }
    )
    table_page.blocks = [block for block in table_page.blocks if block.kind == KnowledgeContentKind.TABLE]
    after = build_page(
        "2-hour incubation and 10-min centrifugation.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Levothyroxine interaction review",
        page_number=9,
    )
    after.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=80),
            content=after.content,
        )
    ]

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([before, table_page, after])
    body = "\n".join(chunk.content for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TEXT)

    assert "supernatant after 2-hour incubation and 10-min centrifugation." in body


def test_split_connects_lowercase_continuation_across_text_blocks() -> None:
    page = build_page(
        "Results\nEvidence for interactions with conventional drugs was reviewed.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Botanical supplement adverse effects",
    )
    page.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=250, bottom=80),
            content="Results\nEvidence for interactions with conventional",
        ),
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=1,
            bbox=KnowledgeBoundingBox(x0=300, top=10, x1=550, bottom=80),
            content="drugs; assessment of causality was reported.",
        ),
    ]

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    content = "\n".join(chunk.content for chunk in chunks)
    assert "conventional drugs; assessment of causality" in content
    assert "conventional\n\ndrugs" not in content


def test_split_research_recognizes_wiley_pipe_numbered_headings() -> None:
    page = build_page(
        "Conclusion\nSummary.\n\n"
        "KEYWORDS\nadverse event, bleeding, warfarin\n\n"
        "1 | INTRODUCTION\nIntroduction body.\n\n"
        "2 | METHODS\n"
        "2.1 | Search strategy\nSearch body.\n\n"
        "2.2 | Study inclusion\nInclusion body.\nresults of de-challenge were assessed.\n\n"
        "2.5 | Data synthesis\nSynthesis body.",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Warfarin interaction review",
    )

    chunks = KnowledgeSplitter(token_counter=WordTokenCounter()).split([page])

    contents = [chunk.content for chunk in chunks]
    assert any(content == "KEYWORDS\nadverse event, bleeding, warfarin" for content in contents)
    assert any(content.startswith("1 | INTRODUCTION") for content in contents)
    assert any(content.startswith("2 | METHODS\n2.1 | Search strategy") for content in contents)
    assert any(content.startswith("2.2 | Study inclusion") for content in contents)
    assert any(content.startswith("2.5 | Data synthesis") for content in contents)
    assert not any(content.startswith("results of de-challenge") for content in contents)


def test_repair_aspirin_warfarin_text_chunk_boundaries() -> None:
    chunks = [
        build_aspirin_warfarin_chunk(
            "Abstract. Our article reviews the",
            chunk_index=0,
        ),
        build_aspirin_warfarin_chunk(
            "drug–nutrient interactions that alter micronutritional status. Some mechanisms were investigated.",
            chunk_index=1,
        ),
        build_aspirin_warfarin_chunk(
            "Niacin (B3)\nThe clinical significance thereof is unknown.\n"
            "Pantothenic Acid (B5)\nPantethine is used as a",
            chunk_index=2,
        ),
        build_aspirin_warfarin_chunk(
            "Calciferols (D)\nVitamin D context.\nK Vitamin\n"
            "factors II, VII, IX, and\n\nX. It is expected to change "
            "coagulation. Lack of menaquinone-7-trans",
            chunk_index=3,
        ),
        build_aspirin_warfarin_chunk(
            "results in the inactivation of extrahepatic proteins.",
            chunk_index=4,
        ),
        build_aspirin_warfarin_chunk(
            "developing countries. DNIs and polypharmacy theoretically increase "
            "the risks of micronutritional deficiencies, enhancing the risk of "
            "adverse effect on chronically ill people with impaired nutritional "
            "status. Karadima et al. proposed omics and the functionality of\n\n"
            "Karadima et al. proposed omics and the functionality of systems.",
            chunk_index=5,
        ),
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)
    contents = [chunk.content for chunk in repaired]

    assert contents[0].endswith("drug–nutrient interactions that alter micronutritional status.")
    assert contents[1] == "Some mechanisms were investigated."
    assert contents[2].endswith("The clinical significance thereof is unknown.")
    assert contents[3].startswith("Pantothenic Acid (B5)")
    assert contents[3].endswith("had mild antiplatelet aggregation properties.")
    assert contents[4] == "Calciferols (D)\nVitamin D context."
    assert contents[5].startswith("K Vitamin\n")
    assert "II, VII, IX, and X. It is expected" in contents[5]
    assert "Lack of menaquinone-7-trans results in" in contents[5]
    assert not contents[6].startswith("developing countries.")
    assert contents[6].count("Karadima et al.") == 1
    assert "functionality of systems" in contents[6]


def test_repair_warfarin_review_discussion_boundary() -> None:
    boundary = "multiple active ingredients listed in the current review to avoid the risk of interaction."
    continuation = "Concurrent use of other antiplatelet or anticoagulants"
    chunks = [
        build_warfarin_review_chunk(
            f"Discussion before boundary. {boundary} {continuation} should be discouraged.",
            chunk_index=12,
        ),
        build_warfarin_review_chunk(
            f"duplicated overlap before. {boundary} {continuation} should be discouraged. More evidence.",
            chunk_index=13,
        ),
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)

    assert repaired[0].content.endswith(boundary)
    assert repaired[1].content.startswith(continuation)
    assert boundary not in repaired[1].content


def test_repair_drug_vitamin_d_review_removes_overlap_and_keeps_verified_boundaries() -> None:
    active_form = "The metabolically active 1,25(OH)2 D form is tightly regulated at the tissue level."
    chunks = [
        build_drug_vitamin_d_review_chunk(
            f"Introduction\nIntroductory context. {active_form}",
            chunk_index=1,
            page_start=2,
            page_end=3,
        ),
        build_drug_vitamin_d_review_chunk(
            f"{active_form} Review purpose.",
            chunk_index=2,
            page_start=2,
            page_end=3,
        ),
        build_drug_vitamin_d_review_chunk(
            "Methods\nStudy selection\nSearch strategy begins and",
            chunk_index=3,
            page_start=3,
            page_end=4,
        ),
        build_drug_vitamin_d_review_chunk(
            "Search strategy begins and continues. A considerable number of studies with stronger "
            "study designs were available for those drug categories.\n"
            "Data abstraction and quality assessment\nQuality methods.",
            chunk_index=4,
            page_start=4,
            page_end=5,
        ),
        build_drug_vitamin_d_review_chunk(
            "Results\nResults summary, likely reflecting increasing reporting standards for publication.\n"
            "Drugs that interfere with vitamin D absorption\nAbsorption evidence. "
            "orlistat dose to maximize vitamin D absorption.\n"
            "Drugs that interfere with vitamin D metabolism\nStatins\nStatin evidence.",
            chunk_index=5,
            page_start=5,
            page_end=6,
        ),
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)
    contents = [chunk.content for chunk in repaired]

    assert sum(content.count(active_form) for content in contents) == 1
    assert contents[0] == "Introduction\nIntroductory context."
    assert contents[1].startswith(active_form)
    assert contents[2].startswith("Methods\nStudy selection")
    assert contents[2].endswith("study designs were available for those drug categories.")
    assert contents[3].startswith("Data abstraction and quality assessment")
    assert contents[4].startswith("Results")
    assert contents[4].endswith("likely reflecting increasing reporting standards for publication.")
    assert contents[5].startswith("Drugs that interfere with vitamin D absorption")
    assert contents[5].endswith("orlistat dose to maximize vitamin D absorption.")
    assert contents[6].startswith("Drugs that interfere with vitamin D metabolism\nStatins")


def test_repair_drug_vitamin_d_review_splits_drug_groups_at_verified_headings() -> None:
    chunks = [
        build_drug_vitamin_d_review_chunk(
            "Drugs that interfere with vitamin D metabolism\nStatins\nStatin evidence.\n"
            "Antimicrobials\nAntimicrobial evidence ending with conversion of 25(OH)D to 1,25(OH) D.\n"
            "Antiepileptic drugs\nAED evidence evident among individuals with insufficient exposure to "
            "exogenous sources of vitamin D (diet, supplements or UV exposure).\n"
            "Corticosteroids\nSteroid evidence dietary or supplemental vitamin D intake, or UV exposure.\n"
            "Immunosuppressive agents\nImmune evidence itself on vitamin D status.\n"
            "Chemotherapeutic agents\nCancer evidence should be monitored regularly for patients undergoing "
            "cancer treatment.\n"
            "Highly active antiretroviral agents (HAART)\nHAART evidence circulating 25(OH)D "
            "concentrations.\n"
            "Histamine H2-receptor antagonists\nH2 evidence CYP enzymes in animal models.\n"
            "Drug-vitamin D interactions that induce side effects\nThiazide evidence reported significant "
            "alterations in 25(OH)D concentrations as a result of thiazide treatment.\n"
            "Discussion\nDiscussion conclusion adequate serum 25(OH)D concentrations while optimizing "
            "drug efficacy and minimizing drug toxicity.",
            chunk_index=6,
            page_start=6,
            page_end=13,
        )
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)
    contents = [chunk.content for chunk in repaired]

    expected_starts = [
        "Drugs that interfere with vitamin D metabolism\nStatins",
        "Antimicrobials",
        "Antiepileptic drugs",
        "Corticosteroids",
        "Immunosuppressive agents",
        "Chemotherapeutic agents",
        "Highly active antiretroviral agents (HAART)",
        "Histamine H2-receptor antagonists",
        "Drug-vitamin D interactions that induce side effects",
        "Discussion",
    ]
    assert len(contents) == len(expected_starts)
    assert all(content.startswith(start) for content, start in zip(contents, expected_starts, strict=True))
    assert contents[1].endswith("conversion of 25(OH)D to 1,25(OH) D.")
    assert contents[2].endswith("vitamin D (diet, supplements or UV exposure).")
    assert contents[-1].endswith("drug efficacy and minimizing drug toxicity.")


def test_repair_drug_vitamin_d_review_splits_oversized_discussion_at_paragraph_topics() -> None:
    chunks = [
        build_drug_vitamin_d_review_chunk(
            "Discussion\nInitial findings. "
            "The currently available literature on drug-vitamin D interactions has limitations. "
            "Because vitamin D is highly hydrophobic and has several metabolites, measurement is challenging. "
            "Given the increasing prevalence of vitamin D supplementation, continued evaluation is warranted.",
            chunk_index=13,
            page_start=12,
            page_end=13,
        )
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)

    assert [chunk.content.splitlines()[0] for chunk in repaired] == [
        "Discussion",
        "The currently available literature on drug-vitamin D interactions has limitations.",
        "Because vitamin D is highly hydrophobic and has several metabolites, measurement is challenging.",
        "Given the increasing prevalence of vitamin D supplementation, continued evaluation is warranted.",
    ]


def test_repair_drug_vitamin_d_review_uses_verified_page_ranges_and_abstract_layout() -> None:
    chunks = [
        build_drug_vitamin_d_review_chunk(
            "Drug-vitamin D interactions: A systematic review of the literature Abstract Abstract body.",
            chunk_index=0,
            page_start=1,
            page_end=2,
        ),
        build_drug_vitamin_d_review_chunk(
            "Introduction Intro. The metabolically active 1,25(OH)2 D form continues. "
            "Methods Study selection Methods body. Data abstraction and quality assessment Quality body. "
            "Results Result body. Drugs that interfere with vitamin D absorption Absorption body. "
            "Drugs that interfere with vitamin D metabolism Statins Statin body. "
            "Antimicrobials Antimicrobial body. Antiepileptic drugs AED body. "
            "Corticosteroids Steroid body. Immunosuppressive agents Immune body. "
            "Chemotherapeutic agents Cancer body. Highly active antiretroviral agents (HAART) HAART body. "
            "Histamine H2-receptor antagonists H2 body. "
            "Drug-vitamin D interactions that induce side effects Side-effect body. Discussion Discussion body.",
            chunk_index=1,
            page_start=2,
            page_end=13,
        ),
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)
    by_start = {" ".join(chunk.content.split())[:80]: chunk for chunk in repaired}

    assert repaired[0].content.startswith(
        "Drug-vitamin D interactions: A systematic review of the literature\n\nAbstract\n"
    )
    expected_ranges = {
        "Drug-vitamin D interactions: A systematic review of the literature Abstract": (1, 1),
        "Introduction": (2, 2),
        "Methods Study selection": (3, 4),
        "Results": (5, 5),
        "Drugs that interfere with vitamin D metabolism Statins": (6, 6),
        "Antiepileptic drugs": (7, 8),
        "Corticosteroids": (8, 9),
        "Chemotherapeutic agents": (10, 10),
        "Highly active antiretroviral agents (HAART)": (10, 11),
        "Histamine H2-receptor antagonists": (11, 11),
    }
    for prefix, expected in expected_ranges.items():
        chunk = next(item for normalized, item in by_start.items() if normalized.startswith(prefix))
        assert (chunk.metadata.page_start, chunk.metadata.page_end) == expected


def test_repair_statins_vitamin_d_review_uses_verified_semantic_boundaries() -> None:
    content = "\n".join(
        [
            "Statins, Vitamin D, and Cardiovascular Health: A Comprehensive Review",
            "Review",
            "Review",
            "Abstract",
            "Statins are widely used lipid-lowering agents. Keywords: endothelial inflammation modulation",
            "1. Introduction",
            "Introduction body between statins, vitamin D, and cardiovascular outcomes.",
            "2. Statins and Vitamin D: Mechanistic Interactions",
            "2.1. Shared Precursors and Metabolic Pathways",
            "Cholesterol and 25(OH)D, the main circulating form of vitamin D, body atherosclerosis and heart failure.",
            "2.3. Molecular Mediators and Transport Proteins Involved in Statin–Vitamin D Interactions",
            "Molecular body under investigation.",
            "2.4. Influence on Vitamin D Synthesis and Metabolism",
            "Metabolism body through direct clinical evidence.",
            "Although cholesterol and vitamin D share a precursor. The net effect likely varies among different statin drugs and patient contexts.",
            "2.5. Combined Role of Statins and Vitamin D in Cardiovascular Risk Reduction: Synergy or Redundancy?",
            "Combined body reducing tissue factor mRNA expression.",
            "• Endothelial Protection",
            "Protection body with a few incorporating animal or in vitro mechanistic findings (notably references).",
            "3. Changes in Vitamin D Levels in Statin Users: Clinical Evidence",
            "Clinical body changes in vitamin D concentrations.",
            "Key Point: Current evidence",
            "Key point body with coronary artery disease.",
            "4. Vitamin D Supplementation in Statin-Treated Patients",
            "Supplement body supporting better cardiovascular outcomes.",
            "Guideline Recommendations for Vitamin D Testing and Supplementation",
            "Guideline body without specific risk factors or symptoms.",
            "5. Vitamin D, Atherosclerosis, and Coronary Artery Disease",
            "5.1. Vitamin D Levels and Cardiovascular Risk",
            "Risk body but results have been inconsistent and not definitive.",
            "5.4. Current Consensus",
            "Consensus body especially in patients with muscular symptoms or inflammation.",
            "5.7. Preventive Cardiovascular Strategies",
            "Strategy body to maximizing therapeutic outcomes.",
            "6. Summary of Key Findings and Future Therapeutic Directions",
            "6.1. Summary of Key Findings",
            "Summary body beyond those achievable by statins alone.",
            "7. Limitations of the Study",
            "Limitations body vitamin D, and cardiovascular risk.",
            "8. Conclusions",
            "Conclusion body vitamin D-deficient populations.",
            "Author Contributions: remove this back matter.",
        ]
    )
    chunks = [build_statins_vitamin_d_review_chunk(content, chunk_index=0)]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)
    contents = [" ".join(chunk.content.split()) for chunk in repaired]

    expected_starts = [
        "Statins, Vitamin D",
        "1. Introduction",
        "2. Statins and Vitamin D: Mechanistic Interactions 2.1.",
        "2.3. Molecular Mediators",
        "2.4. Influence on Vitamin D Synthesis and Metabolism",
        "Although cholesterol and vitamin D",
        "2.5. Combined Role of Statins and Vitamin D",
        "• Endothelial Protection",
        "3. Changes in Vitamin D Levels in Statin Users",
        "Key Point: Current evidence",
        "4. Vitamin D Supplementation in Statin-Treated Patients",
        "Guideline Recommendations for Vitamin D Testing and Supplementation",
        "5. Vitamin D, Atherosclerosis, and Coronary Artery Disease 5.1.",
        "5.4. Current Consensus",
        "5.7. Preventive Cardiovascular Strategies",
        "6. Summary of Key Findings and Future Therapeutic Directions 6.1.",
        "7. Limitations of the Study",
        "8. Conclusions",
    ]
    assert len(contents) == len(expected_starts)
    assert all(content.startswith(start) for content, start in zip(contents, expected_starts, strict=True))
    assert contents[0].endswith("endothelial inflammation modulation")
    assert repaired[0].content.startswith(
        "Statins, Vitamin D, and Cardiovascular Health: A Comprehensive Review\n\nAbstract\n"
    )
    assert "\n\nKeywords:" in repaired[0].content
    expected_page_ranges = {
        "2. Statins and Vitamin D: Mechanistic Interactions": (2, 3),
        "• Endothelial Protection": (6, 7),
        "4. Vitamin D Supplementation in Statin-Treated Patients": (10, 10),
    }
    for prefix, expected_page_range in expected_page_ranges.items():
        chunk = next(item for item in repaired if item.content.startswith(prefix))
        assert (chunk.metadata.page_start, chunk.metadata.page_end) == expected_page_range
    assert contents[-1].endswith("vitamin D-deficient populations.")
    assert not any("Author Contributions" in content for content in contents)


def test_repair_statins_vitamin_d_review_preserves_verified_table_chunks() -> None:
    text = build_statins_vitamin_d_review_chunk(
        "Review Statins, Vitamin D, and Cardiovascular Health: A Comprehensive Review "
        "Abstract Statins are widely used lipid-lowering agents. "
        "8. Conclusions Evidence ends in vitamin D-deficient populations.",
        chunk_index=0,
    )
    table = build_statins_vitamin_d_review_chunk(
        "Mechanism/Pathway=Anti-inflammatory/immunomodulation | "
        "Statin Mechanism=↓ IL-6 | Vitamin D Mechanism=VDR activation | "
        "Representative Evidence (Study Type/Population)=Clinical review [1]",
        chunk_index=1,
        page_start=7,
        page_end=7,
    )
    table = table.model_copy(
        update={
            "metadata": table.metadata.model_copy(
                update={
                    "content_kind": KnowledgeContentKind.TABLE,
                    "table_title": "Overlap of Statins and Vitamin D Mechanisms",
                }
            )
        }
    )

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks([text, table])

    table_chunks = [chunk for chunk in repaired if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
    assert len(table_chunks) == 1
    assert table_chunks[0].metadata.table_title == "Overlap of Statins and Vitamin D Mechanisms"
    assert "Clinical review [1]" in table_chunks[0].content


def test_repair_aspirin_warfarin_vitamin_k_after_overview_reference() -> None:
    chunks = [
        build_aspirin_warfarin_chunk(
            "Warfarin overview: factors II, VII, IX, and X are inhibited.",
            chunk_index=0,
        ),
        build_aspirin_warfarin_chunk(
            "Calciferols (D)\nVitamin D context.\nK Vitamin\n"
            "carboxylation of factors II, VII, IX, and\n\n"
            "X. It is expected to decrease proteins. "
            "Lack of menaquinone-7-trans",
            chunk_index=1,
        ),
        build_aspirin_warfarin_chunk(
            "results in the inactivation of extrahepatic proteins.",
            chunk_index=2,
        ),
    ]

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks(chunks)

    assert repaired[1].content == "Calciferols (D)\nVitamin D context."
    assert repaired[2].content.startswith("K Vitamin\n")
    assert "II, VII, IX, and X. It is expected" in repaired[2].content
    assert "Lack of menaquinone-7-trans results in" in repaired[2].content


def test_repair_aspirin_warfarin_scientific_table_rows() -> None:
    table = build_aspirin_warfarin_chunk(
        "Nutriment=ascorbic acid (C) | Effect on Nutrient Status or Function="
        "↓ C intragastric concentration ↑ urinary excretion ↓ C leukocyte "
        "concentration | Number=1 1 1 | Study Design=interventional— randomized, "
        "double-blind, parallel group case report interventional | Number of "
        "Patients=45 3 10 | Dosage=3 × 80 mg ASA for 6 days 162 mg ASA 2 times "
        "at 3 days interval 600 mg ASA, 500 mg C | Result=↓ gastric mucosa "
        "concentration per 10% ↑ urinary excretion ↓ C leukocyte concentration "
        "by 114%\n"
        "Nutriment=iron | Effect on Nutrient Status or Function=↓ serum ferritin "
        "| Number=2 | Study Design=first study\n"
        "Nutriment=iron | Study Design=second study\n"
        "Nutriment=folate (B9) | Effect on Nutrient Status or Function=no "
        "association with bleeding ↑ clearance of S-7-hydroxywarfarin "
        "dietary-induced Folate deficiency | Number=1 1 1 | Study Design="
        "longitudinal cohort interventional observational | Number of Patients="
        "719 24 114 | Dosage=86% patients in INR 2.0–3.5 5 mg/day B9 "
        "supplementation dose unavailable | Result=no association non significant "
        "changes in dose and INR impaired folate status in as little as 6 months",
        chunk_index=37,
        content_kind=KnowledgeContentKind.TABLE,
    )

    [repaired] = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks([table])

    assert repaired.content.count("Nutriment=ascorbic acid (C)") == 3
    assert "Effect on Nutrient Status or Function=↑ urinary excretion" in (repaired.content)
    assert (
        "Nutriment=iron | Effect on Nutrient Status or Function=↓ serum ferritin | Number=2 | Study Design=second study"
    ) in repaired.content
    assert repaired.content.count("Nutriment=folate (B9)") == 3
    assert ("Effect on Nutrient Status or Function=↑ clearance of S-7-hydroxywarfarin") in repaired.content
    assert "Effect on Nutrient Status or Function=dietary-induced Folate deficiency" in (repaired.content)


def test_repair_aspirin_warfarin_regroups_oversized_table_rows() -> None:
    rows = [
        "Nutriment=iron | Effect on Nutrient Status or Function=↓ serum ferritin "
        f"| Number=1 | Result={'result ' * 350}",
        "Nutriment=folate (B9) | Effect on Nutrient Status or Function=no "
        f"association | Number=1 | Result={'result ' * 350}",
        "Nutriment=K vitamin | Effect on Nutrient Status or Function=influence INR "
        f"| Number=1 | Result={'result ' * 350}",
    ]
    table = build_aspirin_warfarin_chunk(
        "\n".join(rows),
        chunk_index=38,
        content_kind=KnowledgeContentKind.TABLE,
    )

    repaired = KnowledgeSplitter(token_counter=WordTokenCounter())._repair_verified_document_chunks([table])

    assert len(repaired) == 2
    assert all(chunk.token_count <= 800 for chunk in repaired)
    assert [chunk.metadata.chunk_index for chunk in repaired] == [0, 1]


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


def test_locate_split_chunks_replaces_nested_fragment_at_same_position() -> None:
    source = "앞 문장\n\n스테로이드제\n가려움증 안내\n\n다음 문장"

    located = KnowledgeSplitter._locate_split_chunks(
        source,
        [
            "앞 문장",
            "스테로이드제",
            "스테로이드제\n가려움증 안내",
            "다음 문장",
        ],
    )

    assert [content for content, _, _ in located] == [
        "앞 문장",
        "스테로이드제\n가려움증 안내",
        "다음 문장",
    ]
