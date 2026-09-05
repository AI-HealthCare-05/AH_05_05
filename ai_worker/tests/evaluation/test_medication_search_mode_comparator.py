from ai_worker.evaluation.medication_search_mode_comparator import (
    MedicationSearchModeComparator,
)
from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineReport,
    MedicationSearchModeDecision,
)


def build_report(
    *,
    mode: KnowledgeSearchMode,
    hit_at_5: float = 0.5,
    recall_at_20: float = 0.6,
    mrr: float = 0.4,
    source_accuracy: float = 0.8,
    evidence_coverage_rate: float = 0.5,
    wrong_target_mixing_count: int = 0,
    search_p95_ms: float = 100.0,
) -> MedicationSearchBaselineReport:
    return MedicationSearchBaselineReport(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name=f"knowledge-{mode.value.lower()}",
        search_mode=mode,
        min_similarity_score=0.65,
        final_top_k=5,
        candidate_top_k=20,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
        query_count=1,
        resolution_accuracy=1.0,
        scope_accuracy=1.0,
        correction_accuracy=1.0,
        false_correction_rate=0.0,
        ambiguity_accuracy=1.0,
        recall_at_20=recall_at_20,
        hit_at_5=hit_at_5,
        mrr=mrr,
        source_accuracy=source_accuracy,
        evidence_coverage_rate=evidence_coverage_rate,
        wrong_target_mixing_count=wrong_target_mixing_count,
        duplicate_retrieval_rate=0.0,
        fallback_rate=0.0,
        search_p50_ms=50.0,
        search_p95_ms=search_p95_ms,
        passed=True,
        results=[],
    )


def test_activates_hybrid_only_when_accuracy_improves_without_guardrail_regression() -> None:
    dense = build_report(mode=KnowledgeSearchMode.DENSE)
    bm25 = build_report(mode=KnowledgeSearchMode.BM25, hit_at_5=0.55)
    hybrid = build_report(
        mode=KnowledgeSearchMode.HYBRID,
        hit_at_5=0.6,
        mrr=0.5,
        evidence_coverage_rate=0.6,
    )

    comparison = MedicationSearchModeComparator().compare(
        dense=dense,
        bm25=bm25,
        hybrid=hybrid,
    )

    assert comparison.decision == MedicationSearchModeDecision.ACTIVATE_HYBRID
    assert comparison.blocking_reasons == []
    assert comparison.metric_deltas["hit_at_5"] == 0.1


def test_keeps_dense_when_only_latency_improves() -> None:
    dense = build_report(mode=KnowledgeSearchMode.DENSE)
    comparison = MedicationSearchModeComparator().compare(
        dense=dense,
        bm25=build_report(mode=KnowledgeSearchMode.BM25),
        hybrid=build_report(
            mode=KnowledgeSearchMode.HYBRID,
            search_p95_ms=20.0,
        ),
    )

    assert comparison.decision == MedicationSearchModeDecision.KEEP_DENSE
    assert "NO_ACCURACY_IMPROVEMENT" in comparison.blocking_reasons


def test_keeps_dense_when_hybrid_mixes_more_wrong_targets() -> None:
    dense = build_report(mode=KnowledgeSearchMode.DENSE)
    comparison = MedicationSearchModeComparator().compare(
        dense=dense,
        bm25=build_report(mode=KnowledgeSearchMode.BM25),
        hybrid=build_report(
            mode=KnowledgeSearchMode.HYBRID,
            hit_at_5=0.7,
            wrong_target_mixing_count=1,
        ),
    )

    assert comparison.decision == MedicationSearchModeDecision.KEEP_DENSE
    assert "WRONG_TARGET_MIXING_REGRESSION" in comparison.blocking_reasons


def test_keeps_dense_when_hybrid_loses_evidence_coverage() -> None:
    dense = build_report(mode=KnowledgeSearchMode.DENSE)
    comparison = MedicationSearchModeComparator().compare(
        dense=dense,
        bm25=build_report(mode=KnowledgeSearchMode.BM25),
        hybrid=build_report(
            mode=KnowledgeSearchMode.HYBRID,
            hit_at_5=0.7,
            evidence_coverage_rate=0.4,
        ),
    )

    assert comparison.decision == MedicationSearchModeDecision.KEEP_DENSE
    assert "EVIDENCE_COVERAGE_REGRESSION" in comparison.blocking_reasons


def test_keeps_dense_when_hybrid_fails_fixed_evaluation_contract() -> None:
    dense = build_report(mode=KnowledgeSearchMode.DENSE)
    hybrid = build_report(
        mode=KnowledgeSearchMode.HYBRID,
        hit_at_5=0.7,
    ).model_copy(update={"passed": False})

    comparison = MedicationSearchModeComparator().compare(
        dense=dense,
        bm25=build_report(mode=KnowledgeSearchMode.BM25),
        hybrid=hybrid,
    )

    assert comparison.decision == MedicationSearchModeDecision.KEEP_DENSE
    assert "HYBRID_EVALUATION_FAILED" in comparison.blocking_reasons
