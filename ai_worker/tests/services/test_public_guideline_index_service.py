from pathlib import Path

from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
    GuidelineManifestDocument,
)
from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexRequest,
)
from ai_worker.services.public_guideline_index_service import (
    PublicGuidelineIndexService,
)


class FakeManifestLoader:
    def __init__(
        self,
        manifest: GuidelineManifest,
    ) -> None:
        self._manifest = manifest
        self.received_path: Path | None = None

    def load(
        self,
        manifest_path: Path,
    ) -> GuidelineManifest:
        self.received_path = manifest_path
        return self._manifest


class FakeManifestIndexer:
    def __init__(self) -> None:
        self.received_manifest: GuidelineManifest | None = None

    async def index_manifest(
        self,
        manifest: GuidelineManifest,
    ) -> dict[str, list[str]]:
        self.received_manifest = manifest

        return {
            "stroke-2020": [
                "point-1",
                "point-2",
            ],
            "heart-failure-2024": [
                "point-3",
            ],
        }


class RecordingIndexerFactory:
    def __init__(
        self,
        indexer: FakeManifestIndexer,
    ) -> None:
        self._indexer = indexer
        self.received_chunk_size: int | None = None
        self.received_chunk_overlap: int | None = None

    def __call__(
        self,
        chunk_size: int,
        chunk_overlap: int,
    ) -> FakeManifestIndexer:
        self.received_chunk_size = chunk_size
        self.received_chunk_overlap = chunk_overlap

        return self._indexer


async def test_execute_indexes_manifest_documents() -> None:
    manifest = GuidelineManifest(
        documents=[
            GuidelineManifestDocument(
                file_path=Path("stroke.pdf"),
                document_id="stroke-2020",
                title="Stroke Guideline",
                condition="STROKE",
            ),
            GuidelineManifestDocument(
                file_path=Path("heart-failure.pdf"),
                document_id="heart-failure-2024",
                title="Heart Failure Guideline",
                condition="HEART_FAILURE",
            ),
        ]
    )

    manifest_loader = FakeManifestLoader(manifest=manifest)
    indexer = FakeManifestIndexer()
    indexer_factory = RecordingIndexerFactory(indexer=indexer)

    service = PublicGuidelineIndexService(
        manifest_loader=manifest_loader,
        indexer_factory=indexer_factory,
    )

    request = PublicGuidelineIndexRequest(
        job_id="index-job-1",
        manifest_path=Path("data/public_guidelines/manifest.json"),
        chunk_size=800,
        chunk_overlap=100,
    )

    result = await service.execute(request)

    assert manifest_loader.received_path == (request.manifest_path)
    assert indexer_factory.received_chunk_size == 800
    assert indexer_factory.received_chunk_overlap == 100
    assert indexer.received_manifest == manifest

    assert result.job_id == "index-job-1"
    assert result.indexed_document_count == 2
    assert result.indexed_chunk_count == 3
    assert result.point_ids_by_document == {
        "stroke-2020": [
            "point-1",
            "point-2",
        ],
        "heart-failure-2024": [
            "point-3",
        ],
    }
