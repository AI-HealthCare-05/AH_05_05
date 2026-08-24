from pathlib import Path
from typing import Protocol

from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
)
from ai_worker.schemas.public_guideline_index_job import (
    PublicGuidelineIndexRequest,
    PublicGuidelineIndexResult,
)


class ManifestLoader(Protocol):
    def load(
        self,
        manifest_path: Path,
    ) -> GuidelineManifest: ...


class ManifestIndexer(Protocol):
    async def index_manifest(
        self,
        manifest: GuidelineManifest,
    ) -> dict[str, list[str]]: ...


class ManifestIndexerFactory(Protocol):
    def __call__(
        self,
        chunk_size: int,
        chunk_overlap: int,
    ) -> ManifestIndexer: ...


class PublicGuidelineIndexService:
    def __init__(
        self,
        manifest_loader: ManifestLoader,
        indexer_factory: ManifestIndexerFactory,
    ) -> None:
        self._manifest_loader = manifest_loader
        self._indexer_factory = indexer_factory

    async def execute(
        self,
        request: PublicGuidelineIndexRequest,
    ) -> PublicGuidelineIndexResult:
        manifest = self._manifest_loader.load(request.manifest_path)

        indexer = self._indexer_factory(
            request.chunk_size,
            request.chunk_overlap,
        )

        point_ids_by_document = await indexer.index_manifest(manifest)

        indexed_chunk_count = sum(len(point_ids) for point_ids in (point_ids_by_document.values()))

        return PublicGuidelineIndexResult(
            job_id=request.job_id,
            indexed_document_count=len(point_ids_by_document),
            indexed_chunk_count=indexed_chunk_count,
            point_ids_by_document=(point_ids_by_document),
        )
