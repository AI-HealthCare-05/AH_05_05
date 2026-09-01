from pathlib import Path

from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
    KnowledgeReleaseDecision,
)
from scripts import compare_knowledge_releases as module


def build_report(collection_name: str, *, mrr: float) -> KnowledgeEvaluationReport:
    return KnowledgeEvaluationReport(
        dataset_version=f"{collection_name}-dataset",
        collection_name=collection_name,
        query_count=1,
        hit_at_5=1.0,
        mrr=mrr,
        citation_accuracy=1.0,
        duplicate_retrieval_rate=0.0,
        wrong_entity_mixing_count=0,
        search_p95_ms=10.0,
        evaluation_contract_hash="same-contract",
        accuracy_passed=True,
        latency_passed=True,
        passed=True,
        query_results=[
            KnowledgeQueryEvaluationResult(
                query_id="q1",
                retrieved_document_ids=["doc"],
                hit_at_5=True,
                reciprocal_rank=mrr,
                relevant_count=1,
                retrieved_count=1,
                duplicate_count=0,
                wrong_entity_mixing_count=0,
                search_latency_ms=10.0,
            )
        ],
    )


def test_compare_files_writes_activation_recommendation(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "comparison.json"
    baseline_path.write_text(
        build_report("v1", mrr=0.7).model_dump_json(),
        encoding="utf-8",
    )
    candidate_path.write_text(
        build_report("v2", mrr=0.9).model_dump_json(),
        encoding="utf-8",
    )

    result = module.compare_files(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        output_path=output_path,
    )

    assert result.decision == KnowledgeReleaseDecision.ACTIVATE
    assert output_path.exists()
