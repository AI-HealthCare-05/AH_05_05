import math
from dataclasses import dataclass

from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeQueryEvaluationResult,
)


@dataclass(frozen=True)
class KnowledgeEvaluationMetrics:
    hit_at_5: float
    mrr: float
    citation_accuracy: float
    duplicate_retrieval_rate: float
    wrong_entity_mixing_count: int
    search_p95_ms: float


def calculate_knowledge_evaluation_metrics(
    results: list[KnowledgeQueryEvaluationResult],
) -> KnowledgeEvaluationMetrics:
    """질문별 결과에서 release 평가 집계값을 한 가지 계약으로 계산합니다."""

    if not results:
        raise ValueError("평가 집계에는 질문별 결과가 하나 이상 필요합니다.")

    query_count = len(results)
    total_retrieved = sum(result.retrieved_count for result in results)
    total_relevant = sum(result.relevant_count for result in results)
    total_duplicates = sum(result.duplicate_count for result in results)
    ordered_latency = sorted(result.search_latency_ms for result in results)
    p95_rank = max(math.ceil(0.95 * query_count) - 1, 0)

    return KnowledgeEvaluationMetrics(
        hit_at_5=round(
            sum(result.hit_at_5 for result in results) / query_count,
            6,
        ),
        mrr=round(
            sum(result.reciprocal_rank for result in results) / query_count,
            6,
        ),
        citation_accuracy=round(
            total_relevant / total_retrieved if total_retrieved else 0.0,
            6,
        ),
        duplicate_retrieval_rate=round(
            total_duplicates / total_retrieved if total_retrieved else 0.0,
            6,
        ),
        wrong_entity_mixing_count=sum(result.wrong_entity_mixing_count for result in results),
        search_p95_ms=round(ordered_latency[p95_rank], 3),
    )
