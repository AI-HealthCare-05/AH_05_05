import pytest

from ai_worker.rag.indexers.knowledge_indexer import KnowledgeIndexer
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
)


def build_chunk(
    marker: str,
    *,
    dataset_version: str = "knowledge-pilot-v1",
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=marker * 64,
        content=f"content-{marker}",
        embedding_text=f"embedding-{marker}",
        token_count=5,
        metadata=KnowledgeChunkMetadata(
            source_id=f"source-{marker}",
            document_id=f"document-{marker}",
            title=f"문서 {marker}",
            provider="시험 제공자",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
            dataset_version=dataset_version,
            section_type=KnowledgeSectionType.CAUTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=marker * 64,
        ),
    )


class RecordingEmbeddingProvider:
    model_name = "test-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.batches.append(texts)
        return [[float(len(self.batches)), float(index), 0.0] for index, _ in enumerate(texts, start=1)]

    async def embed_query(self, query: str) -> list[float]:
        raise AssertionError("인덱싱에서는 질문 임베딩을 호출하지 않습니다.")


class RecordingKnowledgeStore:
    collection_name = "knowledge_release"

    def __init__(self, *, count_offset: int = 0) -> None:
        self.created = False
        self.saved_batches: list[tuple[list[KnowledgeChunk], list[list[float]]]] = []
        self.count_offset = count_offset

    async def create_release_collection(self) -> None:
        self.created = True

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> list[str]:
        self.saved_batches.append((chunks, vectors))
        return [chunk.chunk_id for chunk in chunks]

    async def count_points(self) -> int:
        return sum(len(chunks) for chunks, _ in self.saved_batches) + self.count_offset


async def test_index_release_embeds_and_upserts_in_batches() -> None:
    embedding_provider = RecordingEmbeddingProvider()
    store = RecordingKnowledgeStore()
    indexer = KnowledgeIndexer(
        embedding_provider=embedding_provider,
        vector_store=store,
        embedding_batch_size=2,
        upsert_batch_size=2,
    )
    chunks = [
        build_chunk("a"),
        build_chunk("b"),
        build_chunk("c"),
    ]

    result = await indexer.index_release(chunks)

    assert store.created is True
    assert embedding_provider.batches == [
        ["embedding-a", "embedding-b"],
        ["embedding-c"],
    ]
    assert [[chunk.chunk_id for chunk in saved_chunks] for saved_chunks, _ in store.saved_batches] == [
        ["a" * 64, "b" * 64],
        ["c" * 64],
    ]
    assert result.collection_name == "knowledge_release"
    assert result.dataset_version == "knowledge-pilot-v1"
    assert result.indexed_chunk_count == 3


async def test_index_release_rejects_empty_chunks() -> None:
    indexer = KnowledgeIndexer(
        embedding_provider=RecordingEmbeddingProvider(),
        vector_store=RecordingKnowledgeStore(),
    )

    with pytest.raises(ValueError, match="청크"):
        await indexer.index_release([])


async def test_index_release_rejects_mixed_dataset_versions() -> None:
    indexer = KnowledgeIndexer(
        embedding_provider=RecordingEmbeddingProvider(),
        vector_store=RecordingKnowledgeStore(),
    )

    with pytest.raises(ValueError, match="dataset_version"):
        await indexer.index_release(
            [
                build_chunk("a"),
                build_chunk(
                    "b",
                    dataset_version="knowledge-pilot-v2",
                ),
            ]
        )


async def test_index_release_rejects_final_point_count_mismatch() -> None:
    indexer = KnowledgeIndexer(
        embedding_provider=RecordingEmbeddingProvider(),
        vector_store=RecordingKnowledgeStore(count_offset=-1),
    )

    with pytest.raises(ValueError, match="저장 건수"):
        await indexer.index_release([build_chunk("a")])
