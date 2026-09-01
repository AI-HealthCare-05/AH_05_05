from ai_worker.rag.evaluators.knowledge_release_comparator import (
    KnowledgeReleaseComparator,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
    KnowledgeReleaseDecision,
)


def build_report(
    *,
    collection_name: str,
    hit_at_5: float = 1.0,
    mrr: float = 0.8,
    citation_accuracy: float = 0.7,
    duplicate_retrieval_rate: float = 0.1,
    wrong_entity_mixing_count: int = 0,
    search_p95_ms: float = 100.0,
    accuracy_passed: bool = True,
    latency_passed: bool = True,
    evaluation_contract_hash: str = "contract-hash",
    query_results: list[KnowledgeQueryEvaluationResult] | None = None,
) -> KnowledgeEvaluationReport:
    if query_results is None:
        query_results = []
        query_count = 10
        hit_count = round(hit_at_5 * query_count)
        total_retrieved = query_count * 10
        relevant_count = round(citation_accuracy * total_retrieved)
        duplicate_count = round(duplicate_retrieval_rate * total_retrieved)
        for index in range(query_count):
            per_query_relevant = relevant_count // query_count + (index < relevant_count % query_count)
            per_query_duplicates = duplicate_count // query_count + (index < duplicate_count % query_count)
            query_results.append(
                KnowledgeQueryEvaluationResult(
                    query_id=f"query-{index}",
                    retrieved_document_ids=["document"],
                    hit_at_5=index < hit_count,
                    reciprocal_rank=mrr,
                    relevant_count=per_query_relevant,
                    retrieved_count=10,
                    duplicate_count=per_query_duplicates,
                    wrong_entity_mixing_count=(1 if index < wrong_entity_mixing_count else 0),
                    search_latency_ms=search_p95_ms,
                )
            )
    return KnowledgeEvaluationReport(
        dataset_version=f"{collection_name}-dataset",
        collection_name=collection_name,
        query_count=len(query_results),
        hit_at_5=hit_at_5,
        mrr=mrr,
        citation_accuracy=citation_accuracy,
        duplicate_retrieval_rate=duplicate_retrieval_rate,
        wrong_entity_mixing_count=wrong_entity_mixing_count,
        search_p95_ms=search_p95_ms,
        accuracy_passed=accuracy_passed,
        latency_passed=latency_passed,
        evaluation_contract_hash=evaluation_contract_hash,
        passed=accuracy_passed and latency_passed,
        query_results=query_results,
    )


def test_recommends_activation_when_accuracy_improves_without_regression() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        mrr=0.9,
        citation_accuracy=0.8,
        duplicate_retrieval_rate=0.08,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.ACTIVATE
    assert comparison.accuracy_improved is True
    assert comparison.blocking_reasons == []


def test_recommends_activation_when_only_duplicate_rate_improves() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        duplicate_retrieval_rate=0.05,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.ACTIVATE
    assert comparison.accuracy_improved is True
    assert comparison.blocking_reasons == []


def test_keeps_baseline_when_candidate_aggregates_do_not_match_queries() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(collection_name="medication_knowledge_full_v2").model_copy(update={"mrr": 0.9})

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "CANDIDATE_REPORT_METRICS_MISMATCH" in comparison.blocking_reasons


def test_keeps_baseline_when_hit_rate_regresses() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        hit_at_5=0.9,
        mrr=0.95,
        citation_accuracy=0.9,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "HIT_AT_5_REGRESSION" in comparison.blocking_reasons


def test_keeps_baseline_when_only_latency_improves() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(collection_name="medication_knowledge_full_v2")

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "NO_ACCURACY_IMPROVEMENT" in comparison.blocking_reasons


def test_latency_regression_is_warning_when_accuracy_improves() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        mrr=0.9,
        search_p95_ms=500.0,
        latency_passed=False,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.ACTIVATE
    assert comparison.blocking_reasons == []
    assert "SEARCH_P95_REGRESSION" in comparison.warning_reasons
    assert "CANDIDATE_LATENCY_GATE_FAILED" in comparison.warning_reasons


def test_keeps_baseline_when_evaluation_contract_differs() -> None:
    baseline = build_report(collection_name="medication_knowledge_full_v1")
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        mrr=0.9,
        evaluation_contract_hash="different-contract",
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "EVALUATION_CONTRACT_MISMATCH" in comparison.blocking_reasons


def test_keeps_baseline_when_one_query_rank_regresses() -> None:
    baseline_query = KnowledgeQueryEvaluationResult(
        query_id="calcium-iron",
        retrieved_document_ids=["calcium-iron-paper"],
        hit_at_5=True,
        reciprocal_rank=1.0,
        relevant_count=1,
        retrieved_count=1,
        duplicate_count=0,
        wrong_entity_mixing_count=0,
        search_latency_ms=100.0,
    )
    candidate_query = baseline_query.model_copy(update={"reciprocal_rank": 0.5})
    baseline = build_report(
        collection_name="medication_knowledge_full_v1",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=1.0,
        duplicate_retrieval_rate=0.0,
        query_results=[baseline_query],
    )
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        hit_at_5=1.0,
        mrr=0.5,
        citation_accuracy=1.0,
        duplicate_retrieval_rate=0.0,
        query_results=[candidate_query],
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "QUERY_RANK_REGRESSION:calcium-iron" in comparison.blocking_reasons


def test_keeps_baseline_when_one_query_citation_accuracy_regresses() -> None:
    baseline_queries = [
        KnowledgeQueryEvaluationResult(
            query_id="query-a",
            retrieved_document_ids=["a", "b"],
            hit_at_5=True,
            reciprocal_rank=1.0,
            relevant_count=2,
            retrieved_count=2,
            duplicate_count=0,
            wrong_entity_mixing_count=0,
            search_latency_ms=100.0,
        ),
        KnowledgeQueryEvaluationResult(
            query_id="query-b",
            retrieved_document_ids=["c", "d"],
            hit_at_5=True,
            reciprocal_rank=1.0,
            relevant_count=0,
            retrieved_count=2,
            duplicate_count=0,
            wrong_entity_mixing_count=0,
            search_latency_ms=100.0,
        ),
    ]
    candidate_queries = [
        baseline_queries[0].model_copy(update={"relevant_count": 1}),
        baseline_queries[1].model_copy(update={"relevant_count": 2}),
    ]
    baseline = build_report(
        collection_name="medication_knowledge_full_v1",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=0.5,
        duplicate_retrieval_rate=0.0,
        query_results=baseline_queries,
    )
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=0.75,
        duplicate_retrieval_rate=0.0,
        query_results=candidate_queries,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "QUERY_CITATION_ACCURACY_REGRESSION:query-a" in comparison.blocking_reasons


def test_keeps_baseline_when_one_query_duplicate_rate_regresses() -> None:
    baseline_queries = [
        KnowledgeQueryEvaluationResult(
            query_id="query-a",
            retrieved_document_ids=["a", "b"],
            hit_at_5=True,
            reciprocal_rank=1.0,
            relevant_count=1,
            retrieved_count=2,
            duplicate_count=0,
            wrong_entity_mixing_count=0,
            search_latency_ms=100.0,
        ),
        KnowledgeQueryEvaluationResult(
            query_id="query-b",
            retrieved_document_ids=["c", "d"],
            hit_at_5=True,
            reciprocal_rank=1.0,
            relevant_count=1,
            retrieved_count=2,
            duplicate_count=2,
            wrong_entity_mixing_count=0,
            search_latency_ms=100.0,
        ),
    ]
    candidate_queries = [
        baseline_queries[0].model_copy(update={"duplicate_count": 1}),
        baseline_queries[1].model_copy(update={"relevant_count": 2, "duplicate_count": 0}),
    ]
    baseline = build_report(
        collection_name="medication_knowledge_full_v1",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=0.5,
        duplicate_retrieval_rate=0.5,
        query_results=baseline_queries,
    )
    candidate = build_report(
        collection_name="medication_knowledge_full_v2",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=0.75,
        duplicate_retrieval_rate=0.25,
        query_results=candidate_queries,
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "QUERY_DUPLICATE_RETRIEVAL_REGRESSION:query-a" in comparison.blocking_reasons


def test_keeps_baseline_when_report_contains_duplicate_query_ids() -> None:
    query = KnowledgeQueryEvaluationResult(
        query_id="duplicate",
        retrieved_document_ids=["a"],
        hit_at_5=True,
        reciprocal_rank=1.0,
        relevant_count=1,
        retrieved_count=1,
        duplicate_count=0,
        wrong_entity_mixing_count=0,
        search_latency_ms=100.0,
    )
    baseline = build_report(
        collection_name="medication_knowledge_full_v1",
        hit_at_5=1.0,
        mrr=1.0,
        citation_accuracy=1.0,
        duplicate_retrieval_rate=0.0,
        query_results=[query, query],
    )
    candidate = baseline.model_copy(
        update={
            "collection_name": "medication_knowledge_full_v2",
            "dataset_version": "medication_knowledge_full_v2-dataset",
        }
    )

    comparison = KnowledgeReleaseComparator().compare(
        baseline=baseline,
        candidate=candidate,
    )

    assert comparison.decision == KnowledgeReleaseDecision.KEEP_BASELINE
    assert "BASELINE_REPORT_METRICS_MISMATCH" in comparison.blocking_reasons
