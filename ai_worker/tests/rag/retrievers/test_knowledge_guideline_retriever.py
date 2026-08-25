import pytest

from ai_worker.rag.errors import GuidelineRetrievalError
from ai_worker.rag.retrievers.knowledge_guideline_retriever import (
    KnowledgeGuidelineRetriever,
)
from ai_worker.schemas.guideline import GuidelineSearchQuery
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)


class FakeEmbeddingProvider:
    async def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FailingEmbeddingProvider:
    async def embed_query(self, query: str) -> list[float]:
        raise RuntimeError("embedding failed")


class RecordingKnowledgeStore:
    def __init__(
        self,
        results: list[RetrievedKnowledgeChunk],
    ) -> None:
        self.results = results
        self.received_vector: list[float] | None = None
        self.received_query: KnowledgeSearchQuery | None = None

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]:
        self.received_vector = query_vector
        self.received_query = search_query
        return self.results


def build_chunk(
    *,
    score: float = 0.91,
    document_type: KnowledgeDocumentType = (KnowledgeDocumentType.SUPPLEMENT_CODE),
    section_type: KnowledgeSectionType = KnowledgeSectionType.CAUTION,
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="knowledge-point-1",
        similarity_score=score,
        chunk_id="a" * 64,
        content="비타민 B6 섭취 시 주의사항입니다.",
        embedding_text="[성분] 비타민 B6 [섹션] 주의사항",
        token_count=20,
        metadata=KnowledgeChunkMetadata(
            source_id="mfds-supplement-code",
            document_id="vitamin-b6-document",
            title="건강기능식품 공전 비타민 B6",
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=document_type,
            dataset_version="knowledge-pilot-v1",
            source_url="https://example.test/vitamin-b6",
            ingredient_names=["비타민 B6"],
            section_type=section_type,
            section_title="섭취 시 주의사항",
            page_start=3,
            page_end=3,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


async def test_search_maps_lifestyle_filters_and_source_metadata() -> None:
    store = RecordingKnowledgeStore([build_chunk()])
    retriever = KnowledgeGuidelineRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-pilot-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search(
        GuidelineSearchQuery(
            query="비타민 B6 섭취 시 주의사항",
            condition="MEDICATION_KNOWLEDGE",
            topic="LIFESTYLE",
            limit=5,
        )
    )

    assert store.received_vector == [0.1, 0.2, 0.3]
    assert store.received_query is not None
    assert store.received_query.dataset_version == "knowledge-pilot-v1"
    assert KnowledgeDocumentType.SUPPLEMENT_CODE in (store.received_query.document_types)
    assert KnowledgeSectionType.CAUTION in store.received_query.section_types
    assert len(result) == 1
    assert result[0].vector_chunk_id == "knowledge-point-1"
    assert result[0].metadata.dataset_key == "MEDICATION_KNOWLEDGE"
    assert result[0].metadata.document_id == "vitamin-b6-document"
    assert result[0].metadata.organization == "식품의약품안전처"
    assert result[0].metadata.topic == "CAUTION"
    assert result[0].metadata.page_number == 3
    assert result[0].metadata.license == "PUBLIC"


async def test_search_maps_warning_sign_to_safety_sections() -> None:
    store = RecordingKnowledgeStore([])
    retriever = KnowledgeGuidelineRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-pilot-v1",
    )

    await retriever.search(
        GuidelineSearchQuery(
            query="복용 후 어지러움 부작용 사례",
            condition="MEDICATION_KNOWLEDGE",
            topic="WARNING_SIGN",
        )
    )

    assert store.received_query is not None
    assert set(store.received_query.section_types) == {
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.ADVERSE_EVENT,
        KnowledgeSectionType.CASE_SUMMARY,
        KnowledgeSectionType.ASSESSMENT,
    }


async def test_search_excludes_chunks_below_similarity_threshold() -> None:
    store = RecordingKnowledgeStore(
        [
            build_chunk(score=0.8),
            build_chunk(score=0.4),
        ]
    )
    retriever = KnowledgeGuidelineRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-pilot-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search(
        GuidelineSearchQuery(
            query="비타민 B6",
            condition="MEDICATION_KNOWLEDGE",
        )
    )

    assert len(result) == 1
    assert result[0].similarity_score == 0.8


async def test_search_converts_embedding_failure_to_retrieval_error() -> None:
    retriever = KnowledgeGuidelineRetriever(
        embedding_provider=FailingEmbeddingProvider(),
        vector_store=RecordingKnowledgeStore([]),
        dataset_version="knowledge-pilot-v1",
    )

    with pytest.raises(
        GuidelineRetrievalError,
        match="질문 임베딩",
    ):
        await retriever.search(
            GuidelineSearchQuery(
                query="비타민 B6",
                condition="MEDICATION_KNOWLEDGE",
            )
        )
