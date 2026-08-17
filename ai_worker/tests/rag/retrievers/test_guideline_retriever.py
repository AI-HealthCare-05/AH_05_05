from ai_worker.rag.retrievers.guideline_retriever import (
    GuidelineRetriever,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.received_query: str | None = None

    @property
    def model_name(self) -> str:
        return "fake-embedding"

    @property
    def dimension(self) -> int:
        return 3

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [
            [1.0, 0.0, 0.0]
            for _ in texts
        ]

    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        self.received_query = query
        return [1.0, 0.0, 0.0]


class FakeVectorStore:
    def __init__(
        self,
        results: list[RetrievedGuidelineChunk],
    ) -> None:
        self._results = results
        self.received_query_vector: (
            list[float] | None
        ) = None
        self.received_search_query: (
            GuidelineSearchQuery | None
        ) = None

    async def search(
        self,
        query_vector: list[float],
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        self.received_query_vector = query_vector
        self.received_search_query = search_query

        return self._results


def build_result() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="chunk-1",
        content="퇴원 후 처방된 약을 지시에 따라 복용합니다.",
        similarity_score=0.93,
        metadata=GuidelineMetadata(
            document_id="stroke-guideline-2020",
            title="Stroke Guideline",
            organization="Test Organization",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="MEDICATION",
            page_number=10,
        ),
    )


def build_search_query() -> GuidelineSearchQuery:
    return GuidelineSearchQuery(
        query="뇌졸중 퇴원 후 복약 주의사항",
        condition="STROKE",
        care_phase="POST_DISCHARGE",
        topic="MEDICATION",
        limit=5,
    )


async def test_search_embeds_query_and_searches_store() -> None:
    embedding_provider = FakeEmbeddingProvider()
    expected_result = build_result()
    vector_store = FakeVectorStore(
        results=[expected_result]
    )

    retriever = GuidelineRetriever(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )
    search_query = build_search_query()

    results = await retriever.search(search_query)

    assert embedding_provider.received_query == (
        search_query.query
    )
    assert vector_store.received_query_vector == [
        1.0,
        0.0,
        0.0,
    ]
    assert (
        vector_store.received_search_query
        == search_query
    )
    assert results == [expected_result]


async def test_search_returns_empty_result() -> None:
    retriever = GuidelineRetriever(
        embedding_provider=(
            FakeEmbeddingProvider()
        ),
        vector_store=FakeVectorStore(results=[]),
    )

    results = await retriever.search(
        build_search_query()
    )

    assert results == []