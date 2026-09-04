from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineReport,
    MedicationSearchModeComparisonReport,
    MedicationSearchModeDecision,
)
from scripts.compare_medication_search_modes import render_markdown


def build_report(mode: KnowledgeSearchMode) -> MedicationSearchBaselineReport:
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
        query_count=14,
        resolution_accuracy=1.0,
        scope_accuracy=1.0,
        correction_accuracy=1.0,
        false_correction_rate=0.0,
        ambiguity_accuracy=1.0,
        recall_at_20=0.8,
        hit_at_5=0.7,
        mrr=0.6,
        source_accuracy=0.9,
        evidence_coverage_rate=0.75,
        wrong_target_mixing_count=0,
        duplicate_retrieval_rate=0.0,
        fallback_rate=0.2,
        search_p50_ms=100.0,
        search_p95_ms=200.0,
        passed=False,
        results=[],
    )


def test_render_markdown_explains_accuracy_first_decision_and_all_modes() -> None:
    reports = {
        mode: build_report(mode)
        for mode in KnowledgeSearchMode
    }
    comparison = MedicationSearchModeComparisonReport(
        dense_collection_name="knowledge-dense",
        bm25_collection_name="knowledge-bm25",
        hybrid_collection_name="knowledge-hybrid",
        decision=MedicationSearchModeDecision.KEEP_DENSE,
        blocking_reasons=["NO_ACCURACY_IMPROVEMENT"],
    )

    rendered = render_markdown(
        reports=reports,
        comparison=comparison,
    )

    assert "정확도 우선" in rendered
    assert "DENSE" in rendered
    assert "BM25" in rendered
    assert "HYBRID" in rendered
    assert "근거 커버리지" in rendered
    assert "KEEP_DENSE" in rendered
