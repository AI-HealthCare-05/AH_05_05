import asyncio
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.metadata.supplement_interaction_registry import (
    supplement_pair_matches_text,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeRetrievalDiagnostics,
    KnowledgeRetrievalResult,
    KnowledgeSearchQuery,
    KnowledgeSearchTier,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntityType,
    MedicationSearchExecutionPlan,
)


@dataclass(frozen=True)
class _SearchTier:
    name: KnowledgeSearchTier
    medication_names: tuple[str, ...] = ()
    supplement_names: tuple[str, ...] = ()
    interaction_pair_keys: tuple[str, ...] = ()


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
    _PAIR_SAME_SENTENCE_BONUS = 0.04
    _SECTION_BONUS = 0.05
    _DOCUMENT_TYPE_BONUS = 0.03
    _INTERACTION_TYPE_BONUS = 0.03
    _EXACT_TOPIC_TITLE_BONUS = 0.15
    _BOOST_ELIGIBILITY_MARGIN = 0.10
    _PAIR_BOOST_ELIGIBILITY_MARGIN = 0.15
    _VERIFIED_RELATION_ELIGIBILITY_MARGIN = 0.20
    _MAX_CHUNKS_PER_DOCUMENT = 2
    _GENERIC_FOOD_ALIASES = {
        "음식": ("음식", "식사", "공복", "물", "음료", "주스"),
    }

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

    async def search(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> list[RetrievedKnowledgeChunk]:
        result = await self.search_with_diagnostics(
            execution_plan=execution_plan,
        )
        return result.chunks

    async def search_with_diagnostics(
        self,
        *,
        execution_plan: MedicationSearchExecutionPlan,
    ) -> KnowledgeRetrievalResult:
        plan = execution_plan.query_plan
        limit = execution_plan.limit
        candidate_limit = min(50, max(20, limit * 4))
        queries = list(
            dict.fromkeys(
                [plan.expanded_query, *plan.alternate_queries],
            )
        )
        query_vectors = await asyncio.gather(
            *(self._embedding_provider.embed_query(query) for query in queries),
        )
        results: list[RetrievedKnowledgeChunk] = []
        eligibility_reasons: list[_EligibilityReason] = []
        eligible: list[RetrievedKnowledgeChunk] = []
        attempted_search_tiers: list[KnowledgeSearchTier] = []
        selected_search_tier: KnowledgeSearchTier | None = None
        entity_filtered_count = 0
        broad_candidate_count = 0

        for tier in self._search_tiers(execution_plan):
            attempted_search_tiers.append(tier.name)
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
            tier_results = [result for batch in tier_batches for result in batch]
            tier_reasons = [self._eligibility_reason(result, plan=plan) for result in tier_results]
            tier_eligible = [
                result
                for result, reason in zip(
                    tier_results,
                    tier_reasons,
                    strict=True,
                )
                if reason == _EligibilityReason.ELIGIBLE
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
                tier.name == KnowledgeSearchTier.SEMANTIC
                or self._has_requested_section_coverage(
                    eligible,
                    plan=plan,
                )
            ):
                break

        unique = self._deduplicate(eligible)
        ranked = sorted(
            unique,
            key=lambda result: self._ranking_score(
                result,
                plan=plan,
            ),
            reverse=True,
        )
        selected = self._select_diverse(
            ranked,
            plan=plan,
            limit=limit,
        )
        diagnostics = KnowledgeRetrievalDiagnostics(
            raw_candidate_count=len(results),
            entity_filtered_count=entity_filtered_count,
            broad_candidate_count=broad_candidate_count,
            fallback_used=len(attempted_search_tiers) > 1,
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
            attempted_search_tiers=attempted_search_tiers,
            selected_search_tier=selected_search_tier,
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
        plan: MedicationKnowledgeQueryPlan,
        limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        selected: list[RetrievedKnowledgeChunk] = []
        selected_chunk_ids: set[str] = set()
        document_counts: dict[str, int] = {}

        def add(result: RetrievedKnowledgeChunk) -> bool:
            if result.chunk_id in selected_chunk_ids:
                return False
            document_id = result.metadata.document_id
            count = document_counts.get(document_id, 0)
            if count >= cls._MAX_CHUNKS_PER_DOCUMENT:
                return False
            selected.append(result)
            selected_chunk_ids.add(result.chunk_id)
            document_counts[document_id] = count + 1
            return True

        for section_type in plan.section_types:
            for explicit_only in (True, False):
                section_result = next(
                    (
                        result
                        for result in results
                        if result.chunk_id not in selected_chunk_ids
                        and section_type
                        in (
                            cls._explicit_legacy_section_types(result)
                            if explicit_only
                            else cls._effective_section_types(result)
                        )
                    ),
                    None,
                )
                if section_result is not None and add(section_result):
                    break
            if len(selected) >= limit:
                return selected

        for result in results:
            add(result)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _search_tiers(
        execution_plan: MedicationSearchExecutionPlan,
    ) -> list[_SearchTier]:
        tiers: list[_SearchTier] = []
        if execution_plan.interaction_pair_keys:
            tiers.append(
                _SearchTier(
                    name=KnowledgeSearchTier.EXACT_PAIR,
                    interaction_pair_keys=tuple(
                        execution_plan.interaction_pair_keys,
                    ),
                )
            )
        if execution_plan.medication_names or execution_plan.supplement_names:
            tiers.append(
                _SearchTier(
                    name=KnowledgeSearchTier.ENTITY,
                    medication_names=tuple(
                        execution_plan.medication_names,
                    ),
                    supplement_names=tuple(
                        execution_plan.supplement_names,
                    ),
                )
            )
        tiers.append(
            _SearchTier(name=KnowledgeSearchTier.SEMANTIC),
        )
        return tiers

    async def _search_once(
        self,
        *,
        query: str,
        query_vector: list[float],
        tier: _SearchTier,
        candidate_limit: int,
    ) -> list[RetrievedKnowledgeChunk]:
        search_query = KnowledgeSearchQuery(
            query=query,
            dataset_version=self._dataset_version,
            drug_names=list(tier.medication_names),
            ingredient_names=list(tier.supplement_names),
            interaction_pair_keys=list(tier.interaction_pair_keys),
            limit=candidate_limit,
        )
        return await self._vector_store.search(
            query_vector=query_vector,
            search_query=search_query,
        )

    @classmethod
    def _has_requested_section_coverage(
        cls,
        results: list[RetrievedKnowledgeChunk],
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        requested = set(plan.section_types)
        if not requested:
            return bool(results)
        covered = {section_type for result in results for section_type in cls._effective_section_types(result)}
        return requested.issubset(covered)

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
            )
            + MedicationKnowledgeRetriever._metadata_preference_score(
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
            and not self._matches_any_interaction_pair(result, plan=plan)
        ):
            return _EligibilityReason.PAIR_MISMATCH
        if (
            self._normalized_query_entities(plan)
            and not self._requires_entity_pair_match(plan)
            and plan.interaction_pair is None
            and not self._matches_query_target(result, plan=plan)
        ):
            return _EligibilityReason.ENTITY_MISMATCH
        if result.similarity_score >= self._min_similarity_score:
            return _EligibilityReason.ELIGIBLE

        eligibility_margin = self._eligibility_margin(
            result,
            plan=plan,
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
    def _eligibility_margin(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        margin = (
            cls._PAIR_BOOST_ELIGIBILITY_MARGIN
            if cls._requires_entity_pair_match(plan) and cls._matches_any_interaction_pair(result, plan=plan)
            else cls._BOOST_ELIGIBILITY_MARGIN
        )
        if cls._has_exact_drug_section_match(
            result,
            plan=plan,
        ) or cls._has_topic_title_prefix_match(result, plan=plan):
            margin = max(
                margin,
                cls._PAIR_BOOST_ELIGIBILITY_MARGIN,
            )
        if cls._has_same_sentence_interaction_pair(result, plan=plan):
            margin = max(
                margin,
                cls._VERIFIED_RELATION_ELIGIBILITY_MARGIN,
            )
        return margin

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
        pair_relationship_bonus = (
            cls._PAIR_SAME_SENTENCE_BONUS if cls._has_same_sentence_interaction_pair(result, plan=plan) else 0.0
        )
        return (
            result.similarity_score
            + cls._entity_match_bonus(result, plan=plan)
            + section_bonus
            + pair_relationship_bonus
        )

    @classmethod
    def _metadata_preference_score(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        document_type_bonus = cls._DOCUMENT_TYPE_BONUS if result.metadata.document_type in plan.document_types else 0.0
        interaction_type_bonus = (
            cls._INTERACTION_TYPE_BONUS
            if result.metadata.interaction_type is not None
            and result.metadata.interaction_type
            in {interaction_type.value for interaction_type in plan.interaction_types}
            else 0.0
        )
        return document_type_bonus + interaction_type_bonus

    @classmethod
    def _effective_section_types(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> set[KnowledgeSectionType]:
        if result.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            section_types = {result.metadata.section_type}
            if result.metadata.interaction_pair_keys:
                section_types.add(KnowledgeSectionType.INTERACTION)
            return section_types

        return cls._explicit_legacy_section_types(result) or {
            result.metadata.section_type,
        }

    @classmethod
    def _explicit_legacy_section_types(
        cls,
        result: RetrievedKnowledgeChunk,
    ) -> set[KnowledgeSectionType]:
        if result.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            return set()

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

        return section_types

    @classmethod
    def _has_exact_drug_section_match(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        if result.metadata.document_type != KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            return False
        if not cls._normalized_query_entities(plan).intersection(
            cls._metadata_entity_aliases(result),
        ):
            return False
        return bool(
            set(plan.section_types).intersection(
                cls._explicit_legacy_section_types(result),
            )
        )

    @classmethod
    def _entity_match_bonus(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> float:
        query_entities = cls._normalized_query_entities(plan)
        metadata_entities = cls._metadata_entity_aliases(result)
        if cls._has_topic_title_prefix_match(result, plan=plan):
            return cls._EXACT_TOPIC_TITLE_BONUS
        if len(query_entities) >= 2 and cls._matches_any_interaction_pair(result, plan=plan):
            return cls._PAIR_ENTITY_BONUS
        if query_entities.intersection(metadata_entities):
            return cls._EXACT_ENTITY_BONUS
        if any(
            query_entity in metadata_entity for query_entity in query_entities for metadata_entity in metadata_entities
        ):
            return cls._CONTAINED_ENTITY_BONUS
        return 0.0

    @classmethod
    def _matches_query_target(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        query_entities = cls._normalized_query_entities(plan)
        if not query_entities:
            return True
        if cls._entity_match_bonus(result, plan=plan) > 0.0:
            return True
        searchable_text = cls._normalize_name(
            f"{result.metadata.title} {result.content}",
        )
        return any(query_entity in searchable_text for query_entity in query_entities)

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
            len(MedicationKnowledgeRetriever._normalized_query_entities(plan)) >= 2
            and KnowledgeSectionType.INTERACTION in plan.section_types
        )

    @classmethod
    def _matches_any_interaction_pair(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        if set(plan.interaction_pair_keys).intersection(
            result.metadata.interaction_pair_keys,
        ):
            return True
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
        return any(
            cls._interaction_entity_matches_text(
                pair.left_name,
                searchable_text,
            )
            and cls._interaction_entity_matches_text(
                pair.right_name,
                searchable_text,
            )
            for pair in plan.interaction_pairs
        )

    @classmethod
    def _has_same_sentence_interaction_pair(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        if KnowledgeSectionType.INTERACTION not in plan.section_types:
            return False
        sentences = [
            cls._normalize_name(sentence)
            for sentence in re.split(r"[.!?。！？\n]+", result.content)
            if sentence.strip()
        ]
        return any(
            cls._interaction_entity_matches_text(pair.left_name, sentence)
            and cls._interaction_entity_matches_text(pair.right_name, sentence)
            for pair in plan.interaction_pairs
            for sentence in sentences
        )

    @classmethod
    def _interaction_entity_matches_text(
        cls,
        entity_name: str,
        normalized_text: str,
    ) -> bool:
        normalized_name = cls._normalize_name(entity_name)
        aliases = cls._GENERIC_FOOD_ALIASES.get(normalized_name)
        if aliases is None:
            return normalized_name in normalized_text
        return any(cls._normalize_name(alias) in normalized_text for alias in aliases)

    @classmethod
    def _has_topic_title_prefix_match(
        cls,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> bool:
        normalized_title = cls._normalize_name(result.metadata.title)
        return any(
            entity.entity_type == MedicationQueryEntityType.TOPIC
            and normalized_title.startswith(
                cls._normalize_name(entity.canonical_name),
            )
            for entity in plan.entities
        )

    @classmethod
    def _normalized_query_entities(
        cls,
        plan: MedicationKnowledgeQueryPlan,
    ) -> set[str]:
        return {cls._normalize_name(name) for name in plan.entity_names if len(cls._normalize_name(name)) >= 2}

    @staticmethod
    def _normalize_name(value: str) -> str:
        return "".join(value.casefold().split())
