from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.evaluation.medication_search_baseline_evaluator import (
    MedicationSearchBaselineEvaluator,
)
from ai_worker.schemas.interaction import InteractionEntityKind
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
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)
from ai_worker.schemas.medication_search_evaluation import (
    MedicationExpectedEntity,
    MedicationSearchBaselineCase,
    MedicationSearchBaselineManifest,
)


class StaticCatalog:
    async def list_expressions(self) -> list[str]:
        return ["타이레놀", "아세트아미노펜", "마그네슘"]


class TypedStaticCatalog:
    async def list_entries(self) -> list[MedicationCatalogEntry]:
        return [
            MedicationCatalogEntry(
                canonical_name="타이레놀",
                entity_type=MedicationQueryEntityType.BRAND_ALIAS,
                kind=InteractionEntityKind.DRUG,
                source=MedicationQueryEntitySource.RDBMS,
            )
        ]


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


class FailOnSearchRetriever:
    async def search_with_diagnostics(self, *, execution_plan):
        raise AssertionError("source-backed 엔터티가 없으면 RAG를 실행하면 안 됩니다.")


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


async def test_evaluate_passes_resolver_typed_entities_to_query_plan() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=TypedStaticCatalog(),
        ),
        knowledge_retriever=FakeRetriever(),
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="typed-brand",
                question="타이레놀의 효능을 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="UNCHANGED",
                expected_entity_names=["타이레놀"],
                expected_entities=[
                    MedicationExpectedEntity(
                        canonical_name="타이레놀",
                        entity_type=MedicationQueryEntityType.BRAND_ALIAS,
                        kind=InteractionEntityKind.DRUG,
                        expected_sources=[MedicationQueryEntitySource.RDBMS],
                    )
                ],
            )
        ],
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.results[0].observed_entities == [
        MedicationExpectedEntity(
            canonical_name="타이레놀",
            entity_type=MedicationQueryEntityType.BRAND_ALIAS,
            kind=InteractionEntityKind.DRUG,
            expected_sources=[MedicationQueryEntitySource.RDBMS],
        )
    ]
    assert report.results[0].passed is True


async def test_evaluate_measures_requested_answer_evidence_coverage() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
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
        knowledge_retriever=PartialCoverageRetriever(),
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="no-evidence",
                question="마그네슘의 주의사항을 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="UNCHANGED",
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
    assert "UNEXPECTED_EVIDENCE_RETRIEVED" in (report.results[0].failure_reasons)


async def test_evaluate_skips_rag_for_in_scope_question_without_source_backed_entity() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        knowledge_retriever=FailOnSearchRetriever(),
    )
    manifest = MedicationSearchBaselineManifest(
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name="medication_knowledge_full_v2",
        cases=[
            MedicationSearchBaselineCase(
                query_id="no-entity-no-rag",
                question="처음 보는 영양제의 주의사항을 알려줘",
                expected_scope="IN_SCOPE",
                expected_resolution_status="UNRESOLVED",
                expect_no_entity=True,
                expect_no_evidence=True,
                expect_no_rag=True,
            )
        ],
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.results[0].retrieval_executed is False
    assert report.results[0].passed is True


async def test_evaluate_preserves_gold_document_and_experiment_rationales() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        knowledge_retriever=FakeRetriever(),
    )
    manifest = MedicationSearchBaselineManifest.model_validate(
        {
            "schema_version": "medication-search-baseline-v2",
            "dataset_version": "knowledge-full-v2-interaction-metadata",
            "collection_name": "medication_knowledge_full_v2",
            "experiment_goal": "검색 방식별 골드 문서 순위를 비교합니다.",
            "activation_rule": "정확도가 개선되고 안전 지표가 악화되지 않을 때만 채택합니다.",
            "metric_rationales": {
                "recall_at_20": "후보 포함 여부",
                "hit_at_5": "상위 근거 포함 여부",
                "mrr": "첫 정답 순위",
                "source_accuracy": "출처 정확성",
                "evidence_coverage_rate": "근거 범위",
                "wrong_target_mixing_count": "다른 대상 혼입",
                "duplicate_retrieval_rate": "중복 근거",
                "search_p95_ms": "지연 감시",
            },
            "cases": [
                {
                    "query_id": "typo-brand",
                    "question": "타이래놀 효능 알려줘",
                    "expected_scope": "IN_SCOPE",
                    "expected_resolution_status": "AUTO_CORRECTED",
                    "expected_resolved_question": "타이레놀 효능 알려줘",
                    "expected_entity_names": ["타이레놀"],
                    "evidence_kind": "QDRANT_GOLD",
                    "evaluation_rationale": "오타 교정 후 정답 근거가 유지되는지 검증합니다.",
                    "expected_document_ids": ["acetaminophen-guide"],
                    "gold_document_rationales": {"acetaminophen-guide": "교정된 성분을 직접 설명하는 문서입니다."},
                }
            ],
        }
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.experiment_goal == "검색 방식별 골드 문서 순위를 비교합니다."
    assert report.metric_rationales["mrr"] == "첫 정답 순위"
    assert report.results[0].evaluation_rationale == ("오타 교정 후 정답 근거가 유지되는지 검증합니다.")
    assert report.results[0].expected_document_ids == ["acetaminophen-guide"]
    assert report.results[0].gold_document_rationales == {
        "acetaminophen-guide": "교정된 성분을 직접 설명하는 문서입니다."
    }


async def test_evaluate_excludes_deferred_case_from_active_phase_pass_rate() -> None:
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=StaticCatalog(),
        ),
        knowledge_retriever=FakeRetriever(),
    )
    manifest = MedicationSearchBaselineManifest.model_validate(
        {
            "schema_version": "medication-search-baseline-v3",
            "dataset_version": "knowledge-full-v5-o200k",
            "collection_name": "medication_knowledge_full_v5",
            "baseline_observed_at": "2026-09-08",
            "baseline_environment": "unit-test",
            "experiment_goal": "활성 단계와 후속 단계를 구분해 회귀를 측정합니다.",
            "activation_rule": "활성 단계만 다음 구현의 차단 기준으로 사용합니다.",
            "metric_rationales": {
                "recall_at_20": "후보 포함 여부",
                "hit_at_5": "최종 근거 포함 여부",
                "mrr": "첫 정답 순위",
                "source_accuracy": "출처 정확성",
                "evidence_coverage_rate": "근거 범위",
                "wrong_target_mixing_count": "다른 대상 혼입",
                "duplicate_retrieval_rate": "중복 근거",
                "search_p95_ms": "지연 감시",
            },
            "cases": [
                {
                    "query_id": "active-out-of-scope",
                    "question": "오늘 배고파요",
                    "phase": "ACTIVE_PHASE",
                    "historical_outcome": "PASS",
                    "expected_scope": "OUT_OF_SCOPE",
                    "expected_resolution_status": "UNRESOLVED",
                    "expect_no_entity": True,
                    "expect_no_guide_lookup": True,
                    "expect_no_rag": True,
                    "evidence_kind": "NOT_APPLICABLE",
                    "evaluation_rationale": "활성 범위 집계가 비도메인 질문도 정확히 반영하는지 확인합니다.",
                },
                {
                    "query_id": "deferred-memory",
                    "question": "그 약의 주의사항을 알려줘",
                    "phase": "DEFERRED_MEMORY",
                    "historical_outcome": "FAIL",
                    "expected_scope": "IN_SCOPE",
                    "expected_resolution_status": "UNCHANGED",
                    "evidence_kind": "NOT_APPLICABLE",
                    "evaluation_rationale": "세션 대명사 해소는 이번 단계의 범위 밖입니다.",
                },
            ],
        }
    )

    report = await evaluator.evaluate(
        manifest,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
    )

    assert report.active_query_count == 1
    assert report.active_pass_count == 1
    assert report.active_pass_rate == 1.0
    assert report.deferred_query_count == 1
    assert report.baseline_observed_at == "2026-09-08"
    assert report.baseline_environment == "unit-test"
    assert report.passed is True
