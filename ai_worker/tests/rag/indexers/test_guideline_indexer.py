from pathlib import Path

import pytest

from ai_worker.rag.indexers.guideline_indexer import (
    GuidelineIndexer,
)
from ai_worker.schemas.guideline import (
    GuidelineDocument,
    GuidelineMetadata,
)
from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
    GuidelineManifestDocument,
)


class FakeLoader:
    def __init__(self) -> None:
        self.received_path: Path | None = None
        self.received_metadata: GuidelineMetadata | None = None

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
                metadata=metadata.model_copy(update={"page_number": 1}),
            )
        ]


class BatchRecordingLoader(FakeLoader):
    def __init__(self) -> None:
        super().__init__()
        self.received_paths: list[Path] = []
        self.received_metadatas: list[GuidelineMetadata] = []

    def load(
        self,
        file_path: Path,
        metadata: GuidelineMetadata,
    ) -> list[GuidelineDocument]:
        self.received_paths.append(file_path)
        self.received_metadatas.append(metadata)

        return super().load(
            file_path=file_path,
            metadata=metadata,
        )


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

        return [[1.0, 0.0, 0.0] for _ in texts]

    async def embed_query(
        self,
        query: str,
    ) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.received_chunks: list[GuidelineDocument] = []
        self.received_vectors: list[list[float]] = []
        self.deleted_document_ids: list[str] = []

    async def delete_by_document_id(
        self,
        document_id: str,
    ) -> None:
        self.deleted_document_ids.append(document_id)

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


class RecordingEmbeddingProvider(FakeEmbeddingProvider):
    def __init__(
        self,
        events: list[str],
    ) -> None:
        super().__init__()
        self._events = events

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        self._events.append("embed")

        return await super().embed_documents(texts)


class RecordingVectorStore(FakeVectorStore):
    def __init__(
        self,
        events: list[str],
    ) -> None:
        super().__init__()
        self._events = events

    async def delete_by_document_id(
        self,
        document_id: str,
    ) -> None:
        self._events.append(f"delete:{document_id}")

    async def upsert_chunks(
        self,
        chunks: list[GuidelineDocument],
        vectors: list[list[float]],
    ) -> list[str]:
        self._events.append("upsert")

        return await super().upsert_chunks(
            chunks=chunks,
            vectors=vectors,
        )


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        raise RuntimeError("임베딩 생성 실패")


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

    assert [chunk.content for chunk in vector_store.received_chunks] == embedding_provider.received_texts

    assert vector_store.received_vectors == [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
    ]

    assert vector_store.deleted_document_ids == ["stroke-guideline-2020"]

    assert point_ids == [
        "point-1",
        "point-2",
    ]


async def test_index_pdf_rejects_empty_chunks() -> None:
    indexer = GuidelineIndexer(
        loader=FakeLoader(),
        splitter=EmptySplitter(),
        embedding_provider=(FakeEmbeddingProvider()),
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(
        ValueError,
        match="청크",
    ):
        await indexer.index_pdf(
            pdf_path=Path("stroke-guideline.pdf"),
            metadata=build_metadata(),
        )


async def test_index_pdf_replaces_existing_chunks_after_embedding() -> None:
    events: list[str] = []

    indexer = GuidelineIndexer(
        loader=FakeLoader(),
        splitter=FakeSplitter(),
        embedding_provider=(RecordingEmbeddingProvider(events)),
        vector_store=(RecordingVectorStore(events)),
    )

    metadata = build_metadata()

    await indexer.index_pdf(
        pdf_path=Path("stroke-guideline.pdf"),
        metadata=metadata,
    )

    assert events == [
        "embed",
        ("delete:stroke-guideline-2020"),
        "upsert",
    ]


async def test_index_pdf_keeps_existing_chunks_when_embedding_fails() -> None:
    vector_store = FakeVectorStore()

    indexer = GuidelineIndexer(
        loader=FakeLoader(),
        splitter=FakeSplitter(),
        embedding_provider=(FailingEmbeddingProvider()),
        vector_store=vector_store,
    )

    with pytest.raises(
        RuntimeError,
        match="임베딩 생성 실패",
    ):
        await indexer.index_pdf(
            pdf_path=Path("stroke-guideline.pdf"),
            metadata=build_metadata(),
        )

    assert vector_store.deleted_document_ids == []
    assert vector_store.received_chunks == []
    assert vector_store.received_vectors == []


async def test_index_manifest_indexes_all_documents() -> None:
    loader = BatchRecordingLoader()
    vector_store = FakeVectorStore()

    indexer = GuidelineIndexer(
        loader=loader,
        splitter=FakeSplitter(),
        embedding_provider=(FakeEmbeddingProvider()),
        vector_store=vector_store,
    )

    manifest = GuidelineManifest(
        documents=[
            GuidelineManifestDocument(
                file_path=Path("stroke-guideline.pdf"),
                document_id=("stroke-guideline-2020"),
                title="Stroke Guideline",
                organization=("Test Organization"),
                dataset_version="2020",
                publication_year=2020,
                language="en",
                condition="STROKE",
                care_phase="POST_DISCHARGE",
                topic="LIFESTYLE",
                source_url=("https://example.com/stroke"),
                license="TEST_LICENSE",
            ),
            GuidelineManifestDocument(
                file_path=Path("heart-failure-guideline.pdf"),
                document_id=("heart-failure-guideline-2021"),
                title=("Heart Failure Guideline"),
                organization=("Test Organization"),
                dataset_version="2021",
                publication_year=2021,
                language="en",
                condition="HEART_FAILURE",
                care_phase="POST_DISCHARGE",
                topic="LIFESTYLE",
                source_url=("https://example.com/heart-failure"),
                license="TEST_LICENSE",
            ),
        ]
    )

    result = await indexer.index_manifest(manifest)

    assert loader.received_paths == [
        Path("stroke-guideline.pdf"),
        Path("heart-failure-guideline.pdf"),
    ]

    assert [metadata.document_id for metadata in (loader.received_metadatas)] == [
        "stroke-guideline-2020",
        "heart-failure-guideline-2021",
    ]

    assert loader.received_metadatas[0].source_url == "https://example.com/stroke"
    assert loader.received_metadatas[0].license == "TEST_LICENSE"

    assert result == {
        "stroke-guideline-2020": [
            "point-1",
            "point-2",
        ],
        "heart-failure-guideline-2021": [
            "point-1",
            "point-2",
        ],
    }
