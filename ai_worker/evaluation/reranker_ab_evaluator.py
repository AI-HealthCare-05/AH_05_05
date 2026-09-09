import math

from ai_worker.rag.rerankers.candidate_reranker import CandidateReranker
from ai_worker.schemas.medication_search_evaluation import (
    RerankerABReport,
    RerankerActivationDecision,
    RerankerEvaluationCandidate,
    RerankerEvaluationCase,
    RerankerEvaluationCaseResult,
    RerankerEvaluationEligibility,
    RerankerEvaluationMetrics,
)


class RerankerABEvaluator:
    """실제 검색 경로를 변경하지 않는 Top-30 후보 재정렬 평가기다."""

    _FINAL_TOP_K = 5
    _CANDIDATE_TOP_K = 30
    _EPSILON = 1e-9

    def __init__(
        self,
        *,
        reranker: CandidateReranker,
        max_p95_increase_ms: float = 1_000.0,
    ) -> None:
        self._reranker = reranker
        self._max_p95_increase_ms = max_p95_increase_ms

    def evaluate(self, *, cases: list[RerankerEvaluationCase]) -> RerankerABReport:
        if not cases:
            raise ValueError("reranker A/B 평가에는 질문이 하나 이상 필요합니다.")

        results: list[RerankerEvaluationCaseResult] = []
        eligible_results: list[RerankerEvaluationCaseResult] = []
        for case in cases:
            result = self._evaluate_case(case)
            results.append(result)
            if result.eligibility == RerankerEvaluationEligibility.ELIGIBLE:
                eligible_results.append(result)

        baseline = self._metrics(eligible_results, reranked=False) if eligible_results else None
        reranked = self._metrics(eligible_results, reranked=True) if eligible_results else None
        blocking_reasons = self._blocking_reasons(
            baseline=baseline,
            reranked=reranked,
        )
        return RerankerABReport(
            max_p95_increase_ms=self._max_p95_increase_ms,
            eligible_query_count=len(eligible_results),
            excluded_query_count=len(results) - len(eligible_results),
            baseline=baseline,
            reranked=reranked,
            decision=(
                RerankerActivationDecision.ELIGIBLE_FOR_CONTROLLED_ACTIVATION
                if not blocking_reasons
                else RerankerActivationDecision.KEEP_RUNTIME_DISABLED
            ),
            blocking_reasons=blocking_reasons,
            results=results,
        )

    def _evaluate_case(self, case: RerankerEvaluationCase) -> RerankerEvaluationCaseResult:
        baseline_rank = self._first_relevant_rank(
            candidates=case.baseline_candidates,
            expected_document_ids=set(case.expected_document_ids),
        )
        eligibility = self._eligibility(baseline_rank)
        baseline_latency = case.search_latency_ms
        reranked_latency = case.search_latency_ms + case.reranker_latency_ms
        if eligibility != RerankerEvaluationEligibility.ELIGIBLE:
            return RerankerEvaluationCaseResult(
                query_id=case.query_id,
                eligibility=eligibility,
                baseline_first_relevant_rank=baseline_rank,
                baseline_search_latency_ms=baseline_latency,
                reranked_search_latency_ms=reranked_latency,
            )

        reranked_candidates = self._reranker.rerank(
            query=case.question,
            candidates=case.baseline_candidates,
        )
        self._validate_reranked_candidates(
            baseline_candidates=case.baseline_candidates,
            reranked_candidates=reranked_candidates,
        )
        reranked_rank = self._first_relevant_rank(
            candidates=reranked_candidates,
            expected_document_ids=set(case.expected_document_ids),
        )
        return RerankerEvaluationCaseResult(
            query_id=case.query_id,
            eligibility=eligibility,
            baseline_first_relevant_rank=baseline_rank,
            reranked_first_relevant_rank=reranked_rank,
            baseline_hit_at_5=self._hit_at_5(baseline_rank),
            reranked_hit_at_5=self._hit_at_5(reranked_rank),
            baseline_reciprocal_rank=self._reciprocal_rank(baseline_rank),
            reranked_reciprocal_rank=self._reciprocal_rank(reranked_rank),
            baseline_wrong_target_mixing_rate=self._wrong_target_mixing_rate(case.baseline_candidates),
            reranked_wrong_target_mixing_rate=self._wrong_target_mixing_rate(reranked_candidates),
            baseline_search_latency_ms=baseline_latency,
            reranked_search_latency_ms=reranked_latency,
        )

    @classmethod
    def _eligibility(cls, rank: int | None) -> RerankerEvaluationEligibility:
        if rank is None or rank > cls._CANDIDATE_TOP_K:
            return RerankerEvaluationEligibility.GOLD_NOT_IN_TOP_30
        if rank <= cls._FINAL_TOP_K:
            return RerankerEvaluationEligibility.ALREADY_IN_TOP_5
        return RerankerEvaluationEligibility.ELIGIBLE

    @staticmethod
    def _first_relevant_rank(
        *,
        candidates: list[RerankerEvaluationCandidate],
        expected_document_ids: set[str],
    ) -> int | None:
        return next(
            (
                rank
                for rank, candidate in enumerate(candidates, start=1)
                if candidate.document_id in expected_document_ids
            ),
            None,
        )

    @classmethod
    def _hit_at_5(cls, rank: int | None) -> bool:
        return rank is not None and rank <= cls._FINAL_TOP_K

    @staticmethod
    def _reciprocal_rank(rank: int | None) -> float:
        return round(1 / rank, 6) if rank is not None else 0.0

    @classmethod
    def _wrong_target_mixing_rate(cls, candidates: list[RerankerEvaluationCandidate]) -> float:
        top_candidates = candidates[: cls._FINAL_TOP_K]
        if not top_candidates:
            return 0.0
        return round(
            sum(candidate.wrong_target for candidate in top_candidates) / len(top_candidates),
            6,
        )

    @classmethod
    def _metrics(
        cls,
        results: list[RerankerEvaluationCaseResult],
        *,
        reranked: bool,
    ) -> RerankerEvaluationMetrics:
        hit_values = [result.reranked_hit_at_5 if reranked else result.baseline_hit_at_5 for result in results]
        reciprocal_ranks = [
            result.reranked_reciprocal_rank if reranked else result.baseline_reciprocal_rank for result in results
        ]
        wrong_target_rates = [
            result.reranked_wrong_target_mixing_rate if reranked else result.baseline_wrong_target_mixing_rate
            for result in results
        ]
        latencies = [
            result.reranked_search_latency_ms if reranked else result.baseline_search_latency_ms for result in results
        ]
        if any(value is None for value in [*hit_values, *reciprocal_ranks, *wrong_target_rates]):
            raise ValueError("적격 reranker 평가 결과에는 모든 측정값이 필요합니다.")
        query_count = len(results)
        wrong_target_mixing_rate = round(sum(wrong_target_rates) / query_count, 6)
        return RerankerEvaluationMetrics(
            query_count=query_count,
            hit_at_5=round(sum(hit_values) / query_count, 6),
            mrr=round(sum(reciprocal_ranks) / query_count, 6),
            source_precision=round(1.0 - wrong_target_mixing_rate, 6),
            wrong_target_mixing_rate=wrong_target_mixing_rate,
            search_p95_ms=cls._percentile(latencies, percentile=0.95),
        )

    def _blocking_reasons(
        self,
        *,
        baseline: RerankerEvaluationMetrics | None,
        reranked: RerankerEvaluationMetrics | None,
    ) -> list[str]:
        if baseline is None or reranked is None:
            return ["NO_ELIGIBLE_TOP_30_CASES"]
        reasons = []
        if reranked.hit_at_5 <= baseline.hit_at_5 + self._EPSILON and reranked.mrr <= baseline.mrr + self._EPSILON:
            reasons.append("NO_ACCURACY_IMPROVEMENT")
        if reranked.source_precision + self._EPSILON < baseline.source_precision:
            reasons.append("SOURCE_PRECISION_REGRESSION")
        if reranked.wrong_target_mixing_rate > baseline.wrong_target_mixing_rate + self._EPSILON:
            reasons.append("WRONG_TARGET_MIXING_REGRESSION")
        if reranked.search_p95_ms > baseline.search_p95_ms + self._max_p95_increase_ms:
            reasons.append("SEARCH_P95_BUDGET_EXCEEDED")
        return reasons

    @staticmethod
    def _validate_reranked_candidates(
        *,
        baseline_candidates: list[RerankerEvaluationCandidate],
        reranked_candidates: list[RerankerEvaluationCandidate],
    ) -> None:
        if len(baseline_candidates) != len(reranked_candidates) or {
            candidate.document_id for candidate in baseline_candidates
        } != {candidate.document_id for candidate in reranked_candidates}:
            raise ValueError("reranker는 후보를 추가·삭제하지 않고 순서만 변경해야 합니다.")

    @staticmethod
    def _percentile(values: list[float], *, percentile: float) -> float:
        ordered = sorted(values)
        rank = max(math.ceil(percentile * len(ordered)) - 1, 0)
        return round(ordered[rank], 3)
