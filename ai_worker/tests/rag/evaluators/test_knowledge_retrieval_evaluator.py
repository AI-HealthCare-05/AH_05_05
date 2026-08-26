from collections.abc import Callable

from ai_worker.rag.evaluators.knowledge_retrieval_evaluator import (
    KnowledgeRetrievalEvaluator,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationCase,
    KnowledgeEvaluationManifest,
)


def build_result(
    marker: str,
    *,
    document_id: str,
    ingredient_names: list[str] | None = None,
    content_hash: str | None = None,
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id=f"point-{marker}",
        similarity_score=0.9,
        chunk_id=marker * 64,
        content=f"근거 {marker}",
        embedding_text=f"[문서] 시험\n[원문]\n근거 {marker}",
        token_count=10,
        metadata=KnowledgeChunkMetadata(
            source_id=f"source-{marker}",
            document_id=document_id,
            title="시험 문서",
            provider="시험 제공자",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
            dataset_version="knowledge-pilot-v1",
            ingredient_names=ingredient_names or [],
            section_type=KnowledgeSectionType.CAUTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=content_hash or marker * 64,
        ),
    )


class FakeEmbeddingProvider:
    model_name = "test-embedding"
    dimension = 3

    async def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        raise AssertionError("평가에서는 문서 임베딩을 호출하지 않습니다.")

    async def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class SequenceKnowledgeStore:
    collection_name = "knowledge_release"

    def __init__(
        self,
        responses: list[list[RetrievedKnowledgeChunk]],
    ) -> None:
        self._responses = iter(responses)
        self.received_queries: list[KnowledgeSearchQuery] = []

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]:
        self.received_queries.append(search_query)
        return next(self._responses)


def sequence_timer(values: list[float]) -> Callable[[], float]:
    iterator = iter(values)
    return lambda: next(iterator)


async def test_evaluate_computes_retrieval_metrics() -> None:
    duplicate_hash = "d" * 64
    store = SequenceKnowledgeStore(
        responses=[
            [
                build_result("x", document_id="document-x"),
                build_result(
                    "a",
                    document_id="document-a",
                    content_hash=duplicate_hash,
                ),
                build_result(
                    "b",
                    document_id="document-a",
                    content_hash=duplicate_hash,
                ),
            ],
            [build_result("z", document_id="document-z")],
        ]
    )
    evaluator = KnowledgeRetrievalEvaluator(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        timer=sequence_timer([0.0, 0.04, 1.0, 1.02]),
    )
    manifest = KnowledgeEvaluationManifest(
        dataset_version="knowledge-pilot-v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="case-1",
                query="비타민 B6 주의사항",
                expected_document_ids=["document-a"],
            ),
            KnowledgeEvaluationCase(
                query_id="case-2",
                query="철 주의사항",
                expected_document_ids=["document-b"],
            ),
        ],
    )

    report = await evaluator.evaluate(manifest)

    assert report.hit_at_5 == 0.5
    assert report.mrr == 0.25
    assert report.citation_accuracy == 0.5
    assert report.duplicate_retrieval_rate == 0.25
    assert report.search_p95_ms == 40.0
    assert report.passed is False
    assert [query.dataset_version for query in store.received_queries] == [
        "knowledge-pilot-v1",
        "knowledge-pilot-v1",
    ]


async def test_evaluate_counts_disjoint_entity_result_as_mixing() -> None:
    store = SequenceKnowledgeStore(
        responses=[
            [
                build_result(
                    "i",
                    document_id="iron-document",
                    ingredient_names=["철"],
                )
            ]
        ]
    )
    evaluator = KnowledgeRetrievalEvaluator(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        timer=sequence_timer([0.0, 0.01]),
    )
    manifest = KnowledgeEvaluationManifest(
        dataset_version="knowledge-pilot-v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="vitamin-b6",
                query="비타민 B6 주의사항",
                expected_document_ids=["vitamin-b6-document"],
                expected_ingredient_names=["비타민 B6"],
            )
        ],
    )

    report = await evaluator.evaluate(manifest)

    assert report.wrong_entity_mixing_count == 1
    assert report.query_results[0].wrong_entity_mixing_count == 1
    assert report.passed is False


async def test_evaluate_forwards_metadata_filters() -> None:
    store = SequenceKnowledgeStore(responses=[[]])
    evaluator = KnowledgeRetrievalEvaluator(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        timer=sequence_timer([0.0, 0.001]),
    )
    manifest = KnowledgeEvaluationManifest(
        dataset_version="knowledge-pilot-v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="filtered",
                query="임신 중 비타민 B6",
                expected_document_ids=["vitamin-b6-document"],
                ingredient_names=["비타민 B6"],
                special_populations=["임신부"],
                section_types=[KnowledgeSectionType.CAUTION],
                top_k=3,
            )
        ],
    )

    await evaluator.evaluate(manifest)

    query = store.received_queries[0]
    assert query.ingredient_names == ["비타민 B6"]
    assert query.special_populations == ["임신부"]
    assert query.section_types == [KnowledgeSectionType.CAUTION]
    assert query.limit == 3


async def test_evaluate_requires_expected_section_for_relevance() -> None:
    store = SequenceKnowledgeStore(
        responses=[
            [
                build_result(
                    "a",
                    document_id="vitamin-document",
                ).model_copy(
                    update={
                        "metadata": build_result(
                            "a",
                            document_id="vitamin-document",
                        ).metadata.model_copy(update={"section_type": KnowledgeSectionType.FUNCTION})
                    }
                )
            ]
        ]
    )
    evaluator = KnowledgeRetrievalEvaluator(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        timer=sequence_timer([0.0, 0.001]),
    )
    manifest = KnowledgeEvaluationManifest(
        dataset_version="knowledge-pilot-v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="daily-intake",
                query="일일 섭취량은?",
                expected_document_ids=["vitamin-document"],
                expected_section_types=[KnowledgeSectionType.DAILY_INTAKE],
            )
        ],
    )

    report = await evaluator.evaluate(manifest)

    assert report.hit_at_5 == 0.0
    assert report.citation_accuracy == 0.0
