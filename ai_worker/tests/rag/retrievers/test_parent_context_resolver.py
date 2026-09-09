from ai_worker.rag.retrievers.parent_context_resolver import ParentContextResolver
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)


def build_chunk(
    *,
    chunk_id: str,
    index: int,
    content: str,
    document_id: str = "magnesium-guide",
    ingredient_names: list[str] | None = None,
    section_type: KnowledgeSectionType = KnowledgeSectionType.FUNCTION,
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id=chunk_id[:8],
        chunk_id=chunk_id,
        content=content,
        embedding_text=content,
        token_count=10,
        similarity_score=0.8,
        metadata=KnowledgeChunkMetadata(
            source_id="MFDS",
            document_id=document_id,
            title="마그네슘 기능성 안내",
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
            dataset_version="knowledge-full-v6",
            ingredient_names=ingredient_names or ["마그네슘"],
            section_type=section_type,
            section_title="기능성",
            page_start=1,
            page_end=1,
            chunk_index=index,
            content_hash=chunk_id,
        ),
    )


def build_plan() -> MedicationKnowledgeQueryPlan:
    return MedicationKnowledgeQueryPlan(
        original_query="마그네슘은 왜 먹나요?",
        expanded_query="마그네슘 기능성",
        entity_names=["마그네슘"],
        entities=[
            MedicationQueryEntity(
                surface="마그네슘",
                canonical_name="마그네슘",
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.CATALOG,
            )
        ],
        section_types=[KnowledgeSectionType.FUNCTION],
    )


def test_expands_child_with_adjacent_same_document_section_and_entity_context() -> None:
    child = build_chunk(chunk_id="a" * 64, index=4, content="마그네슘은 정상적인 근육 기능에 필요합니다.")
    sibling = build_chunk(chunk_id="b" * 64, index=5, content="에너지 이용에도 필요합니다.")

    resolution = ParentContextResolver().resolve(
        children=[child],
        candidates=[child, sibling],
        query_plan=build_plan(),
    )

    assert resolution.attached_parent_count == 1
    assert resolution.rejected_parent_mismatch_count == 0
    assert resolution.chunks[0].content == "마그네슘은 정상적인 근육 기능에 필요합니다.\n\n에너지 이용에도 필요합니다."


def test_rejects_nearby_context_from_another_document_or_entity() -> None:
    child = build_chunk(chunk_id="a" * 64, index=4, content="마그네슘 기능")
    other_document = build_chunk(
        chunk_id="b" * 64,
        index=5,
        content="다른 문서",
        document_id="calcium-guide",
    )
    other_entity = build_chunk(
        chunk_id="c" * 64,
        index=5,
        content="칼슘 기능",
        ingredient_names=["칼슘"],
    )

    resolution = ParentContextResolver().resolve(
        children=[child],
        candidates=[child, other_document, other_entity],
        query_plan=build_plan(),
    )

    assert resolution.attached_parent_count == 0
    assert resolution.rejected_parent_mismatch_count == 2
    assert resolution.chunks == [child]
