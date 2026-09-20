from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from langchain_core.runnables import RunnableLambda, RunnableParallel

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.domain.supplement_function_goal_detector import (
    is_supplement_function_goal_question,
)
from ai_worker.rag.embeddings.embedding_text_builder import (
    build_medical_retrieval_query_text,
)
from ai_worker.rag.errors import (
    GuidelineRetrievalError,
    RetrievalFailureStage,
)
from ai_worker.rag.ingredient_name_aliases import english_aliases_for
from ai_worker.schemas.knowledge import (
    KnowledgeSearchQuery,
    KnowledgeSearchTier,
    KnowledgeSectionType,
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


EligibilityEvaluator = Callable[[RetrievedKnowledgeChunk, MedicationSearchExecutionPlan], str]
SectionCoverageEvaluator = Callable[[list[RetrievedKnowledgeChunk], MedicationKnowledgeQueryPlan], bool]


class MedicationKnowledgeCandidateRetriever:
    """질의 임베딩과 단계별 Qdrant 후보 조회만 담당합니다."""

    _EXHAUSTIVE_PAGE_SIZE = 50

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

    @staticmethod
    def _english_alias_queries(plan: MedicationKnowledgeQueryPlan) -> list[str]:
        """영문으로만 색인된 상호작용 근거를 한국어 질의가 놓치지 않게 한다.

        INTERACTION 섹션 청크 294건 중 138건이 영문 이름만 가지고 있어 한국어
        질의로는 닿지 않는다. 별칭은 말뭉치에서 유도한 사전에서만 오며, 사전에
        없는 이름에는 아무것도 더하지 않는다.
        """
        if (
            KnowledgeSectionType.INTERACTION not in plan.section_types
            and not plan.interaction_pairs
            and plan.interaction_pair is None
        ):
            return []
        return [f"{alias} interaction" for name in plan.entity_names for alias in english_aliases_for(name)]

    async def retrieve(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> MedicationKnowledgeCandidateSearchResult:
        plan = execution_plan.query_plan
        candidate_limit = (
            self._EXHAUSTIVE_PAGE_SIZE
            if execution_plan.include_all_eligible
            else min(50, max(20, execution_plan.limit * 4))
        )
        queries = list(
            dict.fromkeys(
                [
                    plan.expanded_query,
                    *plan.alternate_queries,
                    *self._english_alias_queries(plan),
                    *(
                        [f"건강기능식품 기능성 원료 {plan.supplement_function_goal} 도움"]
                        if plan.supplement_function_goal
                        else []
                    ),
                ]
            )
        )
        if self._is_interaction_overview(execution_plan):
            subject = plan.entity_names[0]
            queries = list(
                dict.fromkeys(
                    [
                        *queries,
                        f"{subject} 영양제 비타민 미네랄 상호작용",
                        f"{subject} 음식 상호작용",
                        *(
                            f"{subject} {class_name} 영양제 음식 상호작용"
                            for class_name in execution_plan.approved_therapeutic_class_names
                        ),
                    ]
                )
            )
        embedding_queries = [
            self._embedding_query_text(
                query=query,
                plan=plan,
            )
            for query in queries
        ]
        try:
            query_vectors_by_key = await RunnableParallel(
                **{
                    f"query_{index}": self._embedding_runnable(query=query)
                    for index, query in enumerate(embedding_queries)
                },
            ).ainvoke({})
            query_vectors = [query_vectors_by_key[f"query_{index}"] for index in range(len(queries))]
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
                tier_batches_by_key = await RunnableParallel(
                    **{
                        f"query_{index}": self._search_runnable(
                            query=query,
                            query_vector=query_vector,
                            tier=tier,
                            candidate_limit=candidate_limit,
                            exhaustive=execution_plan.include_all_eligible,
                        )
                        for index, (query, query_vector) in enumerate(
                            zip(
                                queries,
                                query_vectors,
                                strict=True,
                            )
                        )
                    },
                ).ainvoke({})
                tier_batches = [tier_batches_by_key[f"query_{index}"] for index in range(len(queries))]
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
            tier_reasons = [self._eligibility_evaluator(result, execution_plan) for result in tier_results]
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
            has_requested_section_coverage = self._section_coverage_evaluator(eligible, plan)
            is_interaction_overview = execution_plan.query_plan.interaction_overview or self._is_interaction_overview(
                execution_plan
            )
            if tier.name == KnowledgeSearchTier.EXACT_PAIR and not is_interaction_overview:
                has_requested_section_coverage = (
                    has_requested_section_coverage and self._has_complete_exact_pair_coverage(eligible, plan=plan)
                )
            if tier_eligible and (
                tier.name == KnowledgeSearchTier.SEMANTIC
                or (not is_interaction_overview and has_requested_section_coverage)
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
    def _has_complete_exact_pair_coverage(
        results: list[RetrievedKnowledgeChunk],
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        """모든 질문 pair가 직접 pair-key 청크로 확보된 경우에만 exact tier에서 멈춘다."""

        required_pair_keys = set(plan.interaction_pair_keys)
        if not required_pair_keys:
            return False
        covered_pair_keys = {pair_key for result in results for pair_key in result.metadata.interaction_pair_keys}
        return required_pair_keys.issubset(covered_pair_keys)

    @staticmethod
    def _embedding_query_text(
        *,
        query: str,
        plan: MedicationKnowledgeQueryPlan,
    ) -> str:
        question = (
            query
            if plan.supplement_function_goal or is_supplement_function_goal_question(plan.original_query)
            else (plan.original_query if query == plan.expanded_query else query)
        )
        return build_medical_retrieval_query_text(
            question=question,
            entity_names=plan.entity_names,
            section_types=plan.section_types,
            pair_names=[f"{pair.left_name}-{pair.right_name}" for pair in plan.interaction_pairs],
        )

    @staticmethod
    def _is_interaction_overview(execution_plan: MedicationSearchExecutionPlan) -> bool:
        plan = execution_plan.query_plan
        return (
            len(plan.entity_names) == 1
            and KnowledgeSectionType.INTERACTION in plan.section_types
            and not plan.interaction_pair_keys
            and not execution_plan.include_patient_context
        )

    @staticmethod
    def search_tiers(
        execution_plan: MedicationSearchExecutionPlan,
    ) -> list[MedicationKnowledgeSearchTier]:
        tiers: list[MedicationKnowledgeSearchTier] = []
        if execution_plan.interaction_pair_keys and not (
            execution_plan.query_plan.interaction_overview
            or MedicationKnowledgeCandidateRetriever._is_interaction_overview(execution_plan)
        ):
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
        exhaustive: bool,
    ) -> list[RetrievedKnowledgeChunk]:
        results: list[RetrievedKnowledgeChunk] = []
        seen_chunk_ids: set[str] = set()
        offset = 0
        while True:
            batch = await self._vector_store.search(
                query_vector=query_vector,
                search_query=KnowledgeSearchQuery(
                    query=query,
                    dataset_version=self._dataset_version,
                    drug_names=list(tier.medication_names),
                    ingredient_names=list(tier.supplement_names),
                    interaction_pair_keys=list(tier.interaction_pair_keys),
                    limit=candidate_limit,
                    offset=offset,
                    exhaustive=exhaustive,
                ),
            )
            if not exhaustive:
                return batch
            if not batch:
                return results
            new_results = [result for result in batch if result.chunk_id not in seen_chunk_ids]
            if not new_results:
                raise RuntimeError(
                    "Knowledge store가 pagination offset을 적용하지 않아 exhaustive 검색을 중단했습니다."
                )
            results.extend(new_results)
            seen_chunk_ids.update(result.chunk_id for result in new_results)
            offset += self._EXHAUSTIVE_PAGE_SIZE

    def _embedding_runnable(
        self,
        *,
        query: str,
    ) -> RunnableLambda:
        async def embed_query(_input: object) -> list[float]:
            return await self._embedding_provider.embed_query(query)

        return RunnableLambda(
            embed_query,
            name="medication_knowledge_query_embedding",
        )

    def _search_runnable(
        self,
        *,
        query: str,
        query_vector: list[float],
        tier: MedicationKnowledgeSearchTier,
        candidate_limit: int,
        exhaustive: bool,
    ) -> RunnableLambda:
        async def search(_input: object) -> list[RetrievedKnowledgeChunk]:
            return await self._search_once(
                query=query,
                query_vector=query_vector,
                tier=tier,
                candidate_limit=candidate_limit,
                exhaustive=exhaustive,
            )

        return RunnableLambda(
            search,
            name="medication_knowledge_candidate_search",
        )
