from ai_worker.evaluation.reranker_ab_evaluator import RerankerABEvaluator
from ai_worker.rag.rerankers.candidate_reranker import DeterministicScoreCandidateReranker
from ai_worker.schemas.medication_search_evaluation import (
    RerankerActivationDecision,
    RerankerEvaluationCandidate,
    RerankerEvaluationCase,
    RerankerEvaluationEligibility,
)


def test_evaluates_only_cases_with_gold_in_top_30_but_outside_top_5() -> None:
    report = RerankerABEvaluator(
        reranker=DeterministicScoreCandidateReranker(),
    ).evaluate(
        cases=[
            build_case(query_id="eligible", gold_rank=6),
            build_case(query_id="already-top-five", gold_rank=3),
            build_case(query_id="not-in-top-thirty", gold_rank=None),
        ],
    )

    assert report.eligible_query_count == 1
    assert report.excluded_query_count == 2
    assert [result.eligibility for result in report.results] == [
        RerankerEvaluationEligibility.ELIGIBLE,
        RerankerEvaluationEligibility.ALREADY_IN_TOP_5,
        RerankerEvaluationEligibility.GOLD_NOT_IN_TOP_30,
    ]
    assert report.baseline.hit_at_5 == 0.0
    assert report.reranked.hit_at_5 == 1.0
    assert report.baseline.mrr == round(1 / 6, 6)
    assert report.reranked.mrr == 1.0
    assert report.baseline.source_precision == report.reranked.source_precision
    assert report.reranked.wrong_target_mixing_rate == report.baseline.wrong_target_mixing_rate
    assert report.baseline.search_p95_ms == 120.0
    assert report.reranked.search_p95_ms == 150.0
    assert report.decision == RerankerActivationDecision.ELIGIBLE_FOR_CONTROLLED_ACTIVATION


def test_keeps_runtime_reranking_disabled_when_wrong_target_mixing_regresses() -> None:
    report = RerankerABEvaluator(
        reranker=DeterministicScoreCandidateReranker(),
    ).evaluate(
        cases=[
            build_case(
                query_id="unsafe-rerank",
                gold_rank=6,
                wrong_target_score=1.1,
                wrong_target_index=8,
            ),
        ],
    )

    assert report.decision == RerankerActivationDecision.KEEP_RUNTIME_DISABLED
    assert "WRONG_TARGET_MIXING_REGRESSION" in report.blocking_reasons
    assert "SOURCE_PRECISION_REGRESSION" in report.blocking_reasons


def test_keeps_runtime_reranking_disabled_without_accuracy_improvement_or_with_excessive_p95() -> None:
    report = RerankerABEvaluator(
        reranker=DeterministicScoreCandidateReranker(),
        max_p95_increase_ms=10.0,
    ).evaluate(
        cases=[
            build_case(
                query_id="slow-and-flat",
                gold_rank=6,
                gold_score=0.0,
                reranker_latency_ms=20.0,
            ),
        ],
    )

    assert report.decision == RerankerActivationDecision.KEEP_RUNTIME_DISABLED
    assert "NO_ACCURACY_IMPROVEMENT" in report.blocking_reasons
    assert "SEARCH_P95_BUDGET_EXCEEDED" in report.blocking_reasons


def build_case(
    *,
    query_id: str,
    gold_rank: int | None,
    gold_score: float = 1.0,
    wrong_target_score: float = 0.8,
    wrong_target_index: int = 1,
    reranker_latency_ms: float = 30.0,
) -> RerankerEvaluationCase:
    candidates = [
        RerankerEvaluationCandidate(
            document_id=("gold-document" if index == gold_rank else f"document-{index}"),
            wrong_target=(index == wrong_target_index),
            reranker_score=(
                gold_score
                if index == gold_rank
                else wrong_target_score
                if index == wrong_target_index
                else 0.5 - index / 1000
            ),
        )
        for index in range(1, 31)
    ]
    if gold_rank is None:
        candidates = [
            candidate.model_copy(update={"document_id": f"document-{index}"})
            for index, candidate in enumerate(candidates, start=1)
        ]
    return RerankerEvaluationCase(
        query_id=query_id,
        question="상호작용을 알려줘",
        expected_document_ids=["gold-document"],
        baseline_candidates=candidates,
        search_latency_ms=120.0,
        reranker_latency_ms=reranker_latency_ms,
    )
