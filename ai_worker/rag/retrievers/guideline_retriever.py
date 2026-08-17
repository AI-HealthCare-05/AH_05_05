from ai_worker.domain.interfaces import (
    EmbeddingProvider,
)
from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)
from ai_worker.schemas.guideline import (
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)


class GuidelineRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: QdrantGuidelineStore,
    ) -> None:
        self._embedding_provider = (
            embedding_provider
        )
        self._vector_store = vector_store

    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        query_vector = (
            await self._embedding_provider
            .embed_query(search_query.query)
        )

        return await self._vector_store.search(
            query_vector=query_vector,
            search_query=search_query,
        )