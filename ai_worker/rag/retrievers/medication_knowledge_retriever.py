import re

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.rag.metadata.supplement_interaction_registry import (
    supplement_pair_matches_text,
)
from ai_worker.rag.retrievers.candidate_retrieval import (
    MedicationKnowledgeCandidateRetriever,
    MedicationKnowledgeSearchStore,
)
from ai_worker.rag.retrievers.medication_knowledge_diagnostics import (
    MedicationKnowledgeDiagnosticsBuilder,
)
from ai_worker.rag.retrievers.medication_knowledge_eligibility import (
    MedicationKnowledgeEligibilityPolicy,
)
from ai_worker.rag.retrievers.medication_knowledge_eligibility import (
    MedicationKnowledgeEligibilityReason as _EligibilityReason,
)
from ai_worker.rag.retrievers.medication_knowledge_ranking import (
    MedicationKnowledgeRankingPolicy,
)
from ai_worker.rag.retrievers.parent_context_resolver import ParentContextResolver
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeRetrievalResult,
    KnowledgeSearchMode,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntityType,
    MedicationSearchExecutionPlan,
)


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
        self._eligibility_policy = MedicationKnowledgeEligibilityPolicy(
            min_similarity_score=min_similarity_score,
            declared_pair_matches=self._declared_pair_matches,
            requires_entity_pair_match=self._requires_entity_pair_match,
            matches_any_interaction_pair=lambda result, plan: self._matches_any_interaction_pair(
                result,
                plan=plan,
            ),
            has_query_entities=lambda plan: bool(self._normalized_query_entities(plan)),
            matches_query_target=lambda result, plan: self._matches_query_target(
                result,
                plan=plan,
            ),
            dense_confidence_score=self._dense_confidence_score,
            eligibility_margin=lambda result, plan: self._eligibility_margin(
                result,
                plan=plan,
            ),
            effective_section_types=self._effective_section_types,
            entity_match_bonus=lambda result, plan: self._entity_match_bonus(
                result,
                plan=plan,
            ),
            relevance_score=lambda result, plan, base_score: self._relevance_score(
                result,
                plan=plan,
                base_score=base_score,
            ),
        )
        self._ranking_policy = MedicationKnowledgeRankingPolicy(
            rank_key=lambda result, plan: self._ranking_score(
                result,
                plan=plan,
            ),
            effective_section_types=self._effective_section_types,
            explicit_legacy_section_types=self._explicit_legacy_section_types,
        )
        self._parent_context_resolver = ParentContextResolver()
        self._candidate_retriever = MedicationKnowledgeCandidateRetriever(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            dataset_version=normalized_version,
            eligibility_evaluator=lambda result, plan: self._eligibility_reason(
                result,
                plan=plan,
            ).value,
            section_coverage_evaluator=lambda results, plan: self._has_requested_section_coverage(
                results,
                plan=plan,
            ),
        )
        self._diagnostics_builder = MedicationKnowledgeDiagnosticsBuilder(
            rank_key=lambda result, plan: self._ranking_score(
                result,
                plan=plan,
            ),
            eligibility_reason=lambda result, plan: self._eligibility_reason(
                result,
                plan=plan,
            ).value,
            entity_matched=lambda result, plan: self._matches_query_target(
                result,
                plan=plan,
            ),
            effective_section_types=self._effective_section_types,
            pair_matched=lambda result, plan: self._matches_any_interaction_pair(
                result,
                plan=plan,
            ),
            dense_score=self._dense_confidence_score,
            has_query_entities=lambda plan: bool(self._normalized_query_entities(plan)),
            pair_required=self._requires_entity_pair_match,
        )

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
        candidates = await self._candidate_retriever.retrieve(
            execution_plan=execution_plan,
        )
        ranked = self._ranking_policy.rank(
            candidates.eligible,
            plan=plan,
        )
        selected = self._ranking_policy.select_diverse(
            ranked,
            plan=plan,
            limit=execution_plan.limit,
        )
        parent_context = self._parent_context_resolver.resolve(
            children=selected,
            candidates=candidates.eligible,
            query_plan=plan,
        )
        diagnostics = self._diagnostics_builder.build(
            results=candidates.results,
            observations=candidates.observations,
            eligibility_reasons=candidates.eligibility_reasons,
            selected=parent_context.chunks,
            plan=plan,
            entity_filtered_count=candidates.entity_filtered_count,
            broad_candidate_count=candidates.broad_candidate_count,
            attempted_search_tiers=candidates.attempted_search_tiers,
            selected_search_tier=candidates.selected_search_tier,
            parent_context_child_count=parent_context.child_count,
            parent_context_attached_count=parent_context.attached_parent_count,
            parent_context_rejected_mismatch_count=(parent_context.rejected_parent_mismatch_count),
        )
        return KnowledgeRetrievalResult(
            chunks=parent_context.chunks,
            diagnostics=diagnostics,
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
        return self._eligibility_policy.evaluate(
            result,
            plan=plan,
        )

    @staticmethod
    def _declared_pair_matches(
        plan: MedicationKnowledgeQueryPlan,
        result: RetrievedKnowledgeChunk,
    ) -> bool:
        if plan.interaction_pair is None:
            return True
        return supplement_pair_matches_text(
            plan.interaction_pair,
            result.metadata.title,
            result.content,
            *result.metadata.ingredient_names,
        )

    @staticmethod
    def _dense_confidence_score(
        result: RetrievedKnowledgeChunk,
    ) -> float | None:
        if result.search_mode == KnowledgeSearchMode.HYBRID:
            return result.dense_similarity_score
        if result.search_mode == KnowledgeSearchMode.DENSE:
            return result.similarity_score
        return None

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
        base_score: float | None = None,
    ) -> float:
        section_bonus = (
            cls._SECTION_BONUS if set(plan.section_types).intersection(cls._effective_section_types(result)) else 0.0
        )
        pair_relationship_bonus = (
            cls._PAIR_SAME_SENTENCE_BONUS if cls._has_same_sentence_interaction_pair(result, plan=plan) else 0.0
        )
        return (
            (result.similarity_score if base_score is None else base_score)
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
