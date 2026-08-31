import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.metadata.supplement_interaction_registry import (
    supplement_pair_matches_text,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
    MedicationKnowledgeQueryPlan,
)
from ai_worker.schemas.knowledge import (
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)


@dataclass(frozen=True)
class _SearchBatch:
    results: list[RetrievedKnowledgeChunk]
    entity_filtered_count: int
    broad_candidate_count: int
    fallback_used: bool


class _EligibilityReason(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BELOW_SCORE = "BELOW_SCORE"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    PAIR_MISMATCH = "PAIR_MISMATCH"


class MedicationKnowledgeSearchStore(Protocol):
    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]: ...


class MedicationKnowledgeRetriever:
    _EXACT_ENTITY_BONUS = 0.12
    _CONTAINED_ENTITY_BONUS = 0.08
    _SECTION_BONUS = 0.05
    _BOOST_ELIGIBILITY_MARGIN = 0.10
    _MAX_CHUNKS_PER_DOCUMENT = 2

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: MedicationKnowledgeSearchStore,
        dataset_version: str,
        min_similarity_score: float = 0.65,
    ) -> None:
        normalized_version = dataset_version.strip()
        if not normalized_version:
            raise ValueError("Knowledge dataset_version은 비어 있을 수 없습니다.")
        if not 0.0 <= min_similarity_score <= 1.0:
            raise ValueError("최소 유사도 점수는 0 이상 1 이하여야 합니다.")
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._dataset_version = normalized_version
        self._min_similarity_score = min_similarity_score
        self._query_builder = MedicationKnowledgeQueryBuilder()

    async def search(
        self,
        *,
        question: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        result = await self.search_with_diagnostics(
            question=question,
            medication_names=medication_names,
            supplement_names=supplement_names,
            interaction_pair_keys=interaction_pair_keys,
            limit=limit,
        )
        return result.chunks

    async def search_with_diagnostics(
        self,
        *,
        question: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        limit: int,
    ) -> KnowledgeRetrievalResult:
        plan = self._query_builder.build(question)
        candidate_limit = min(50, max(20, limit * 4))
        batches = await asyncio.gather(
            *(
                self._search_once(
                    query=query,
                    medication_names=medication_names,
                    supplement_names=supplement_names,
                    interaction_pair_keys=interaction_pair_keys,
                    candidate_limit=candidate_limit,
                )
                for query in [plan.expanded_query, *plan.alternate_queries]
            )
        )
        results = [result for batch in batches for result in batch.results]
        eligibility_reasons = [self._eligibility_reason(result, plan=plan) for result in results]
        eligible = [
            result
            for result, reason in zip(results, eligibility_reasons, strict=True)
            if reason == _EligibilityReason.ELIGIBLE
        ]
        unique = self._deduplicate(eligible)
        ranked = sorted(
            unique,
            key=lambda result: self._ranking_score(
                result,
                plan=plan,
            ),
            reverse=True,
        )
        selected = self._select_diverse(ranked, limit=limit)
        diagnostics = KnowledgeRetrievalDiagnostics(
            raw_candidate_count=len(results),
            entity_filtered_count=sum(batch.entity_filtered_count for batch in batches),
            broad_candidate_count=sum(batch.broad_candidate_count for batch in batches),
            fallback_used=any(batch.fallback_used for batch in batches),
            eligible_candidate_count=len(eligible),
            rejected_below_score_count=eligibility_reasons.count(_EligibilityReason.BELOW_SCORE),
            rejected_entity_mismatch_count=eligibility_reasons.count(_EligibilityReason.ENTITY_MISMATCH),
            rejected_pair_mismatch_count=eligibility_reasons.count(_EligibilityReason.PAIR_MISMATCH),
            accepted_count=len(selected),
            max_raw_score=max(
                (result.similarity_score for result in results),
                default=None,
            ),
            max_score=max(
                (result.similarity_score for result in selected),
                default=None,
            ),
        )
        return KnowledgeRetrievalResult(
            chunks=selected,
            diagnostics=diagnostics,
        )

    @classmethod
    def _select_diverse(
        cls,
        results: list[RetrievedKnowledgeChunk],
        *,
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        selected: list[RetrievedKnowledgeChunk] = []
        document_counts: dict[str, int] = {}
        for result in results:
            document_id = result.metadata.document_id
            count = document_counts.get(document_id, 0)
            if count >= cls._MAX_CHUNKS_PER_DOCUMENT:
                continue
            selected.append(result)
            document_counts[document_id] = count + 1
            if len(selected) >= limit:
                break
        return selected

    async def _search_once(
        self,
        *,
        query: str,
        medication_names: list[str],
        supplement_names: list[str],
        interaction_pair_keys: list[str],
        candidate_limit: int,
    ) -> _SearchBatch:
        query_vector = await self._embedding_provider.embed_query(query)
        filtered_query = KnowledgeSearchQuery(
            query=query,
            dataset_version=self._dataset_version,
            drug_names=medication_names,
            ingredient_names=supplement_names,
            interaction_pair_keys=interaction_pair_keys,
            limit=candidate_limit,
        )
        results = await self._vector_store.search(
            query_vector=query_vector,
            search_query=filtered_query,
        )
        has_entity_filter = bool(medication_names or supplement_names or interaction_pair_keys)
        if not has_entity_filter:
            return _SearchBatch(
                results=results,
                entity_filtered_count=0,
                broad_candidate_count=len(results),
                fallback_used=False,
            )
        if results:
            return _SearchBatch(
                results=results,
                entity_filtered_count=len(results),
                broad_candidate_count=0,
                fallback_used=False,
            )
        fallback_query = KnowledgeSearchQuery(
            query=query,
            dataset_version=self._dataset_version,
            limit=candidate_limit,
        )
        fallback_results = await self._vector_store.search(
            query_vector=query_vector,
            search_query=fallback_query,
        )
        return _SearchBatch(
            results=fallback_results,
            entity_filtered_count=0,
            broad_candidate_count=len(fallback_results),
            fallback_used=True,
        )

    @staticmethod
    def _deduplicate(
        results: list[RetrievedKnowledgeChunk],
    ) -> list[RetrievedKnowledgeChunk]:
        unique: list[RetrievedKnowledgeChunk] = []
        seen_hashes: set[str] = set()
        for result in results:
            content_hash = result.metadata.content_hash
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            unique.append(result)
        return unique

    @staticmethod
    def _ranking_score(
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> tuple[float, float, str]:
        return (
            MedicationKnowledgeRetriever._relevance_score(
                result,
                plan=plan,
            ),
            result.similarity_score,
            result.chunk_id,
        )

    def _eligibility_reason(
        self,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> _EligibilityReason:
        if plan.interaction_pair is not None and not supplement_pair_matches_text(
            plan.interaction_pair,
            result.metadata.title,
            result.content,
            *result.metadata.ingredient_names,
        ):
            return _EligibilityReason.PAIR_MISMATCH
        if result.similarity_score >= self._min_similarity_score:
            return _EligibilityReason.ELIGIBLE

        minimum_raw_score = max(
            0.0,
            self._min_similarity_score - self._BOOST_ELIGIBILITY_MARGIN,
        )
        if result.similarity_score < minimum_raw_score:
            return _EligibilityReason.BELOW_SCORE
        if self._entity_match_bonus(result, plan=plan) <= 0.0:
            return _EligibilityReason.ENTITY_MISMATCH
        if self._relevance_score(result, plan=plan) < self._min_similarity_score:
            return _EligibilityReason.BELOW_SCORE
        return _EligibilityReason.ELIGIBLE

    @classmethod
    def _relevance_score(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        section_bonus = cls._SECTION_BONUS if result.metadata.section_type in plan.section_types else 0.0
        return result.similarity_score + cls._entity_match_bonus(result, plan=plan) + section_bonus

    @classmethod
    def _entity_match_bonus(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        query_entities = {
            cls._normalize_name(name) for name in plan.entity_names if len(cls._normalize_name(name)) >= 2
        }
        metadata_entities = {
            cls._normalize_name(name)
            for name in [
                *result.metadata.ingredient_names,
                *result.metadata.drug_names,
            ]
            if len(cls._normalize_name(name)) >= 2
        }
        if query_entities.intersection(metadata_entities):
            return cls._EXACT_ENTITY_BONUS
        if any(
            query_entity in metadata_entity for query_entity in query_entities for metadata_entity in metadata_entities
        ):
            return cls._CONTAINED_ENTITY_BONUS
        return 0.0

    @staticmethod
    def _normalize_name(value: str) -> str:
        return "".join(value.casefold().split())
