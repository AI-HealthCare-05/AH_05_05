import pytest
from qdrant_client import AsyncQdrantClient

from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
)


def build_chunk(
    marker: str,
    *,
    dataset_version: str = "knowledge-pilot-v1",
    ingredient_names: list[str] | None = None,
    document_type: KnowledgeDocumentType = KnowledgeDocumentType.SUPPLEMENT_CODE,
    section_type: KnowledgeSectionType = KnowledgeSectionType.CAUTION,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=marker * 64,
        content=f"{marker} 근거 원문",
        embedding_text=f"[문서] {marker} 문서\n[원문]\n{marker} 근거 원문",
        token_count=12,
        metadata=KnowledgeChunkMetadata(
            source_id=f"source-{marker}",
            document_id=f"document-{marker}",
            title=f"{marker} 문서",
            provider="시험 제공자",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=document_type,
            dataset_version=dataset_version,
            ingredient_names=ingredient_names or [],
            section_type=section_type,
            section_title="섭취 시 주의사항",
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=marker * 64,
        ),
    )


async def test_create_release_collection_rejects_existing_collection() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()

        with pytest.raises(ValueError, match="이미 존재"):
            await store.create_release_collection()
    finally:
        await client.close()


async def test_upsert_preserves_content_embedding_text_and_metadata() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()
        chunk = build_chunk("a", ingredient_names=["비타민 B6"])

        point_ids = await store.upsert_chunks(
            [chunk],
            [[1.0, 0.0, 0.0]],
        )
        points, _ = await client.scroll(
            collection_name="knowledge_release",
            limit=10,
            with_payload=True,
            with_vectors=False,
        )

        assert len(point_ids) == 1
        assert await store.count_points() == 1
        assert points[0].payload == {
            "chunk_id": chunk.chunk_id,
            "content": chunk.content,
            "embedding_text": chunk.embedding_text,
            "token_count": 12,
            "metadata": chunk.metadata.model_dump(mode="json"),
        }
    finally:
        await client.close()


async def test_search_filters_dataset_version_and_ingredient() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()
        chunks = [
            build_chunk("a", ingredient_names=["비타민 B6"]),
            build_chunk("b", ingredient_names=["철"]),
            build_chunk(
                "c",
                dataset_version="knowledge-pilot-v2",
                ingredient_names=["비타민 B6"],
            ),
        ]
        await store.upsert_chunks(
            chunks,
            [
                [1.0, 0.0, 0.0],
                [0.99, 0.01, 0.0],
                [0.98, 0.02, 0.0],
            ],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=KnowledgeSearchQuery(
                query="비타민 B6 주의사항",
                dataset_version="knowledge-pilot-v1",
                ingredient_names=["비타민 B6"],
                limit=5,
            ),
        )

        assert [result.metadata.document_id for result in results] == ["document-a"]
        assert results[0].content == "a 근거 원문"
        assert results[0].similarity_score > 0.0
    finally:
        await client.close()


async def test_search_filters_document_and_section_types() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()
        chunks = [
            build_chunk("a"),
            build_chunk(
                "b",
                document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
                section_type=KnowledgeSectionType.RESULTS,
            ),
        ]
        await store.upsert_chunks(
            chunks,
            [[1.0, 0.0, 0.0], [0.99, 0.01, 0.0]],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=KnowledgeSearchQuery(
                query="연구 결과",
                dataset_version="knowledge-pilot-v1",
                document_types=[KnowledgeDocumentType.RESEARCH_ARTICLE],
                section_types=[KnowledgeSectionType.RESULTS],
            ),
        )

        assert [result.metadata.document_id for result in results] == ["document-b"]
    finally:
        await client.close()


async def test_upsert_rejects_vector_dimension_mismatch() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()

        with pytest.raises(ValueError, match="차원"):
            await store.upsert_chunks(
                [build_chunk("a")],
                [[1.0, 0.0]],
            )
    finally:
        await client.close()
