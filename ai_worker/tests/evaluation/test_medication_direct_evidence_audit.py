from ai_worker.evaluation.medication_direct_evidence_audit import (
    DirectEvidenceAttribution,
    DirectEvidenceAuditReport,
    DirectEvidenceFailureStage,
    DirectEvidenceSearchTrace,
    DirectEvidenceTargetAttributionBuilder,
    DirectEvidenceTargetObservation,
    DirectEvidenceTracingStore,
    MedicationDirectEvidenceAuditor,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import QdrantKnowledgeSearchTrace
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan
from ai_worker.schemas.medication_search_evaluation import (
    MedicationEvaluationEvidenceKind,
    MedicationSearchBaselineCase,
)

PAIR_KEY = "a" * 64


def build_target_chunk() -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="gold-point",
        similarity_score=0.82,
        chunk_id="a" * 64,
        content="아세트아미노펜과 알코올의 직접 근거",
        embedding_text="아세트아미노펜 알코올",
        token_count=10,
        metadata=KnowledgeChunkMetadata(
            source_id="source-gold",
            document_id="kpicia_pharm_review-3ce7212b15e7c2de",
            title="아세트아미노펜과 알코올",
            provider="test",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.PHARM_REVIEW,
            dataset_version="knowledge-full-v15",
            drug_names=["아세트아미노펜"],
            food_names=["알코올"],
            interaction_pair_keys=[PAIR_KEY],
            section_type=KnowledgeSectionType.INTERACTION,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="b" * 64,
        ),
    )


def test_attribution_marks_target_dropped_by_refiner() -> None:
    attribution = DirectEvidenceAttribution.from_observation(
        DirectEvidenceTargetObservation(
            query_id="drug-food-tylenol-alcohol",
            collection_name="medication_knowledge_full_v15",
            dataset_version="knowledge-full-v15",
            expected_document_id="kpicia_pharm_review-3ce7212b15e7c2de",
            target_payload_present=True,
            payload_dataset_versions=["knowledge-full-v15"],
            payload_pair_key_matched=True,
            exact_pair_raw_rank=3,
            refined_rank=None,
        )
    )

    assert attribution.first_failure_stage is DirectEvidenceFailureStage.REFINER_DROPPED


def test_audit_report_counts_each_first_failure_stage_once() -> None:
    dropped = DirectEvidenceAttribution.from_observation(
        DirectEvidenceTargetObservation(
            query_id="drug-food-tylenol-alcohol",
            collection_name="medication_knowledge_full_v15",
            dataset_version="knowledge-full-v15",
            expected_document_id="gold-refiner",
            target_payload_present=True,
            payload_dataset_versions=["knowledge-full-v15"],
            payload_pair_key_matched=True,
            exact_pair_raw_rank=1,
            refined_rank=None,
        )
    )
    selected = DirectEvidenceAttribution.from_observation(
        DirectEvidenceTargetObservation(
            query_id="drug-food-warfarin-vitamin-k",
            collection_name="medication_knowledge_full_v15",
            dataset_version="knowledge-full-v15",
            expected_document_id="gold-selected",
            target_payload_present=True,
            payload_dataset_versions=["knowledge-full-v15"],
            payload_pair_key_matched=True,
            exact_pair_raw_rank=1,
            refined_rank=1,
            selected_in_top_5=True,
        )
    )

    report = DirectEvidenceAuditReport.from_attributions(
        collection_name="medication_knowledge_full_v15",
        dataset_version="knowledge-full-v15",
        attributions=[dropped, selected],
    )

    assert report.target_count == 2
    assert report.stage_counts == {
        DirectEvidenceFailureStage.REFINER_DROPPED: 1,
        DirectEvidenceFailureStage.TOP_5: 1,
    }


def test_target_attribution_uses_exact_pair_trace_before_retrieval_diagnostics() -> None:
    target = build_target_chunk()
    attribution = DirectEvidenceTargetAttributionBuilder.build(
        query_id="drug-food-tylenol-alcohol",
        collection_name="medication_knowledge_full_v15",
        dataset_version="knowledge-full-v15",
        expected_document_id=target.metadata.document_id,
        expected_pair_keys=[PAIR_KEY],
        target_payloads=[target],
        search_traces=[
            DirectEvidenceSearchTrace(
                search_query=KnowledgeSearchQuery(
                    query="타이레놀과 술을 같이 먹어도 돼?",
                    dataset_version="knowledge-full-v15",
                    interaction_pair_keys=[PAIR_KEY],
                    limit=20,
                ),
                trace=QdrantKnowledgeSearchTrace(
                    raw_results=[target],
                    refined_results=[],
                ),
            )
        ],
        retrieval=KnowledgeRetrievalResult(
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=0,
                entity_filtered_count=0,
                broad_candidate_count=0,
                eligible_candidate_count=0,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=0,
            )
        ),
    )

    assert attribution.observation.exact_pair_raw_rank == 1
    assert attribution.observation.refined_rank is None
    assert attribution.first_failure_stage is DirectEvidenceFailureStage.REFINER_DROPPED


async def test_tracing_store_returns_refined_results_and_records_raw_trace() -> None:
    target = build_target_chunk()

    class FakeStore:
        async def search_with_trace(self, *, query_vector, search_query):
            assert query_vector == [1.0, 0.0, 0.0]
            assert search_query.query == "타이레놀과 술을 같이 먹어도 돼?"
            return QdrantKnowledgeSearchTrace(raw_results=[target], refined_results=[])

    tracing_store = DirectEvidenceTracingStore(store=FakeStore())
    results = await tracing_store.search(
        query_vector=[1.0, 0.0, 0.0],
        search_query=KnowledgeSearchQuery(
            query="타이레놀과 술을 같이 먹어도 돼?",
            dataset_version="knowledge-full-v15",
            interaction_pair_keys=[PAIR_KEY],
            limit=20,
        ),
    )

    assert results == []
    assert tracing_store.search_traces[0].trace.raw_results == [target]


async def test_auditor_keeps_gold_document_out_of_query_plan_inputs() -> None:
    target = build_target_chunk()

    class FakeStore:
        async def find_chunks_by_document_id(self, *, document_id):
            assert document_id == target.metadata.document_id
            return [target]

        async def search_with_trace(self, *, query_vector, search_query):
            assert target.metadata.document_id not in search_query.query
            return QdrantKnowledgeSearchTrace(
                raw_results=[target],
                refined_results=[target],
            )

    class FakeRetriever:
        def __init__(self, *, store) -> None:
            self._store = store

        async def search_with_diagnostics(
            self,
            *,
            execution_plan,
            audit_target_document_ids=None,
        ):
            assert execution_plan.query_plan.interaction_pair_keys == [PAIR_KEY]
            assert audit_target_document_ids == {target.metadata.document_id}
            await self._store.search(
                query_vector=[1.0, 0.0, 0.0],
                search_query=KnowledgeSearchQuery(
                    query=execution_plan.query_plan.expanded_query,
                    dataset_version="knowledge-full-v15",
                    interaction_pair_keys=[PAIR_KEY],
                    limit=20,
                ),
            )
            return KnowledgeRetrievalResult(
                chunks=[target],
                diagnostics=KnowledgeRetrievalDiagnostics(
                    raw_candidate_count=1,
                    entity_filtered_count=1,
                    broad_candidate_count=0,
                    eligible_candidate_count=1,
                    rejected_below_score_count=0,
                    rejected_entity_mismatch_count=0,
                    rejected_pair_mismatch_count=0,
                    accepted_count=1,
                ),
            )

    async def plan_question(question: str) -> MedicationKnowledgeQueryPlan:
        assert question == "타이레놀과 술을 같이 먹어도 돼?"
        return MedicationKnowledgeQueryPlan(
            original_query=question,
            expanded_query=question,
            interaction_pair_keys=[PAIR_KEY],
        )

    auditor = MedicationDirectEvidenceAuditor(
        collection_name="medication_knowledge_full_v15",
        dataset_version="knowledge-full-v15",
        vector_store=FakeStore(),
        query_planner=plan_question,
        retriever_factory=lambda store: FakeRetriever(store=store),
    )
    results = await auditor.audit_case(
        MedicationSearchBaselineCase(
            query_id="drug-food-tylenol-alcohol",
            question="타이레놀과 술을 같이 먹어도 돼?",
            expected_scope="IN_SCOPE",
            expected_resolution_status="UNCHANGED",
            expected_document_ids=[target.metadata.document_id],
            evidence_kind=MedicationEvaluationEvidenceKind.QDRANT_GOLD,
        )
    )

    assert results[0].first_failure_stage is DirectEvidenceFailureStage.TOP_5
