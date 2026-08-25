import math
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.schemas.knowledge import (
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationCase,
    KnowledgeEvaluationManifest,
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
)


class KnowledgeSearchStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]: ...


class KnowledgeRetrievalEvaluator:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: KnowledgeSearchStore,
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._timer = timer

    async def evaluate(
        self,
        manifest: KnowledgeEvaluationManifest,
    ) -> KnowledgeEvaluationReport:
        query_results: list[KnowledgeQueryEvaluationResult] = []

        for case in manifest.cases:
            query_vector = await self._embedding_provider.embed_query(case.query)
            started_at = self._timer()
            retrieved = await self._vector_store.search(
                query_vector=query_vector,
                search_query=self._build_search_query(
                    case=case,
                    dataset_version=manifest.dataset_version,
                ),
            )
            latency_ms = (self._timer() - started_at) * 1000.0
            query_results.append(
                self._evaluate_query(
                    case=case,
                    retrieved=retrieved,
                    latency_ms=latency_ms,
                )
            )

        query_count = len(query_results)
        total_retrieved = sum(result.retrieved_count for result in query_results)
        total_relevant = sum(result.relevant_count for result in query_results)
        total_duplicates = sum(result.duplicate_count for result in query_results)
        wrong_entity_mixing_count = sum(result.wrong_entity_mixing_count for result in query_results)
        hit_at_5 = sum(result.hit_at_5 for result in query_results) / query_count
        mrr = sum(result.reciprocal_rank for result in query_results) / query_count
        citation_accuracy = total_relevant / total_retrieved if total_retrieved else 0.0
        duplicate_rate = total_duplicates / total_retrieved if total_retrieved else 0.0
        search_p95_ms = self._nearest_rank_p95([result.search_latency_ms for result in query_results])
        thresholds = manifest.thresholds
        passed = (
            hit_at_5 >= thresholds.min_hit_at_5
            and citation_accuracy >= thresholds.min_citation_accuracy
            and wrong_entity_mixing_count <= thresholds.max_wrong_entity_mixing_count
            and search_p95_ms <= thresholds.max_search_p95_ms
        )

        return KnowledgeEvaluationReport(
            dataset_version=manifest.dataset_version,
            collection_name=self._vector_store.collection_name,
            query_count=query_count,
            hit_at_5=round(hit_at_5, 6),
            mrr=round(mrr, 6),
            citation_accuracy=round(citation_accuracy, 6),
            duplicate_retrieval_rate=round(duplicate_rate, 6),
            wrong_entity_mixing_count=wrong_entity_mixing_count,
            search_p95_ms=round(search_p95_ms, 3),
            passed=passed,
            query_results=query_results,
        )

    @staticmethod
    def _build_search_query(
        *,
        case: KnowledgeEvaluationCase,
        dataset_version: str,
    ) -> KnowledgeSearchQuery:
        return KnowledgeSearchQuery(
            query=case.query,
            dataset_version=dataset_version,
            document_types=case.document_types,
            drug_names=case.drug_names,
            ingredient_names=case.ingredient_names,
            interaction_type=case.interaction_type,
            special_populations=case.special_populations,
            section_types=case.section_types,
            limit=case.top_k,
        )

    @staticmethod
    def _evaluate_query(
        *,
        case: KnowledgeEvaluationCase,
        retrieved: list[RetrievedKnowledgeChunk],
        latency_ms: float,
    ) -> KnowledgeQueryEvaluationResult:
        relevant_positions = [
            index
            for index, result in enumerate(retrieved, start=1)
            if KnowledgeRetrievalEvaluator._is_relevant(case, result)
        ]
        first_relevant_rank = relevant_positions[0] if relevant_positions else None
        seen_hashes: set[str] = set()
        duplicate_count = 0
        for result in retrieved:
            content_hash = result.metadata.content_hash
            if content_hash in seen_hashes:
                duplicate_count += 1
            else:
                seen_hashes.add(content_hash)

        wrong_entity_mixing_count = sum(
            KnowledgeRetrievalEvaluator._is_disjoint_entity_result(
                case,
                result,
            )
            for result in retrieved
        )

        return KnowledgeQueryEvaluationResult(
            query_id=case.query_id,
            retrieved_document_ids=[result.metadata.document_id for result in retrieved],
            hit_at_5=any(position <= 5 for position in relevant_positions),
            reciprocal_rank=(1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0),
            relevant_count=len(relevant_positions),
            retrieved_count=len(retrieved),
            duplicate_count=duplicate_count,
            wrong_entity_mixing_count=wrong_entity_mixing_count,
            search_latency_ms=round(max(latency_ms, 0.0), 3),
        )

    @staticmethod
    def _is_relevant(
        case: KnowledgeEvaluationCase,
        result: RetrievedKnowledgeChunk,
    ) -> bool:
        if result.metadata.document_id not in set(case.expected_document_ids):
            return False
        if case.expected_section_types and result.metadata.section_type not in set(case.expected_section_types):
            return False
        if case.expected_drug_names and set(result.metadata.drug_names).isdisjoint(case.expected_drug_names):
            return False
        if case.expected_ingredient_names and set(result.metadata.ingredient_names).isdisjoint(
            case.expected_ingredient_names
        ):
            return False
        return True

    @staticmethod
    def _is_disjoint_entity_result(
        case: KnowledgeEvaluationCase,
        result: RetrievedKnowledgeChunk,
    ) -> bool:
        expected = set(case.expected_drug_names) | set(case.expected_ingredient_names)
        if not expected:
            return False
        actual = set(result.metadata.drug_names) | set(result.metadata.ingredient_names)
        return bool(actual) and actual.isdisjoint(expected)

    @staticmethod
    def _nearest_rank_p95(values: list[float]) -> float:
        ordered = sorted(values)
        rank = max(math.ceil(0.95 * len(ordered)) - 1, 0)
        return ordered[rank]
