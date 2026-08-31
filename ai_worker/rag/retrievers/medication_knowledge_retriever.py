import asyncio
import re
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
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchQuery,
    KnowledgeSectionType,
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
    _BILINGUAL_DRUG_NAME = re.compile(
        r"^\s*([^()]*[가-힣][^()]*)\s*\(\s*([A-Za-z][A-Za-z0-9 .,+/-]*)\s*\)\s*$",
    )
    _LEGACY_SECTION_HEADING = re.compile(
        r"(?P<boundary>\A|(?:\r?\n){2,}|[.!?]\s+)"
        r"(?P<heading>효능[·․.]효과|용법(?:[·․.]용량)?|경고|금기|주의사항|부작용|이상반응)"
        r"(?=\S)",
    )
    _EXACT_ENTITY_BONUS = 0.12
    _CONTAINED_ENTITY_BONUS = 0.08
    _PAIR_ENTITY_BONUS = 0.12
    _SECTION_BONUS = 0.05
    _BOOST_ELIGIBILITY_MARGIN = 0.10
    _PAIR_BOOST_ELIGIBILITY_MARGIN = 0.15
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
        if (
            plan.interaction_pair is None
            and self._requires_entity_pair_match(plan)
            and not self._all_query_entities_match_text(result, plan=plan)
        ):
            return _EligibilityReason.PAIR_MISMATCH
        if result.similarity_score >= self._min_similarity_score:
            return _EligibilityReason.ELIGIBLE

        eligibility_margin = (
            self._PAIR_BOOST_ELIGIBILITY_MARGIN
            if self._requires_entity_pair_match(plan) and self._all_query_entities_match_text(result, plan=plan)
            else self._BOOST_ELIGIBILITY_MARGIN
        )
        minimum_raw_score = max(
            0.0,
            self._min_similarity_score - eligibility_margin,
        )
        if result.similarity_score < minimum_raw_score:
            return _EligibilityReason.BELOW_SCORE
        if plan.section_types and not set(plan.section_types).intersection(
            self._effective_section_types(result),
        ):
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
        section_bonus = (
            cls._SECTION_BONUS if set(plan.section_types).intersection(cls._effective_section_types(result)) else 0.0
        )
        return result.similarity_score + cls._entity_match_bonus(result, plan=plan) + section_bonus

    @classmethod
    def _effective_section_types(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> set[KnowledgeSectionType]:
        if result.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            return {result.metadata.section_type}

        section_types: set[KnowledgeSectionType] = set()
        for match in cls._LEGACY_SECTION_HEADING.finditer(result.content):
            boundary = match.group("boundary")
            if boundary and not boundary.startswith(("\n", "\r")):
                suffix = cls._normalize_name(result.content[match.end() :])
                if not any(suffix.startswith(alias) for alias in cls._metadata_entity_aliases(result)):
                    continue

            heading = match.group("heading")
            if heading.startswith("효능"):
                section_types.add(KnowledgeSectionType.FUNCTION)
            elif heading.startswith("용법"):
                section_types.add(KnowledgeSectionType.DAILY_INTAKE)
            elif heading in {"부작용", "이상반응"}:
                section_types.add(KnowledgeSectionType.ADVERSE_EVENT)
            else:
                section_types.add(KnowledgeSectionType.CAUTION)

        return section_types or {result.metadata.section_type}

    @classmethod
    def _entity_match_bonus(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        query_entities = cls._normalized_query_entities(plan)
        metadata_entities = cls._metadata_entity_aliases(result)
        if len(query_entities) >= 2 and cls._all_query_entities_match_text(result, plan=plan):
            return cls._PAIR_ENTITY_BONUS
        if query_entities.intersection(metadata_entities):
            return cls._EXACT_ENTITY_BONUS
        if any(
            query_entity in metadata_entity for query_entity in query_entities for metadata_entity in metadata_entities
        ):
            return cls._CONTAINED_ENTITY_BONUS
        return 0.0

    @classmethod
    def _metadata_entity_aliases(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> set[str]:
        aliases = {
            cls._normalize_name(name)
            for name in [
                *result.metadata.ingredient_names,
                *result.metadata.drug_names,
            ]
            if len(cls._normalize_name(name)) >= 2
        }
        if result.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            return aliases

        for name in result.metadata.drug_names:
            match = cls._BILINGUAL_DRUG_NAME.fullmatch(name)
            if match is None:
                continue
            aliases.update(
                cls._normalize_name(alias) for alias in match.groups() if len(cls._normalize_name(alias)) >= 2
            )
        return aliases

    @staticmethod
    def _requires_entity_pair_match(
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        return (
            len(MedicationKnowledgeRetriever._normalized_query_entities(plan)) == 2
            and KnowledgeSectionType.INTERACTION in plan.section_types
        )

    @classmethod
    def _all_query_entities_match_text(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        query_entities = cls._normalized_query_entities(plan)
        if not query_entities:
            return False
        searchable_text = cls._normalize_name(
            " ".join(
                [
                    result.metadata.title,
                    result.content,
                    *result.metadata.drug_names,
                    *result.metadata.ingredient_names,
                ]
            )
        )
        return all(entity in searchable_text for entity in query_entities)

    @classmethod
    def _normalized_query_entities(
        cls,
        plan: MedicationKnowledgeQueryPlan,
    ) -> set[str]:
        return {cls._normalize_name(name) for name in plan.entity_names if len(cls._normalize_name(name)) >= 2}

    @staticmethod
    def _normalize_name(value: str) -> str:
        return "".join(value.casefold().split())
