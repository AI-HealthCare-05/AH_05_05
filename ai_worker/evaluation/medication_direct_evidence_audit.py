"""QDRANT_GOLD 직접 근거가 검색 파이프라인에서 사라지는 지점을 판정한다."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from ai_worker.rag.vectorstores.qdrant_knowledge_store import QdrantKnowledgeSearchTrace
from ai_worker.schemas.knowledge import (
    KnowledgeRetrievalResult,
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationSearchExecutionPlan,
)
from ai_worker.schemas.medication_search_evaluation import (
    MedicationEvaluationEvidenceKind,
    MedicationSearchBaselineCase,
    MedicationSearchBaselineManifest,
)


class DirectEvidenceFailureStage(StrEnum):
    TARGET_ABSENT = "TARGET_ABSENT"
    DATASET_MISMATCH = "DATASET_MISMATCH"
    EXACT_PAIR_EMPTY = "EXACT_PAIR_EMPTY"
    REFINER_DROPPED = "REFINER_DROPPED"
    ELIGIBILITY_REJECTED = "ELIGIBILITY_REJECTED"
    RANKED_OUT = "RANKED_OUT"
    PARENT_CONTEXT_REPLACED = "PARENT_CONTEXT_REPLACED"
    TOP_5 = "TOP_5"


class DirectEvidenceTargetObservation(BaseModel):
    """한 gold 문서에 대한 검색 단계별 비식별 관측값."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(min_length=1)
    collection_name: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    expected_document_id: str = Field(min_length=1)
    target_payload_present: bool
    payload_dataset_versions: list[str] = Field(default_factory=list)
    payload_pair_key_matched: bool | None = None
    exact_pair_raw_rank: int | None = Field(default=None, ge=1)
    refined_rank: int | None = Field(default=None, ge=1)
    eligibility_reason: str | None = None
    adjusted_rank: int | None = Field(default=None, ge=1)
    selected_in_top_5: bool = False
    parent_context_replaced: bool = False


@dataclass(frozen=True)
class DirectEvidenceSearchTrace:
    """후보 tier 조회 하나에 대한 raw/refined 관측값."""

    search_query: KnowledgeSearchQuery
    trace: QdrantKnowledgeSearchTrace


class DirectEvidenceTraceableStore(Protocol):
    async def search_with_trace(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> QdrantKnowledgeSearchTrace: ...


class DirectEvidencePayloadStore(DirectEvidenceTraceableStore, Protocol):
    async def find_chunks_by_document_id(
        self,
        *,
        document_id: str,
    ) -> list[RetrievedKnowledgeChunk]: ...


class DirectEvidenceDiagnosticRetriever(Protocol):
    async def search_with_diagnostics(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
        audit_target_document_ids: set[str] | None = None,
    ) -> KnowledgeRetrievalResult: ...


class DirectEvidenceTracingStore:
    """Retriever 반환 계약을 바꾸지 않고 audit trace만 축적한다."""

    def __init__(self, *, store: DirectEvidenceTraceableStore) -> None:
        self._store = store
        self.search_traces: list[DirectEvidenceSearchTrace] = []

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]:
        trace = await self._store.search_with_trace(
            query_vector=query_vector,
            search_query=search_query,
        )
        self.search_traces.append(
            DirectEvidenceSearchTrace(
                search_query=search_query,
                trace=trace,
            )
        )
        return trace.refined_results


class DirectEvidenceAttribution(BaseModel):
    """수정할 계층을 하나로 제한하는 직접 근거 귀속 결과."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: DirectEvidenceTargetObservation
    first_failure_stage: DirectEvidenceFailureStage

    @classmethod
    def from_observation(
        cls,
        observation: DirectEvidenceTargetObservation,
    ) -> "DirectEvidenceAttribution":
        return cls(
            observation=observation,
            first_failure_stage=cls._first_failure_stage(observation),
        )

    @staticmethod
    def _first_failure_stage(
        observation: DirectEvidenceTargetObservation,
    ) -> DirectEvidenceFailureStage:
        if not observation.target_payload_present:
            return DirectEvidenceFailureStage.TARGET_ABSENT
        if observation.dataset_version not in observation.payload_dataset_versions:
            return DirectEvidenceFailureStage.DATASET_MISMATCH
        if observation.exact_pair_raw_rank is None:
            return DirectEvidenceFailureStage.EXACT_PAIR_EMPTY
        if observation.refined_rank is None:
            return DirectEvidenceFailureStage.REFINER_DROPPED
        if observation.eligibility_reason not in {None, "ELIGIBLE"}:
            return DirectEvidenceFailureStage.ELIGIBILITY_REJECTED
        if observation.selected_in_top_5:
            return DirectEvidenceFailureStage.TOP_5
        if observation.adjusted_rank is None or observation.adjusted_rank > 5:
            return DirectEvidenceFailureStage.RANKED_OUT
        if observation.parent_context_replaced:
            return DirectEvidenceFailureStage.PARENT_CONTEXT_REPLACED
        return DirectEvidenceFailureStage.PARENT_CONTEXT_REPLACED


class DirectEvidenceAuditReport(BaseModel):
    """불변 collection의 gold 근거가 사라진 최초 단계를 요약한다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    collection_name: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    target_count: int = Field(ge=0)
    stage_counts: dict[DirectEvidenceFailureStage, int] = Field(default_factory=dict)
    attributions: list[DirectEvidenceAttribution] = Field(default_factory=list)

    @classmethod
    def from_attributions(
        cls,
        *,
        collection_name: str,
        dataset_version: str,
        attributions: list[DirectEvidenceAttribution],
    ) -> "DirectEvidenceAuditReport":
        stage_counts: dict[DirectEvidenceFailureStage, int] = {}
        for attribution in attributions:
            stage = attribution.first_failure_stage
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        return cls(
            collection_name=collection_name,
            dataset_version=dataset_version,
            target_count=len(attributions),
            stage_counts=stage_counts,
            attributions=attributions,
        )


class DirectEvidenceTargetAttributionBuilder:
    """Audit 전용 관측값으로 QDRANT_GOLD 문서의 최초 탈락 단계를 만든다."""

    @classmethod
    def build(
        cls,
        *,
        query_id: str,
        collection_name: str,
        dataset_version: str,
        expected_document_id: str,
        expected_pair_keys: list[str],
        target_payloads: list[RetrievedKnowledgeChunk],
        search_traces: list[DirectEvidenceSearchTrace],
        retrieval: KnowledgeRetrievalResult,
    ) -> DirectEvidenceAttribution:
        pair_keys = set(expected_pair_keys)
        exact_pair_traces = [
            search_trace
            for search_trace in search_traces
            if not pair_keys or bool(pair_keys.intersection(search_trace.search_query.interaction_pair_keys))
        ]
        target_diagnostics = sorted(
            (
                diagnostic
                for diagnostic in (
                    retrieval.diagnostics.audit_target_diagnostics or retrieval.diagnostics.candidate_diagnostics
                )
                if diagnostic.document_id == expected_document_id
            ),
            key=lambda diagnostic: diagnostic.adjusted_rank,
        )
        selected_document_ids = {chunk.metadata.document_id for chunk in retrieval.chunks}
        selected_in_top_5 = expected_document_id in selected_document_ids or any(
            diagnostic.selected_in_top_5 for diagnostic in target_diagnostics
        )
        target_diagnostic = target_diagnostics[0] if target_diagnostics else None
        observation = DirectEvidenceTargetObservation(
            query_id=query_id,
            collection_name=collection_name,
            dataset_version=dataset_version,
            expected_document_id=expected_document_id,
            target_payload_present=bool(target_payloads),
            payload_dataset_versions=sorted({chunk.metadata.dataset_version for chunk in target_payloads}),
            payload_pair_key_matched=(
                None
                if not pair_keys
                else any(pair_keys.intersection(chunk.metadata.interaction_pair_keys) for chunk in target_payloads)
            ),
            exact_pair_raw_rank=cls._document_rank(
                search_traces=exact_pair_traces,
                expected_document_id=expected_document_id,
                refined=False,
            ),
            refined_rank=cls._document_rank(
                search_traces=exact_pair_traces,
                expected_document_id=expected_document_id,
                refined=True,
            ),
            eligibility_reason=(
                None
                if target_diagnostic is None or target_diagnostic.eligible
                else target_diagnostic.rejection_reason.value
                if target_diagnostic.rejection_reason is not None
                else "REJECTED"
            ),
            adjusted_rank=(target_diagnostic.adjusted_rank if target_diagnostic is not None else None),
            selected_in_top_5=selected_in_top_5,
            parent_context_replaced=(
                target_diagnostic is not None
                and target_diagnostic.adjusted_rank <= 5
                and not selected_in_top_5
                and retrieval.diagnostics.parent_context_attached_count > 0
            ),
        )
        return DirectEvidenceAttribution.from_observation(observation)

    @staticmethod
    def _document_rank(
        *,
        search_traces: list[DirectEvidenceSearchTrace],
        expected_document_id: str,
        refined: bool,
    ) -> int | None:
        ranks: list[int] = []
        for search_trace in search_traces:
            results = search_trace.trace.refined_results if refined else search_trace.trace.raw_results
            for rank, result in enumerate(results, start=1):
                if result.metadata.document_id == expected_document_id:
                    ranks.append(rank)
                    break
        return min(ranks, default=None)


class MedicationDirectEvidenceAuditor:
    """QDRANT_GOLD fixture를 운영 검색에 주입하지 않고 단계별로 추적한다."""

    def __init__(
        self,
        *,
        collection_name: str,
        dataset_version: str,
        vector_store: DirectEvidencePayloadStore,
        query_planner: Callable[[str], Awaitable[MedicationKnowledgeQueryPlan]],
        retriever_factory: Callable[[DirectEvidenceTracingStore], DirectEvidenceDiagnosticRetriever],
        limit: int = 5,
    ) -> None:
        self._collection_name = collection_name.strip()
        self._dataset_version = dataset_version.strip()
        if not self._collection_name or not self._dataset_version:
            raise ValueError("직접 근거 audit에는 collection과 dataset version이 필요합니다.")
        self._vector_store = vector_store
        self._query_planner = query_planner
        self._retriever_factory = retriever_factory
        self._limit = limit

    async def audit_case(
        self,
        case: MedicationSearchBaselineCase,
    ) -> list[DirectEvidenceAttribution]:
        if case.evidence_kind is not MedicationEvaluationEvidenceKind.QDRANT_GOLD:
            return []
        query_plan = await self._query_planner(case.question)
        tracing_store = DirectEvidenceTracingStore(store=self._vector_store)
        retrieval = await self._retriever_factory(tracing_store).search_with_diagnostics(
            execution_plan=MedicationSearchExecutionPlan(
                query_plan=query_plan,
                context_hash="0" * 64,
                approved_rules_hash="0" * 64,
                limit=self._limit,
            ),
            audit_target_document_ids=set(case.expected_document_ids),
        )
        expected_pair_keys = query_plan.interaction_pair_keys
        attributions: list[DirectEvidenceAttribution] = []
        for expected_document_id in case.expected_document_ids:
            target_payloads = await self._vector_store.find_chunks_by_document_id(
                document_id=expected_document_id,
            )
            attributions.append(
                DirectEvidenceTargetAttributionBuilder.build(
                    query_id=case.query_id,
                    collection_name=self._collection_name,
                    dataset_version=self._dataset_version,
                    expected_document_id=expected_document_id,
                    expected_pair_keys=expected_pair_keys,
                    target_payloads=target_payloads,
                    search_traces=tracing_store.search_traces,
                    retrieval=retrieval,
                )
            )
        return attributions

    async def audit_manifest(
        self,
        manifest: MedicationSearchBaselineManifest,
        *,
        query_ids: set[str] | None = None,
    ) -> DirectEvidenceAuditReport:
        """고정 평가 중 QDRANT_GOLD 문항만 대상으로 실패 단계를 집계한다."""

        cases = [
            case
            for case in manifest.cases
            if case.evidence_kind is MedicationEvaluationEvidenceKind.QDRANT_GOLD
            and (query_ids is None or case.query_id in query_ids)
        ]
        if query_ids is not None:
            missing_query_ids = query_ids.difference({case.query_id for case in cases})
            if missing_query_ids:
                raise ValueError(
                    "QDRANT_GOLD 평가 문항을 찾을 수 없습니다: " + ", ".join(sorted(missing_query_ids)),
                )
        attributions = [attribution for case in cases for attribution in await self.audit_case(case)]
        return DirectEvidenceAuditReport.from_attributions(
            collection_name=self._collection_name,
            dataset_version=self._dataset_version,
            attributions=attributions,
        )
