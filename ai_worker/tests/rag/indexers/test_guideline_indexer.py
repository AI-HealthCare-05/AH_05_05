from pathlib import Path

import pytest

from ai_worker.rag.indexers.guideline_indexer import (
    GuidelineIndexer,
)
from ai_worker.schemas.guideline import (
    GuidelineDocument,
    GuidelineMetadata,
)


class FakeLoader:
    def __init__(self) -> None:
        self.received_path: Path | None = None
        self.received_metadata: (
            GuidelineMetadata | None
        ) = None

    def load(
        self,
        file_path: Path,
        metadata: GuidelineMetadata,
    ) -> list[GuidelineDocument]:
        self.received_path = file_path
        self.received_metadata = metadata

        return [
            GuidelineDocument(
                content="PDF에서 추출한 원문입니다.",
                metadata=metadata.model_copy(
                    update={"page_number": 1}
                ),
            )
        ]


class FakeSplitter:
    def split(
        self,
        documents: list[GuidelineDocument],
    ) -> list[GuidelineDocument]:
        metadata = documents[0].metadata

        return [
            GuidelineDocument(
                content="첫 번째 가이드라인 청크",
                metadata=metadata,
            ),
            GuidelineDocument(
                content="두 번째 가이드라인 청크",
                metadata=metadata,
            ),
        ]


class EmptySplitter:
    def split(
        self,
        documents: list[GuidelineDocument],
    ) -> list[GuidelineDocument]:
        return []


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.received_texts: list[str] = []

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
        self.received_texts = texts

        return [
            [1.0, 0.0, 0.0]
            for _ in texts
        ]

    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.received_chunks: list[
            GuidelineDocument
        ] = []
        self.received_vectors: list[
            list[float]
        ] = []

    async def upsert_chunks(
        self,
        chunks: list[GuidelineDocument],
        vectors: list[list[float]],
    ) -> list[str]:
        self.received_chunks = chunks
        self.received_vectors = vectors

        return [
            "point-1",
            "point-2",
        ]


def build_metadata() -> GuidelineMetadata:
    return GuidelineMetadata(
        document_id="stroke-guideline-2020",
        title="Stroke Guideline",
        organization="Test Organization",
        condition="STROKE",
        care_phase="POST_DISCHARGE",
        topic="LIFESTYLE",
    )


async def test_index_pdf_connects_pipeline() -> None:
    loader = FakeLoader()
    splitter = FakeSplitter()
    embedding_provider = FakeEmbeddingProvider()
    vector_store = FakeVectorStore()

    indexer = GuidelineIndexer(
        loader=loader,
        splitter=splitter,
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )

    pdf_path = Path("stroke-guideline.pdf")
    metadata = build_metadata()

    point_ids = await indexer.index_pdf(
        pdf_path=pdf_path,
        metadata=metadata,
    )

    assert loader.received_path == pdf_path
    assert loader.received_metadata == metadata

    assert embedding_provider.received_texts == [
        "첫 번째 가이드라인 청크",
        "두 번째 가이드라인 청크",
    ]

    assert [
        chunk.content
        for chunk in vector_store.received_chunks
    ] == embedding_provider.received_texts

    assert vector_store.received_vectors == [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
    ]

    assert point_ids == [
        "point-1",
        "point-2",
    ]


async def test_index_pdf_rejects_empty_chunks() -> None:
    indexer = GuidelineIndexer(
        loader=FakeLoader(),
        splitter=EmptySplitter(),
        embedding_provider=(
            FakeEmbeddingProvider()
        ),
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(
        ValueError,
        match="청크",
    ):
        await indexer.index_pdf(
            pdf_path=Path(
                "stroke-guideline.pdf"
            ),
            metadata=build_metadata(),
        )
