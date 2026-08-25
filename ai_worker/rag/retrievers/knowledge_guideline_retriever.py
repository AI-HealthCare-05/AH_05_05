from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)


class KnowledgeSearchStore(Protocol):
    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]: ...


class KnowledgeGuidelineRetriever:
    """새 Knowledge 검색 결과를 기존 Chat 출처 계약으로 변환한다."""

    _LIFESTYLE_DOCUMENT_TYPES = [
        KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
        KnowledgeDocumentType.SUPPLEMENT_CODE,
        KnowledgeDocumentType.RESEARCH_ARTICLE,
    ]
    _LIFESTYLE_SECTION_TYPES = [
        KnowledgeSectionType.OVERVIEW,
        KnowledgeSectionType.SUMMARY,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.INTERACTION,
        KnowledgeSectionType.RESULTS,
        KnowledgeSectionType.CONCLUSION,
    ]
    _WARNING_SECTION_TYPES = [
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.ADVERSE_EVENT,
        KnowledgeSectionType.CASE_SUMMARY,
        KnowledgeSectionType.ASSESSMENT,
    ]

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: KnowledgeSearchStore,
        dataset_version: str,
        min_similarity_score: float = 0.65,
    ) -> None:
        normalized_version = dataset_version.strip()
        if not normalized_version:
            raise ValueError("Knowledge dataset_version은 비어 있을 수 없습니다.")
        if not 0.0 <= min_similarity_score <= 1.0:
            raise ValueError("최소 유사도 점수는 0 이상 1 이하여야 합니다.")

        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._dataset_version = normalized_version
        self._min_similarity_score = min_similarity_score

    async def search(
        self,
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        try:
            query_vector = await self._embedding_provider.embed_query(search_query.query)
        except Exception as error:
            raise GuidelineRetrievalError(
                stage=RetrievalFailureStage.EMBEDDING,
                message="Knowledge 검색을 위한 질문 임베딩 생성에 실패했습니다.",
            ) from error

        try:
            knowledge_results = await self._vector_store.search(
                query_vector=query_vector,
                search_query=self._build_knowledge_query(search_query),
            )
        except Exception as error:
            raise GuidelineRetrievalError(
                stage=RetrievalFailureStage.VECTOR_STORE,
                message="약·영양제 Knowledge 벡터 검색에 실패했습니다.",
            ) from error

        return [
            self._to_guideline_chunk(result)
            for result in knowledge_results
            if result.similarity_score >= self._min_similarity_score
        ]

    def _build_knowledge_query(
        self,
        search_query: GuidelineSearchQuery,
    ) -> KnowledgeSearchQuery:
        document_types: list[KnowledgeDocumentType] = []
        section_types: list[KnowledgeSectionType] = []

        if search_query.topic == "LIFESTYLE":
            document_types = list(self._LIFESTYLE_DOCUMENT_TYPES)
            section_types = list(self._LIFESTYLE_SECTION_TYPES)
        elif search_query.topic == "WARNING_SIGN":
            section_types = list(self._WARNING_SECTION_TYPES)

        return KnowledgeSearchQuery(
            query=search_query.query,
            dataset_version=self._dataset_version,
            document_types=document_types,
            section_types=section_types,
            limit=search_query.limit,
        )

    @staticmethod
    def _to_guideline_chunk(
        chunk: RetrievedKnowledgeChunk,
    ) -> RetrievedGuidelineChunk:
        metadata = chunk.metadata
        return RetrievedGuidelineChunk(
            vector_chunk_id=chunk.point_id,
            content=chunk.content,
            similarity_score=chunk.similarity_score,
            metadata=GuidelineMetadata(
                dataset_key="MEDICATION_KNOWLEDGE",
                dataset_version=metadata.dataset_version,
                document_id=metadata.document_id,
                title=metadata.title,
                organization=metadata.provider,
                language="ko",
                document_type=metadata.document_type.value,
                condition="MEDICATION_KNOWLEDGE",
                topic=metadata.section_type.value,
                section_title=metadata.section_title,
                page_number=metadata.page_start,
                source_url=metadata.source_url,
                license=metadata.access_scope.value,
            ),
        )
