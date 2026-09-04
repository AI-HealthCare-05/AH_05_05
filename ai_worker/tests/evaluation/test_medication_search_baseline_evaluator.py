from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.evaluation.medication_search_baseline_evaluator import (
    MedicationSearchBaselineEvaluator,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeCandidateDiagnostic,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchTier,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineCase,
    MedicationSearchBaselineManifest,
)


class StaticCatalog:
    async def list_expressions(self) -> list[str]:
        return ["타이레놀", "아세트아미노펜", "마그네슘"]


class FakeRetriever:
    async def search_with_diagnostics(self, *, execution_plan):
        diagnostic = KnowledgeCandidateDiagnostic(
            document_id="acetaminophen-guide",
            chunk_id="a" * 64,
            search_tier=KnowledgeSearchTier.ENTITY,
            raw_rank=2,
            raw_similarity_score=0.72,
            boost_score=0.2,
            adjusted_score=0.92,
            adjusted_rank=1,
            entity_matched=True,
            section_matched=True,
            eligible=True,
            selected_in_top_5=True,
        )
        return KnowledgeRetrievalResult(
            chunks=[],
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=20,
                entity_filtered_count=20,
                broad_candidate_count=0,
                eligible_candidate_count=1,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=1,
                attempted_search_tiers=[KnowledgeSearchTier.ENTITY],
                selected_search_tier=KnowledgeSearchTier.ENTITY,
                candidate_diagnostics=[diagnostic],
            ),
        )


class PartialCoverageRetriever:
    async def search_with_diagnostics(self, *, execution_plan):
        chunk = RetrievedKnowledgeChunk(
            chunk_id="c" * 64,
            content="마그네슘은 에너지 이용에 필요합니다.",
            embedding_text="마그네슘 기능성",
            token_count=12,
            point_id="point-c",
            similarity_score=0.8,
            metadata=KnowledgeChunkMetadata(
                source_id="source-c",
                document_id="magnesium-guide",
                title="마그네슘 기능성",
                provider="시험기관",
                access_scope=KnowledgeAccessScope.PUBLIC,
                document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
                dataset_version="knowledge-full-v2-interaction-metadata",
                ingredient_names=["마그네슘"],
                section_type=KnowledgeSectionType.FUNCTION,
                page_start=1,
                page_end=1,
                chunk_index=0,
                content_hash="d" * 64,
            ),
        )
        return KnowledgeRetrievalResult(
            chunks=[chunk],
            diagnostics=KnowledgeRetrievalDiagnostics(
                raw_candidate_count=1,
                entity_filtered_count=1,
                broad_candidate_count=0,
                eligible_candidate_count=1,
                rejected_below_score_count=0,
                rejected_entity_mismatch_count=0,
                rejected_pair_mismatch_count=0,
                accepted_count=1,
                attempted_search_tiers=[KnowledgeSearchTier.ENTITY],
                selected_search_tier=KnowledgeSearchTier.ENTITY,
                candidate_diagnostics=[
                    KnowledgeCandidateDiagnostic(
                        document_id="magnesium-guide",
                        chunk_id=chunk.chunk_id,
                        search_tier=KnowledgeSearchTier.ENTITY,
                        raw_rank=1,
                        raw_similarity_score=0.8,
                        boost_score=0.1,
                        adjusted_score=0.9,
                        adjusted_rank=1,
                        entity_matched=True,
                        section_matched=True,
                        eligible=True,
                        selected_in_top_5=True,
                    )
                ],
            ),
        )


async def test_evaluate_measures_expression_and_candidate_baseline() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        query_builder=MedicationKnowledgeQueryBuilder(),
        knowledge_retriever=FakeRetriever(),
        timer=iter([0.0, 0.01, 1.0, 1.002]).__next__,
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="typo-brand",
                question="타이래놀 효능 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="AUTO_CORRECTED",
                expected_resolved_question="타이레놀 효능 알려줘",
                expected_entity_names=["타이레놀"],
                expected_document_ids=["acetaminophen-guide"],
            ),
            MedicationSearchBaselineCase(
                query_id="out-of-scope",
                question="오늘 배고파요",
                expected_scope="OUT_OF_SCOPE",
                expected_resolution_status="UNRESOLVED",
            ),
        ],
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=True,
        evaluation_file_sha256="f" * 64,
    )

    assert report.resolution_accuracy == 1.0
    assert report.scope_accuracy == 1.0
    assert report.correction_accuracy == 1.0
    assert report.false_correction_rate == 0.0
    assert report.recall_at_20 == 1.0
    assert report.hit_at_5 == 1.0
    assert report.mrr == 1.0
    assert report.fallback_rate == 0.0
    assert report.search_p50_ms == 10.0
    assert report.search_p95_ms == 10.0
    assert report.git_commit == "abc1234"
    assert report.working_tree_dirty is True
    assert report.evaluation_file_sha256 == "f" * 64
    assert report.results[0].candidate_first_relevant_rank == 1
    assert report.results[0].selected_document_ids == [
        "acetaminophen-guide",
    ]
    assert report.results[1].retrieval_executed is False


async def test_evaluate_measures_requested_answer_evidence_coverage() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        query_builder=MedicationKnowledgeQueryBuilder(),
        knowledge_retriever=PartialCoverageRetriever(),
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="partial-coverage",
                question="마그네슘의 효능과 주의사항을 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="UNCHANGED",
                expected_entity_names=["마그네슘"],
                expected_section_types=[
                    KnowledgeSectionType.FUNCTION,
                    KnowledgeSectionType.CAUTION,
                ],
                expected_document_ids=["magnesium-guide"],
            )
        ],
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.results[0].evidence_coverage_rate == 0.5
    assert report.evidence_coverage_rate == 0.5


async def test_evaluate_fails_when_no_evidence_case_returns_documents() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        query_builder=MedicationKnowledgeQueryBuilder(),
        knowledge_retriever=PartialCoverageRetriever(),
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="no-evidence",
                question="처음 보는 영양제의 주의사항을 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="UNRESOLVED",
                expect_no_evidence=True,
            )
        ],
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.results[0].passed is False
    assert "UNEXPECTED_EVIDENCE_RETRIEVED" in (
        report.results[0].failure_reasons
    )
