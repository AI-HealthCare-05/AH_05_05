import pytest

from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)


class FakeEmbeddingClient:
    def __init__(
        self,
        document_vectors: (list[list[float]] | None) = None,
        query_vector: list[float] | None = None,
    ) -> None:
        self.document_vectors = document_vectors or []
        self.query_vector = query_vector or []
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    async def aembed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self.document_calls.append(texts)
        return self.document_vectors

    async def aembed_query(
        self,
        query: str,
    ) -> list[float]:
        self.query_calls.append(query)
        return self.query_vector


@pytest.mark.asyncio
async def test_embed_documents_returns_vectors() -> None:
    client = FakeEmbeddingClient(
        document_vectors=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ],
    )
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=client,
    )

    vectors = await provider.embed_documents(
        [
            " first document ",
            "second document",
        ],
    )

    assert vectors == [
        [0.1, 0.2, 0.3],
        [0.4, 0.5, 0.6],
    ]
    assert client.document_calls == [
        [
            "first document",
            "second document",
        ],
    ]


@pytest.mark.asyncio
async def test_embed_query_returns_vector() -> None:
    client = FakeEmbeddingClient(
        query_vector=[0.1, 0.2, 0.3],
    )
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=client,
    )

    vector = await provider.embed_query(
        " 퇴원 후 주의사항 ",
    )

    assert vector == [0.1, 0.2, 0.3]
    assert client.query_calls == [
        "퇴원 후 주의사항",
    ]


@pytest.mark.asyncio
async def test_embed_documents_returns_empty_without_api_call() -> None:
    client = FakeEmbeddingClient()
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=client,
    )

    vectors = await provider.embed_documents([])

    assert vectors == []
    assert client.document_calls == []


@pytest.mark.asyncio
async def test_embed_query_rejects_blank_query() -> None:
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=FakeEmbeddingClient(),
    )

    with pytest.raises(
        ValueError,
        match="검색어",
    ):
        await provider.embed_query("   ")


@pytest.mark.asyncio
async def test_embed_documents_rejects_blank_document() -> None:
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=FakeEmbeddingClient(),
    )

    with pytest.raises(
        ValueError,
        match="문서",
    ):
        await provider.embed_documents(
            [
                "valid document",
                "   ",
            ],
        )


@pytest.mark.asyncio
async def test_embed_query_rejects_wrong_vector_dimension() -> None:
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=FakeEmbeddingClient(
            query_vector=[0.1, 0.2],
        ),
    )

    with pytest.raises(
        ValueError,
        match="차원",
    ):
        await provider.embed_query("퇴원 후 주의사항")


@pytest.mark.asyncio
async def test_embed_documents_rejects_vector_count_mismatch() -> None:
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=FakeEmbeddingClient(
            document_vectors=[
                [0.1, 0.2, 0.3],
            ],
        ),
    )

    with pytest.raises(
        ValueError,
        match="개수",
    ):
        await provider.embed_documents(
            [
                "first document",
                "second document",
            ],
        )
