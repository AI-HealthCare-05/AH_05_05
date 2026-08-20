from pathlib import Path

from ai_worker.domain.interfaces import (
    EmbeddingProvider,
)
from ai_worker.rag.loaders.pdf_loader import (
    PdfLoader,
)
from ai_worker.rag.splitters.guideline_splitter import (
    GuidelineSplitter,
)
from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
)
from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
)


class GuidelineIndexer:
    def __init__(
        self,
        loader: PdfLoader,
        splitter: GuidelineSplitter,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantGuidelineStore,
    ) -> None:
        self._loader = loader
        self._splitter = splitter
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    async def index_pdf(
        self,
        pdf_path: Path,
        metadata: GuidelineMetadata,
    ) -> list[str]:
        documents = self._loader.load(
            file_path=pdf_path,
            metadata=metadata,
        )

        chunks = self._splitter.split(documents)

        if not chunks:
            raise ValueError("인덱싱할 가이드라인 청크가 없습니다.")

        texts = [chunk.content for chunk in chunks]

        vectors = await self._embedding_provider.embed_documents(texts)

        previous_point_ids = await self._vector_store.list_point_ids_by_document_id(metadata.document_id)
        current_point_ids = await self._vector_store.upsert_chunks(
            chunks=chunks,
            vectors=vectors,
        )
        current_point_id_set = set(current_point_ids)
        obsolete_point_ids = [point_id for point_id in previous_point_ids if point_id not in current_point_id_set]
        if obsolete_point_ids:
            await self._vector_store.delete_points(obsolete_point_ids)

        return current_point_ids

    async def index_manifest(
        self,
        manifest: GuidelineManifest,
    ) -> dict[str, list[str]]:
        indexed_point_ids: dict[
            str,
            list[str],
        ] = {}

        for document in manifest.documents:
            metadata = GuidelineMetadata.model_validate(document.model_dump(exclude={"file_path"}))

            point_ids = await self.index_pdf(
                pdf_path=document.file_path,
                metadata=metadata,
            )

            indexed_point_ids[document.document_id] = point_ids

        return indexed_point_ids
