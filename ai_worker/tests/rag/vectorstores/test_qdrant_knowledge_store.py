from types import SimpleNamespace

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

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
    drug_names: list[str] | None = None,
    document_type: KnowledgeDocumentType = KnowledgeDocumentType.SUPPLEMENT_CODE,
    section_type: KnowledgeSectionType = KnowledgeSectionType.CAUTION,
    interaction_pair_keys: list[str] | None = None,
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
            drug_names=drug_names or [],
            ingredient_names=ingredient_names or [],
            interaction_pair_keys=interaction_pair_keys or [],
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


async def test_search_filters_exact_interaction_pair_key() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )
    requested_pair_key = "a" * 64

    try:
        await store.create_release_collection()
        chunks = [
            build_chunk(
                "a",
                interaction_pair_keys=[requested_pair_key],
            ),
            build_chunk(
                "b",
                interaction_pair_keys=["b" * 64],
            ),
        ]
        await store.upsert_chunks(
            chunks,
            [[1.0, 0.0, 0.0], [0.99, 0.01, 0.0]],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=KnowledgeSearchQuery(
                query="파록세틴과 셀레길린 상호작용",
                dataset_version="knowledge-pilot-v1",
                interaction_pair_keys=[requested_pair_key],
            ),
        )

        assert [result.metadata.document_id for result in results] == ["document-a"]
    finally:
        await client.close()


async def test_search_treats_entity_filters_as_alternatives() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )
    requested_pair_key = "a" * 64

    try:
        await store.create_release_collection()
        chunks = [
            build_chunk("a", drug_names=["아스피린"]),
            build_chunk("b", ingredient_names=["오메가3"]),
            build_chunk("c", interaction_pair_keys=[requested_pair_key]),
            build_chunk("d", ingredient_names=["마그네슘"]),
        ]
        await store.upsert_chunks(
            chunks,
            [
                [1.0, 0.0, 0.0],
                [0.99, 0.01, 0.0],
                [0.98, 0.02, 0.0],
                [0.97, 0.03, 0.0],
            ],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=KnowledgeSearchQuery(
                query="아스피린과 오메가3 상호작용",
                dataset_version="knowledge-pilot-v1",
                drug_names=["아스피린"],
                ingredient_names=["오메가3"],
                interaction_pair_keys=[requested_pair_key],
                limit=10,
            ),
        )

        assert {result.metadata.document_id for result in results} == {
            "document-a",
            "document-b",
            "document-c",
        }
    finally:
        await client.close()


async def test_search_reads_legacy_payload_without_interaction_pair_keys() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )

    try:
        await store.create_release_collection()
        chunk = build_chunk("a")
        legacy_metadata = chunk.metadata.model_dump(mode="json")
        legacy_metadata.pop("interaction_pair_keys")
        await client.upsert(
            collection_name="knowledge_release",
            wait=True,
            points=[
                models.PointStruct(
                    id=1,
                    vector=[1.0, 0.0, 0.0],
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "content": chunk.content,
                        "embedding_text": chunk.embedding_text,
                        "token_count": chunk.token_count,
                        "metadata": legacy_metadata,
                    },
                )
            ],
        )

        results = await store.search(
            query_vector=[1.0, 0.0, 0.0],
            search_query=KnowledgeSearchQuery(
                query="기존 청크",
                dataset_version="knowledge-pilot-v1",
            ),
        )

        assert len(results) == 1
        assert results[0].metadata.interaction_pair_keys == []
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


async def test_search_validates_collection_only_once() -> None:
    class CountingClient:
        def __init__(self) -> None:
            self.exists_calls = 0
            self.get_calls = 0
            self.query_calls = 0

        async def collection_exists(self, collection_name: str) -> bool:
            self.exists_calls += 1
            return True

        async def get_collection(self, collection_name: str):
            self.get_calls += 1
            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors=models.VectorParams(
                            size=3,
                            distance=models.Distance.COSINE,
                        )
                    )
                )
            )

        async def query_points(self, **kwargs):
            self.query_calls += 1
            return SimpleNamespace(points=[])

    client = CountingClient()
    store = QdrantKnowledgeStore(
        client=client,
        collection_name="knowledge_release",
        vector_size=3,
    )
    search_query = KnowledgeSearchQuery(
        query="마그네슘 기능",
        dataset_version="knowledge-pilot-v1",
    )

    await store.search(
        query_vector=[1.0, 0.0, 0.0],
        search_query=search_query,
    )
    await store.search(
        query_vector=[1.0, 0.0, 0.0],
        search_query=search_query,
    )

    assert client.exists_calls == 1
    assert client.get_calls == 1
    assert client.query_calls == 2
