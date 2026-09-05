from types import SimpleNamespace

from qdrant_client.http import models

from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import (
    QdrantHybridKnowledgeStore,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSearchMode,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
)


def build_chunk() -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id="a" * 64,
        content="마그네슘은 에너지 이용에 필요합니다.",
        embedding_text=("[성분] 마그네슘\n[섹션] 기능성\n마그네슘은 에너지 이용에 필요합니다."),
        token_count=20,
        metadata=KnowledgeChunkMetadata(
            source_id="source-a",
            document_id="document-a",
            title="마그네슘 기능성",
            provider="시험기관",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
            dataset_version="knowledge-hybrid-v1",
            ingredient_names=["마그네슘"],
            section_type=KnowledgeSectionType.FUNCTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


class RecordingClient:
    def __init__(self) -> None:
        self.created = None
        self.upserted = None
        self.query_kwargs = None

    async def collection_exists(self, collection_name: str) -> bool:
        return self.created is not None

    async def create_collection(self, **kwargs) -> None:
        self.created = kwargs

    async def get_collection(self, collection_name: str):
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={
                        "dense": models.VectorParams(
                            size=3,
                            distance=models.Distance.COSINE,
                        )
                    },
                    sparse_vectors={
                        "bm25": models.SparseVectorParams(
                            modifier=models.Modifier.IDF,
                        )
                    },
                )
            )
        )

    async def upsert(self, **kwargs) -> None:
        self.upserted = kwargs

    async def query_points(self, **kwargs):
        self.query_kwargs = kwargs
        chunk = build_chunk()
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="point-a",
                    score=3.0,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "content": chunk.content,
                        "embedding_text": chunk.embedding_text,
                        "token_count": chunk.token_count,
                        "metadata": chunk.metadata.model_dump(mode="json"),
                    },
                )
            ]
        )


class HybridConfidenceRecordingClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.query_calls: list[dict] = []

    async def query_points(self, **kwargs):
        self.query_calls.append(kwargs)
        chunk = build_chunk()
        score = 0.72 if kwargs.get("using") == "dense" else 3.0
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    id="point-a",
                    score=score,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "content": chunk.content,
                        "embedding_text": chunk.embedding_text,
                        "token_count": chunk.token_count,
                        "metadata": chunk.metadata.model_dump(mode="json"),
                    },
                )
            ]
        )


async def test_create_release_collection_uses_named_dense_and_bm25_vectors() -> None:
    client = RecordingClient()
    store = QdrantHybridKnowledgeStore(
        client=client,
        collection_name="knowledge_hybrid",
        vector_size=3,
        search_mode=KnowledgeSearchMode.HYBRID,
    )

    await store.create_release_collection()

    dense = client.created["vectors_config"]["dense"]
    sparse = client.created["sparse_vectors_config"]["bm25"]
    assert dense.size == 3
    assert dense.distance == models.Distance.COSINE
    assert sparse.modifier == models.Modifier.IDF


async def test_upsert_preserves_dense_vector_and_builds_multilingual_bm25_document() -> None:
    client = RecordingClient()
    store = QdrantHybridKnowledgeStore(
        client=client,
        collection_name="knowledge_hybrid",
        vector_size=3,
        search_mode=KnowledgeSearchMode.HYBRID,
    )
    await store.create_release_collection()

    await store.upsert_chunks(
        [build_chunk()],
        [[1.0, 0.0, 0.0]],
    )

    vector = client.upserted["points"][0].vector
    assert vector["dense"] == [1.0, 0.0, 0.0]
    assert vector["bm25"].model == "qdrant/bm25"
    assert vector["bm25"].options == {"tokenizer": "multilingual"}
    assert "마그네슘" in vector["bm25"].text


async def test_hybrid_search_prefetches_dense_and_bm25_then_uses_rrf() -> None:
    client = HybridConfidenceRecordingClient()
    store = QdrantHybridKnowledgeStore(
        client=client,
        collection_name="knowledge_hybrid",
        vector_size=3,
        search_mode=KnowledgeSearchMode.HYBRID,
    )
    search_query = KnowledgeSearchQuery(
        query="마그네슘 기능",
        dataset_version="knowledge-hybrid-v1",
        limit=5,
    )
    await store.create_release_collection()

    results = await store.search(
        query_vector=[1.0, 0.0, 0.0],
        search_query=search_query,
    )

    assert len(client.query_calls) == 2
    hybrid_query = client.query_calls[0]
    dense_query = client.query_calls[1]
    prefetch = hybrid_query["prefetch"]
    assert [item.using for item in prefetch] == ["dense", "bm25"]
    assert prefetch[0].limit == 20
    assert prefetch[1].query.options == {"tokenizer": "multilingual"}
    assert hybrid_query["query"].fusion == models.Fusion.RRF
    assert dense_query["query"] == [1.0, 0.0, 0.0]
    assert dense_query["using"] == "dense"
    assert results[0].search_mode == KnowledgeSearchMode.HYBRID
    assert results[0].dense_similarity_score == 0.72


async def test_bm25_search_uses_sparse_vector_without_dense_threshold_semantics() -> None:
    client = RecordingClient()
    store = QdrantHybridKnowledgeStore(
        client=client,
        collection_name="knowledge_hybrid",
        vector_size=3,
        search_mode=KnowledgeSearchMode.BM25,
    )
    await store.create_release_collection()

    results = await store.search(
        query_vector=[1.0, 0.0, 0.0],
        search_query=KnowledgeSearchQuery(
            query="마그네슘 기능",
            dataset_version="knowledge-hybrid-v1",
        ),
    )

    assert client.query_kwargs["using"] == "bm25"
    assert isinstance(client.query_kwargs["query"], models.Document)
    assert results[0].search_mode == KnowledgeSearchMode.BM25
    assert 0.0 < results[0].similarity_score < 1.0
