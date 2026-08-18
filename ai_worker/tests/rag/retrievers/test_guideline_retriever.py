import pytest

from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
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


class FailingEmbeddingProvider(
    FakeEmbeddingProvider
):
    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        raise RuntimeError(
            "임베딩 서비스 연결 실패"
        )


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


class FailingVectorStore(
    FakeVectorStore
):
    async def search(
        self,
        query_vector: list[float],
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        raise RuntimeError(
            "Qdrant 검색 연결 실패"
        )


def build_result() -> RetrievedGuidelineChunk:
    return RetrievedGuidelineChunk(
        vector_chunk_id="chunk-1",
        content=(
            "퇴원 후 처방된 약을 "
            "지시에 따라 복용합니다."
        ),
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


async def test_search_embeds_query_and_searches_store(
) -> None:
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

    results = await retriever.search(
        search_query
    )

    assert (
        embedding_provider.received_query
        == search_query.query
    )
    assert (
        vector_store.received_query_vector
        == [1.0, 0.0, 0.0]
    )
    assert (
        vector_store.received_search_query
        == search_query
    )
    assert results == [expected_result]


async def test_search_returns_empty_result(
) -> None:
    retriever = GuidelineRetriever(
        embedding_provider=(
            FakeEmbeddingProvider()
        ),
        vector_store=FakeVectorStore(
            results=[]
        ),
    )

    results = await retriever.search(
        build_search_query()
    )

    assert results == []


async def test_search_excludes_results_below_similarity_threshold(
) -> None:
    high_score_result = build_result()
    low_score_result = RetrievedGuidelineChunk(
        vector_chunk_id="chunk-low-score",
        content=(
            "검색 질문과 관련성이 "
            "낮은 내용"
        ),
        similarity_score=0.64,
        metadata=GuidelineMetadata(
            document_id="unrelated-guideline",
            title="Unrelated Guideline",
            organization="Test Organization",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            topic="MEDICATION",
        ),
    )

    retriever = GuidelineRetriever(
        embedding_provider=(
            FakeEmbeddingProvider()
        ),
        vector_store=FakeVectorStore(
            results=[
                high_score_result,
                low_score_result,
            ]
        ),
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        build_search_query()
    )

    assert results == [
        high_score_result
    ]


async def test_search_converts_embedding_failure_to_retrieval_error(
) -> None:
    retriever = GuidelineRetriever(
        embedding_provider=(
            FailingEmbeddingProvider()
        ),
        vector_store=FakeVectorStore(
            results=[]
        ),
    )

    with pytest.raises(
        GuidelineRetrievalError
    ) as exc_info:
        await retriever.search(
            build_search_query()
        )

    assert (
        exc_info.value.stage
        == RetrievalFailureStage.EMBEDDING
    )
    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )


async def test_search_converts_vector_store_failure_to_retrieval_error(
) -> None:
    retriever = GuidelineRetriever(
        embedding_provider=(
            FakeEmbeddingProvider()
        ),
        vector_store=FailingVectorStore(
            results=[]
        ),
    )

    with pytest.raises(
        GuidelineRetrievalError
    ) as exc_info:
        await retriever.search(
            build_search_query()
        )

    assert (
        exc_info.value.stage
        == RetrievalFailureStage.VECTOR_STORE
    )
    assert isinstance(
        exc_info.value.__cause__,
        RuntimeError,
    )
