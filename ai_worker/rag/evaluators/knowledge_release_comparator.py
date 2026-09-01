from ai_worker.rag.evaluators.knowledge_evaluation_metrics import (
    calculate_knowledge_evaluation_metrics,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
    KnowledgeReleaseComparisonReport,
    KnowledgeReleaseDecision,
)


class KnowledgeReleaseComparator:
    """동일 평가 세트의 기준선과 후보 release를 정확도 우선으로 비교합니다."""

    _EPSILON = 1e-9

    def compare(
        self,
        *,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> KnowledgeReleaseComparisonReport:
        report_integrity_reasons = self._report_integrity_reasons(
            baseline,
            candidate,
        )
        blocking_reasons = [
            *report_integrity_reasons,
            *self._contract_reasons(baseline, candidate),
            *self._query_regression_reasons(baseline, candidate),
            *self._aggregate_regression_reasons(baseline, candidate),
        ]
        if candidate.accuracy_passed is False:
            blocking_reasons.append("CANDIDATE_ACCURACY_GATE_FAILED")
        warning_reasons = self._warning_reasons(baseline, candidate)
        accuracy_improved = not report_integrity_reasons and self._accuracy_improved(baseline, candidate)
        if not accuracy_improved:
            blocking_reasons.append("NO_ACCURACY_IMPROVEMENT")

        return KnowledgeReleaseComparisonReport(
            baseline_dataset_version=baseline.dataset_version,
            baseline_collection_name=baseline.collection_name,
            candidate_dataset_version=candidate.dataset_version,
            candidate_collection_name=candidate.collection_name,
            decision=(
                KnowledgeReleaseDecision.ACTIVATE if not blocking_reasons else KnowledgeReleaseDecision.KEEP_BASELINE
            ),
            accuracy_improved=accuracy_improved,
            blocking_reasons=blocking_reasons,
            warning_reasons=warning_reasons,
            metric_deltas={
                "hit_at_5": round(candidate.hit_at_5 - baseline.hit_at_5, 6),
                "mrr": round(candidate.mrr - baseline.mrr, 6),
                "citation_accuracy": round(
                    candidate.citation_accuracy - baseline.citation_accuracy,
                    6,
                ),
                "duplicate_retrieval_rate": round(
                    candidate.duplicate_retrieval_rate - baseline.duplicate_retrieval_rate,
                    6,
                ),
                "wrong_entity_mixing_count": float(
                    candidate.wrong_entity_mixing_count - baseline.wrong_entity_mixing_count
                ),
                "search_p95_ms": round(
                    candidate.search_p95_ms - baseline.search_p95_ms,
                    3,
                ),
            },
        )

    def _report_integrity_reasons(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> list[str]:
        reasons: list[str] = []
        if not self._aggregates_match_queries(baseline):
            reasons.append("BASELINE_REPORT_METRICS_MISMATCH")
        if not self._aggregates_match_queries(candidate):
            reasons.append("CANDIDATE_REPORT_METRICS_MISMATCH")
        return reasons

    def _aggregates_match_queries(
        self,
        report: KnowledgeEvaluationReport,
    ) -> bool:
        results = report.query_results
        if report.query_count != len(results) or not results:
            return False
        query_ids = [result.query_id for result in results]
        if len(query_ids) != len(set(query_ids)):
            return False

        expected = calculate_knowledge_evaluation_metrics(results)
        return (
            abs(report.hit_at_5 - expected.hit_at_5) <= self._EPSILON
            and abs(report.mrr - expected.mrr) <= self._EPSILON
            and abs(report.citation_accuracy - expected.citation_accuracy) <= self._EPSILON
            and abs(report.duplicate_retrieval_rate - expected.duplicate_retrieval_rate) <= self._EPSILON
            and report.wrong_entity_mixing_count == expected.wrong_entity_mixing_count
            and abs(report.search_p95_ms - expected.search_p95_ms) <= self._EPSILON
        )

    def _contract_reasons(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> list[str]:
        if (
            baseline.evaluation_contract_hash is None
            or candidate.evaluation_contract_hash is None
            or baseline.evaluation_contract_hash != candidate.evaluation_contract_hash
        ):
            return ["EVALUATION_CONTRACT_MISMATCH"]
        return []

    def _query_regression_reasons(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> list[str]:
        baseline_by_id = {result.query_id: result for result in baseline.query_results}
        candidate_by_id = {result.query_id: result for result in candidate.query_results}
        if baseline_by_id.keys() != candidate_by_id.keys():
            return ["QUERY_SET_MISMATCH"]

        reasons: list[str] = []
        for query_id in sorted(baseline_by_id):
            baseline_result = baseline_by_id[query_id]
            candidate_result = candidate_by_id[query_id]
            if baseline_result.hit_at_5 and not candidate_result.hit_at_5:
                reasons.append(f"QUERY_HIT_REGRESSION:{query_id}")
            if candidate_result.reciprocal_rank + self._EPSILON < (baseline_result.reciprocal_rank):
                reasons.append(f"QUERY_RANK_REGRESSION:{query_id}")
            if candidate_result.wrong_entity_mixing_count > (baseline_result.wrong_entity_mixing_count):
                reasons.append(f"QUERY_ENTITY_MIXING_REGRESSION:{query_id}")
            if self._query_citation_accuracy(candidate_result) + self._EPSILON < (
                self._query_citation_accuracy(baseline_result)
            ):
                reasons.append(f"QUERY_CITATION_ACCURACY_REGRESSION:{query_id}")
            if self._query_duplicate_rate(candidate_result) > (
                self._query_duplicate_rate(baseline_result) + self._EPSILON
            ):
                reasons.append(f"QUERY_DUPLICATE_RETRIEVAL_REGRESSION:{query_id}")
        return reasons

    @staticmethod
    def _query_citation_accuracy(
        result: KnowledgeQueryEvaluationResult,
    ) -> float:
        if result.retrieved_count == 0:
            return 0.0
        return result.relevant_count / result.retrieved_count

    @staticmethod
    def _query_duplicate_rate(
        result: KnowledgeQueryEvaluationResult,
    ) -> float:
        if result.retrieved_count == 0:
            return 0.0
        return result.duplicate_count / result.retrieved_count

    def _aggregate_regression_reasons(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> list[str]:
        comparisons = (
            (
                candidate.hit_at_5 + self._EPSILON < baseline.hit_at_5,
                "HIT_AT_5_REGRESSION",
            ),
            (
                candidate.mrr + self._EPSILON < baseline.mrr,
                "MRR_REGRESSION",
            ),
            (
                candidate.citation_accuracy + self._EPSILON < baseline.citation_accuracy,
                "CITATION_ACCURACY_REGRESSION",
            ),
            (
                candidate.wrong_entity_mixing_count > baseline.wrong_entity_mixing_count,
                "WRONG_ENTITY_MIXING_REGRESSION",
            ),
            (
                candidate.duplicate_retrieval_rate > baseline.duplicate_retrieval_rate + self._EPSILON,
                "DUPLICATE_RETRIEVAL_REGRESSION",
            ),
        )
        return [reason for regressed, reason in comparisons if regressed]

    def _warning_reasons(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> list[str]:
        reasons: list[str] = []
        if candidate.latency_passed is False:
            reasons.append("CANDIDATE_LATENCY_GATE_FAILED")
        if candidate.search_p95_ms > baseline.search_p95_ms + self._EPSILON:
            reasons.append("SEARCH_P95_REGRESSION")
        return reasons

    def _accuracy_improved(
        self,
        baseline: KnowledgeEvaluationReport,
        candidate: KnowledgeEvaluationReport,
    ) -> bool:
        return any(
            (
                candidate.hit_at_5 > baseline.hit_at_5 + self._EPSILON,
                candidate.mrr > baseline.mrr + self._EPSILON,
                candidate.citation_accuracy > baseline.citation_accuracy + self._EPSILON,
                candidate.wrong_entity_mixing_count < baseline.wrong_entity_mixing_count,
                candidate.duplicate_retrieval_rate < baseline.duplicate_retrieval_rate - self._EPSILON,
            )
        )
