import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
from ai_worker.schemas.knowledge import (
    KnowledgeSearchQuery,
    KnowledgeSearchTier,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationSearchExecutionPlan,
)


@dataclass(frozen=True)
class MedicationKnowledgeSearchTier:
    name: KnowledgeSearchTier
    medication_names: tuple[str, ...] = ()
    supplement_names: tuple[str, ...] = ()
    interaction_pair_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class MedicationKnowledgeCandidateObservation:
    result: RetrievedKnowledgeChunk
    search_tier: KnowledgeSearchTier
    raw_rank: int


@dataclass(frozen=True)
class MedicationKnowledgeCandidateSearchResult:
    results: list[RetrievedKnowledgeChunk]
    eligible: list[RetrievedKnowledgeChunk]
    observations: list[MedicationKnowledgeCandidateObservation]
    eligibility_reasons: list[str]
    attempted_search_tiers: list[KnowledgeSearchTier]
    selected_search_tier: KnowledgeSearchTier | None
    entity_filtered_count: int
    broad_candidate_count: int


class MedicationKnowledgeSearchStore(Protocol):
    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]: ...


EligibilityEvaluator = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], str]
SectionCoverageEvaluator = Callable[[list[RetrievedKnowledgeChunk], MedicationKnowledgeQueryPlan], bool]


class MedicationKnowledgeCandidateRetriever:
    """질의 임베딩과 단계별 Qdrant 후보 조회만 담당합니다."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: MedicationKnowledgeSearchStore,
        dataset_version: str,
        eligibility_evaluator: EligibilityEvaluator,
        section_coverage_evaluator: SectionCoverageEvaluator,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._dataset_version = dataset_version
        self._eligibility_evaluator = eligibility_evaluator
        self._section_coverage_evaluator = section_coverage_evaluator

    async def retrieve(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> MedicationKnowledgeCandidateSearchResult:
        plan = execution_plan.query_plan
        candidate_limit = min(50, max(20, execution_plan.limit * 4))
        queries = list(dict.fromkeys([plan.expanded_query, *plan.alternate_queries]))
        try:
            query_vectors = await asyncio.gather(
                *(self._embedding_provider.embed_query(query) for query in queries),
            )
        except Exception as error:
            raise GuidelineRetrievalError(
                stage=RetrievalFailureStage.EMBEDDING,
                message="약·영양제 검색을 위한 질문 임베딩 생성에 실패했습니다.",
            ) from error

        results: list[RetrievedKnowledgeChunk] = []
        observations: list[MedicationKnowledgeCandidateObservation] = []
        eligibility_reasons: list[str] = []
        eligible: list[RetrievedKnowledgeChunk] = []
        attempted_search_tiers: list[KnowledgeSearchTier] = []
        selected_search_tier: KnowledgeSearchTier | None = None
        entity_filtered_count = 0
        broad_candidate_count = 0

        for tier in self.search_tiers(execution_plan):
            attempted_search_tiers.append(tier.name)
            try:
                tier_batches = await asyncio.gather(
                    *(
                        self._search_once(
                            query=query,
                            query_vector=query_vector,
                            tier=tier,
                            candidate_limit=candidate_limit,
                        )
                        for query, query_vector in zip(
                            queries,
                            query_vectors,
                            strict=True,
                        )
                    )
                )
            except Exception as error:
                raise GuidelineRetrievalError(
                    stage=RetrievalFailureStage.VECTOR_STORE,
                    message="약·영양제 Knowledge 벡터 검색에 실패했습니다.",
                ) from error
            tier_results = [result for batch in tier_batches for result in batch]
            observations.extend(
                MedicationKnowledgeCandidateObservation(
                    result=result,
                    search_tier=tier.name,
                    raw_rank=raw_rank,
                )
                for batch in tier_batches
                for raw_rank, result in enumerate(batch, start=1)
            )
            tier_reasons = [self._eligibility_evaluator(result, plan) for result in tier_results]
            tier_eligible = [
                result for result, reason in zip(tier_results, tier_reasons, strict=True) if reason == "ELIGIBLE"
            ]
            results.extend(tier_results)
            eligibility_reasons.extend(tier_reasons)
            eligible.extend(tier_eligible)
            if tier.name == KnowledgeSearchTier.SEMANTIC:
                broad_candidate_count += len(tier_results)
            else:
                entity_filtered_count += len(tier_results)
            if tier_eligible:
                selected_search_tier = tier.name
            if tier_eligible and (
                tier.name == KnowledgeSearchTier.SEMANTIC or self._section_coverage_evaluator(eligible, plan)
            ):
                break

        return MedicationKnowledgeCandidateSearchResult(
            results=results,
            eligible=eligible,
            observations=observations,
            eligibility_reasons=eligibility_reasons,
            attempted_search_tiers=attempted_search_tiers,
            selected_search_tier=selected_search_tier,
            entity_filtered_count=entity_filtered_count,
            broad_candidate_count=broad_candidate_count,
        )

    @staticmethod
    def search_tiers(
        execution_plan: MedicationSearchExecutionPlan,
    ) -> list[MedicationKnowledgeSearchTier]:
        tiers: list[MedicationKnowledgeSearchTier] = []
        if execution_plan.interaction_pair_keys:
            tiers.append(
                MedicationKnowledgeSearchTier(
                    name=KnowledgeSearchTier.EXACT_PAIR,
                    interaction_pair_keys=tuple(execution_plan.interaction_pair_keys),
                )
            )
        if execution_plan.medication_names or execution_plan.supplement_names:
            tiers.append(
                MedicationKnowledgeSearchTier(
                    name=KnowledgeSearchTier.ENTITY,
                    medication_names=tuple(execution_plan.medication_names),
                    supplement_names=tuple(execution_plan.supplement_names),
                )
            )
        tiers.append(MedicationKnowledgeSearchTier(name=KnowledgeSearchTier.SEMANTIC))
        return tiers

    async def _search_once(
        self,
        *,
        query: str,
        query_vector: list[float],
        tier: MedicationKnowledgeSearchTier,
        candidate_limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        return await self._vector_store.search(
            query_vector=query_vector,
            search_query=KnowledgeSearchQuery(
                query=query,
                dataset_version=self._dataset_version,
                drug_names=list(tier.medication_names),
                ingredient_names=list(tier.supplement_names),
                interaction_pair_keys=list(tier.interaction_pair_keys),
                limit=candidate_limit,
            ),
        )
