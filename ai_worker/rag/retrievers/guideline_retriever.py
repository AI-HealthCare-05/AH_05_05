from ai_worker.domain.interfaces import (
    EmbeddingProvider,
)
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
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
        min_similarity_score: float = 0.65,
    ) -> None:
        if not 0.0 <= min_similarity_score <= 1.0:
            raise ValueError("최소 유사도 점수는 0 이상 1 이하여야 합니다.")

        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._min_similarity_score = min_similarity_score

    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        try:
            query_vector = await self._embedding_provider.embed_query(search_query.query)
        except Exception as error:
            raise GuidelineRetrievalError(
                stage=(RetrievalFailureStage.EMBEDDING),
                message=("가이드라인 검색을 위한 질문 임베딩 생성에 실패했습니다."),
            ) from error

        try:
            results = await self._vector_store.search(
                query_vector=query_vector,
                search_query=search_query,
            )
            filtered_results = self._filter_by_similarity(results)

            if filtered_results or search_query.topic is None:
                return filtered_results

            fallback_query = search_query.model_copy(update={"topic": None})
            fallback_results = await self._vector_store.search(
                query_vector=query_vector,
                search_query=fallback_query,
            )

            return self._filter_by_similarity(fallback_results)
        except Exception as error:
            raise GuidelineRetrievalError(
                stage=(RetrievalFailureStage.VECTOR_STORE),
                message=("공공 가이드라인 벡터 검색에 실패했습니다."),
            ) from error

    def _filter_by_similarity(
        self,
        results: list[RetrievedGuidelineChunk],
    ) -> list[RetrievedGuidelineChunk]:
        return [
            result
            for result in results
            if (result.similarity_score is not None and result.similarity_score >= self._min_similarity_score)
        ]
