import math
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from ai_worker.domain.medication_evidence_coverage import (
    MedicationEvidenceCoverageEvaluator,
)
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.knowledge import (
    KnowledgeRetrievalResult,
    KnowledgeSearchMode,
)
from ai_worker.schemas.medication_chat import MedicationGuideLookup
from ai_worker.schemas.medication_search import (
    MedicationExpressionResolutionStatus,
    MedicationQuestionScope,
    MedicationSearchExecutionPlan,
)
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineCase,
    MedicationSearchBaselineCaseResult,
    MedicationSearchBaselineManifest,
    MedicationSearchBaselineReport,
)


class DiagnosticKnowledgeRetriever(Protocol):
    async def search_with_diagnostics(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> KnowledgeRetrievalResult: ...


class MedicationSearchBaselineEvaluator:
    """현재 질문 해석과 Retriever를 변경 없이 연결해 기준선을 측정한다."""

    def __init__(
        self,
        *,
        question_resolver: RuleBasedMedicationQuestionResolver,
        query_builder: MedicationKnowledgeQueryBuilder,
        knowledge_retriever: DiagnosticKnowledgeRetriever,
        timer: Callable[[], float] = perf_counter,
        embedding_model_name: str | None = None,
        embedding_dimension: int | None = None,
        search_mode: KnowledgeSearchMode = KnowledgeSearchMode.DENSE,
    ) -> None:
        self._question_resolver = question_resolver
        self._query_builder = query_builder
        self._knowledge_retriever = knowledge_retriever
        self._timer = timer
        self._embedding_model_name = embedding_model_name
        self._embedding_dimension = embedding_dimension
        self._search_mode = search_mode
        self._evidence_coverage_evaluator = MedicationEvidenceCoverageEvaluator()

    async def evaluate(
        self,
        manifest: MedicationSearchBaselineManifest,
        *,
        git_commit: str,
        working_tree_dirty: bool,
        evaluation_file_sha256: str,
    ) -> MedicationSearchBaselineReport:
        results = [await self._evaluate_case(case, manifest=manifest) for case in manifest.cases]
        retrieval_results = [result for result in results if result.retrieval_executed]
        evidence_results = [
            result for case, result in zip(manifest.cases, results, strict=True) if case.expected_document_ids
        ]
        correction_results = [
            result
            for case, result in zip(manifest.cases, results, strict=True)
            if case.expected_resolution_status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
        ]
        non_correction_results = [
            result
            for case, result in zip(manifest.cases, results, strict=True)
            if case.expected_resolution_status != MedicationExpressionResolutionStatus.AUTO_CORRECTED
        ]
        ambiguity_results = [
            result
            for case, result in zip(manifest.cases, results, strict=True)
            if case.expected_resolution_status == MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED
        ]
        selected_total = sum(len(result.selected_document_ids) for result in evidence_results)
        relevant_selected = sum(
            sum(document_id in set(case.expected_document_ids) for document_id in result.selected_document_ids)
            for case, result in zip(manifest.cases, results, strict=True)
            if case.expected_document_ids
        )
        duplicate_total = sum(
            len(result.selected_chunk_ids) - len(set(result.selected_chunk_ids)) for result in retrieval_results
        )
        retrieval_selected_total = sum(len(result.selected_chunk_ids) for result in retrieval_results)
        latencies = sorted(result.search_latency_ms for result in retrieval_results)

        return MedicationSearchBaselineReport(
            experiment_goal=manifest.experiment_goal,
            activation_rule=manifest.activation_rule,
            metric_rationales=manifest.metric_rationales,
            dataset_version=manifest.dataset_version,
            collection_name=manifest.collection_name,
            search_mode=self._search_mode,
            embedding_model_name=self._embedding_model_name,
            embedding_dimension=self._embedding_dimension,
            min_similarity_score=manifest.min_similarity_score,
            final_top_k=manifest.final_top_k,
            candidate_top_k=manifest.candidate_top_k,
            git_commit=git_commit,
            working_tree_dirty=working_tree_dirty,
            evaluation_file_sha256=evaluation_file_sha256,
            query_count=len(results),
            resolution_accuracy=self._ratio(
                sum(
                    result.observed_resolution_status == case.expected_resolution_status
                    for case, result in zip(manifest.cases, results, strict=True)
                ),
                len(results),
            ),
            scope_accuracy=self._ratio(
                sum(
                    result.observed_scope == case.expected_scope
                    for case, result in zip(manifest.cases, results, strict=True)
                ),
                len(results),
            ),
            correction_accuracy=self._status_accuracy(
                correction_results,
                MedicationExpressionResolutionStatus.AUTO_CORRECTED,
            ),
            false_correction_rate=self._ratio(
                sum(
                    result.observed_resolution_status == MedicationExpressionResolutionStatus.AUTO_CORRECTED
                    for result in non_correction_results
                ),
                len(non_correction_results),
            ),
            ambiguity_accuracy=self._status_accuracy(
                ambiguity_results,
                MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED,
            ),
            recall_at_20=self._optional_bool_rate(evidence_results, "recall_at_20"),
            hit_at_5=self._optional_bool_rate(evidence_results, "hit_at_5"),
            mrr=self._average(
                [result.reciprocal_rank or 0.0 for result in evidence_results],
            ),
            source_accuracy=self._ratio(relevant_selected, selected_total),
            evidence_coverage_rate=self._average(
                [
                    result.evidence_coverage_rate
                    for result in evidence_results
                    if result.evidence_coverage_rate is not None
                ],
            ),
            wrong_target_mixing_count=sum("FORBIDDEN_DOCUMENT_MIXED" in result.failure_reasons for result in results),
            duplicate_retrieval_rate=self._ratio(
                duplicate_total,
                retrieval_selected_total,
            ),
            fallback_rate=self._ratio(
                sum(result.fallback_used for result in retrieval_results),
                len(retrieval_results),
            ),
            search_p50_ms=self._percentile(latencies, 0.50),
            search_p95_ms=self._percentile(latencies, 0.95),
            passed=all(result.passed for result in results),
            results=results,
        )

    async def _evaluate_case(
        self,
        case: MedicationSearchBaselineCase,
        *,
        manifest: MedicationSearchBaselineManifest,
    ) -> MedicationSearchBaselineCaseResult:
        resolution = await self._question_resolver.resolve(question=case.question)
        retrieval: KnowledgeRetrievalResult | None = None
        query_plan = None
        latency_ms = 0.0
        if (
            resolution.scope == MedicationQuestionScope.IN_SCOPE
            and resolution.status != MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED
        ):
            query_plan = self._query_builder.build(resolution.resolved_question)
            started_at = self._timer()
            retrieval = await self._knowledge_retriever.search_with_diagnostics(
                execution_plan=MedicationSearchExecutionPlan(
                    query_plan=query_plan,
                    context_hash="0" * 64,
                    approved_rules_hash="0" * 64,
                    limit=manifest.final_top_k,
                )
            )
            latency_ms = round(max((self._timer() - started_at) * 1000.0, 0.0), 3)

        candidate_diagnostics = retrieval.diagnostics.candidate_diagnostics if retrieval is not None else []
        selected_diagnostics = [diagnostic for diagnostic in candidate_diagnostics if diagnostic.selected_in_top_5]
        selected_chunks = retrieval.chunks if retrieval is not None else []
        selected_document_ids = (
            [chunk.metadata.document_id for chunk in selected_chunks]
            if selected_chunks
            else [diagnostic.document_id for diagnostic in selected_diagnostics]
        )
        selected_chunk_ids = (
            [chunk.chunk_id for chunk in selected_chunks]
            if selected_chunks
            else [diagnostic.chunk_id for diagnostic in selected_diagnostics]
        )
        expected_documents = set(case.expected_document_ids)
        relevant_candidates = [
            diagnostic
            for diagnostic in candidate_diagnostics[: manifest.candidate_top_k]
            if diagnostic.document_id in expected_documents
            and (not case.expected_section_types or diagnostic.section_matched)
        ]
        relevant_selected_positions = [
            rank for rank, document_id in enumerate(selected_document_ids, start=1) if document_id in expected_documents
        ]
        first_selected_rank = relevant_selected_positions[0] if relevant_selected_positions else None
        failure_reasons: list[str] = []
        if resolution.scope != case.expected_scope:
            failure_reasons.append("SCOPE_MISMATCH")
        if resolution.status != case.expected_resolution_status:
            failure_reasons.append("RESOLUTION_STATUS_MISMATCH")
        if (
            case.expected_resolved_question is not None
            and resolution.resolved_question != case.expected_resolved_question
        ):
            failure_reasons.append("RESOLVED_QUESTION_MISMATCH")
        observed_entities = query_plan.entity_names if query_plan is not None else []
        if not set(case.expected_entity_names).issubset(observed_entities):
            failure_reasons.append("ENTITY_MISMATCH")
        observed_sections = query_plan.section_types if query_plan is not None else []
        if not set(case.expected_section_types).issubset(observed_sections):
            failure_reasons.append("SECTION_MISMATCH")
        if case.expected_document_ids and not relevant_candidates:
            failure_reasons.append("EXPECTED_DOCUMENT_NOT_IN_TOP_20")
        if case.expected_document_ids and not relevant_selected_positions:
            failure_reasons.append("EXPECTED_DOCUMENT_NOT_IN_TOP_5")
        if set(case.forbidden_document_ids).intersection(selected_document_ids):
            failure_reasons.append("FORBIDDEN_DOCUMENT_MIXED")
        failure_reasons.extend(
            self._evidence_expectation_failures(
                case=case,
                selected_document_ids=selected_document_ids,
            )
        )
        evidence_coverage_rate = self._evidence_coverage_rate(
            case=case,
            query_plan=query_plan,
            selected_chunks=selected_chunks,
        )

        return MedicationSearchBaselineCaseResult(
            query_id=case.query_id,
            expression_category=case.expression_category,
            evidence_kind=case.evidence_kind,
            evaluation_rationale=case.evaluation_rationale,
            expected_document_ids=case.expected_document_ids,
            gold_document_rationales=case.gold_document_rationales,
            observed_scope=resolution.scope,
            observed_resolution_status=resolution.status,
            observed_resolved_question=resolution.resolved_question,
            observed_entity_names=observed_entities,
            observed_section_types=observed_sections,
            retrieval_executed=retrieval is not None,
            attempted_search_tiers=(
                [tier.value for tier in retrieval.diagnostics.attempted_search_tiers] if retrieval is not None else []
            ),
            candidate_count=len(candidate_diagnostics),
            candidate_first_relevant_rank=(
                min(diagnostic.adjusted_rank for diagnostic in relevant_candidates) if relevant_candidates else None
            ),
            selected_document_ids=selected_document_ids,
            selected_chunk_ids=selected_chunk_ids,
            hit_at_5=(bool(relevant_selected_positions) if expected_documents else None),
            recall_at_20=(bool(relevant_candidates) if expected_documents else None),
            reciprocal_rank=(
                1.0 / first_selected_rank
                if expected_documents and first_selected_rank is not None
                else (0.0 if expected_documents else None)
            ),
            evidence_coverage_rate=evidence_coverage_rate,
            fallback_used=(retrieval.diagnostics.fallback_used if retrieval is not None else False),
            search_latency_ms=latency_ms,
            failure_reasons=failure_reasons,
            passed=not failure_reasons,
        )

    def _evidence_coverage_rate(
        self,
        *,
        case: MedicationSearchBaselineCase,
        query_plan,
        selected_chunks,
    ) -> float | None:
        if query_plan is None or not case.expected_document_ids or not case.expected_section_types:
            return None
        coverage = self._evidence_coverage_evaluator.evaluate(
            query_plan=query_plan,
            guide_lookup=MedicationGuideLookup(),
            rules=[],
            chunks=selected_chunks,
        )
        expected = set(case.expected_section_types)
        covered = expected.intersection(coverage.covered_section_types)
        return round(len(covered) / len(expected), 6)

    @staticmethod
    def _evidence_expectation_failures(
        *,
        case: MedicationSearchBaselineCase,
        selected_document_ids: list[str],
    ) -> list[str]:
        if case.expect_no_evidence and selected_document_ids:
            return ["UNEXPECTED_EVIDENCE_RETRIEVED"]
        return []

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 6) if denominator else 0.0

    @classmethod
    def _status_accuracy(
        cls,
        results: list[MedicationSearchBaselineCaseResult],
        status: MedicationExpressionResolutionStatus,
    ) -> float:
        return cls._ratio(
            sum(result.observed_resolution_status == status for result in results),
            len(results),
        )

    @classmethod
    def _optional_bool_rate(
        cls,
        results: list[MedicationSearchBaselineCaseResult],
        field_name: str,
    ) -> float:
        return cls._ratio(
            sum(bool(getattr(result, field_name)) for result in results),
            len(results),
        )

    @staticmethod
    def _average(values: list[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        rank = max(math.ceil(percentile * len(values)) - 1, 0)
        return round(values[rank], 3)
