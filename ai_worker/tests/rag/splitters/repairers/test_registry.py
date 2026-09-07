from ai_worker.rag.splitters.repairers.registry import (
    CallableDocumentChunkRepairer,
    DocumentChunkRepairRegistry,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
)


def _chunk(*, document_id: str, content: str, chunk_index: int = 7) -> KnowledgeChunk:
    metadata = KnowledgeChunkMetadata(
        source_id="research",
        document_id=document_id,
        title="검수 문서",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="test",
        section_type=KnowledgeSectionType.RESULTS,
        page_start=1,
        page_end=1,
        chunk_index=chunk_index,
        content_hash="0" * 64,
    )
    return KnowledgeChunk(
        chunk_id="1" * 64,
        content=content,
        embedding_text=content,
        token_count=1,
        metadata=metadata,
    )


def test_registry_returns_original_chunks_when_document_has_no_repairer() -> None:
    chunks = [_chunk(document_id="unreviewed", content="원문")]

    assert DocumentChunkRepairRegistry().repair(chunks) == chunks


def test_registry_applies_verified_repairer() -> None:
    chunks = [_chunk(document_id="verified", content="before")]

    def apply(items: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return [items[0].model_copy(update={"content": "after"})]

    registry = DocumentChunkRepairRegistry(
        repairers=[
            CallableDocumentChunkRepairer(
                document_id="verified",
                apply_chunks=apply,
            )
        ]
    )

    repaired = registry.repair(chunks)

    assert repaired[0].content == "after"
    assert repaired[0].metadata.chunk_index == 7


def test_registry_rejects_duplicate_document_repairers() -> None:
    def apply(items: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return items

    def repairer_factory() -> CallableDocumentChunkRepairer:
        return CallableDocumentChunkRepairer(
            document_id="verified",
            apply_chunks=apply,
        )

    try:
        DocumentChunkRepairRegistry(repairers=[repairer_factory(), repairer_factory()])
    except ValueError as error:
        assert "중복" in str(error)
    else:
        raise AssertionError("중복 문서 repairer는 거부해야 합니다.")
