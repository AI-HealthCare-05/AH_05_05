from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineReport,
    MedicationSearchModeComparisonReport,
    MedicationSearchModeDecision,
)


class MedicationSearchModeComparator:
    """Dense 기준선에 대해 Hybrid를 정확도 우선으로 채택할지 판정한다."""

    _EPSILON = 1e-9

    def compare(
        self,
        *,
        dense: MedicationSearchBaselineReport,
        bm25: MedicationSearchBaselineReport,
        hybrid: MedicationSearchBaselineReport,
    ) -> MedicationSearchModeComparisonReport:
        blocking_reasons = self._contract_reasons(
            dense=dense,
            bm25=bm25,
            hybrid=hybrid,
        )
        accuracy_improved = (
            hybrid.hit_at_5 > dense.hit_at_5 + self._EPSILON
            or hybrid.mrr > dense.mrr + self._EPSILON
        )
        if not accuracy_improved:
            blocking_reasons.append("NO_ACCURACY_IMPROVEMENT")
        if not hybrid.passed:
            blocking_reasons.append("HYBRID_EVALUATION_FAILED")
        guardrails = (
            (
                hybrid.recall_at_20 + self._EPSILON < dense.recall_at_20,
                "RECALL_AT_20_REGRESSION",
            ),
            (
                hybrid.source_accuracy + self._EPSILON < dense.source_accuracy,
                "SOURCE_ACCURACY_REGRESSION",
            ),
            (
                hybrid.evidence_coverage_rate + self._EPSILON
                < dense.evidence_coverage_rate,
                "EVIDENCE_COVERAGE_REGRESSION",
            ),
            (
                hybrid.wrong_target_mixing_count
                > dense.wrong_target_mixing_count,
                "WRONG_TARGET_MIXING_REGRESSION",
            ),
            (
                hybrid.duplicate_retrieval_rate
                > dense.duplicate_retrieval_rate + self._EPSILON,
                "DUPLICATE_RETRIEVAL_REGRESSION",
            ),
        )
        blocking_reasons.extend(
            reason for regressed, reason in guardrails if regressed
        )
        warning_reasons = []
        if hybrid.search_p95_ms > dense.search_p95_ms + self._EPSILON:
            warning_reasons.append("SEARCH_P95_REGRESSION")

        return MedicationSearchModeComparisonReport(
            dense_collection_name=dense.collection_name,
            bm25_collection_name=bm25.collection_name,
            hybrid_collection_name=hybrid.collection_name,
            decision=(
                MedicationSearchModeDecision.ACTIVATE_HYBRID
                if not blocking_reasons
                else MedicationSearchModeDecision.KEEP_DENSE
            ),
            blocking_reasons=list(dict.fromkeys(blocking_reasons)),
            warning_reasons=warning_reasons,
            metric_deltas={
                "recall_at_20": round(
                    hybrid.recall_at_20 - dense.recall_at_20,
                    6,
                ),
                "hit_at_5": round(hybrid.hit_at_5 - dense.hit_at_5, 6),
                "mrr": round(hybrid.mrr - dense.mrr, 6),
                "source_accuracy": round(
                    hybrid.source_accuracy - dense.source_accuracy,
                    6,
                ),
                "evidence_coverage_rate": round(
                    hybrid.evidence_coverage_rate
                    - dense.evidence_coverage_rate,
                    6,
                ),
                "wrong_target_mixing_count": float(
                    hybrid.wrong_target_mixing_count
                    - dense.wrong_target_mixing_count
                ),
                "duplicate_retrieval_rate": round(
                    hybrid.duplicate_retrieval_rate
                    - dense.duplicate_retrieval_rate,
                    6,
                ),
                "search_p95_ms": round(
                    hybrid.search_p95_ms - dense.search_p95_ms,
                    3,
                ),
            },
        )

    @staticmethod
    def _contract_reasons(
        *,
        dense: MedicationSearchBaselineReport,
        bm25: MedicationSearchBaselineReport,
        hybrid: MedicationSearchBaselineReport,
    ) -> list[str]:
        reasons: list[str] = []
        if (
            dense.search_mode != KnowledgeSearchMode.DENSE
            or bm25.search_mode != KnowledgeSearchMode.BM25
            or hybrid.search_mode != KnowledgeSearchMode.HYBRID
        ):
            reasons.append("SEARCH_MODE_MISMATCH")
        if len(
            {
                dense.evaluation_file_sha256,
                bm25.evaluation_file_sha256,
                hybrid.evaluation_file_sha256,
            }
        ) != 1:
            reasons.append("EVALUATION_CONTRACT_MISMATCH")
        if len({dense.dataset_version, bm25.dataset_version, hybrid.dataset_version}) != 1:
            reasons.append("DATASET_VERSION_MISMATCH")
        if len({dense.query_count, bm25.query_count, hybrid.query_count}) != 1:
            reasons.append("QUERY_COUNT_MISMATCH")
        return reasons
