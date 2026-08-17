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
        self._embedding_provider = (
            embedding_provider
        )
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
            raise ValueError(
                "인덱싱할 가이드라인 청크가 없습니다."
            )

        texts = [
            chunk.content
            for chunk in chunks
        ]

        vectors = (
            await self._embedding_provider
            .embed_documents(texts)
        )

        return await self._vector_store.upsert_chunks(
            chunks=chunks,
            vectors=vectors,
        )
