from collections.abc import Callable
from enum import StrEnum

from ai_worker.schemas.knowledge import (
    KnowledgeSearchMode,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan


class MedicationKnowledgeEligibilityReason(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BELOW_SCORE = "BELOW_SCORE"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    PAIR_MISMATCH = "PAIR_MISMATCH"


PairTextMatcher = Callable[[MedicationKnowledgeQueryPlan, RetrievedKnowledgeChunk], bool]
PlanMatcher = Callable[[MedicationKnowledgeQueryPlan], bool]
CandidateMatcher = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], bool]
DenseScore = Callable[[RetrievedKnowledgeChunk], float | None]
Margin = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], float]
SectionTypes = Callable[[RetrievedKnowledgeChunk], set[KnowledgeSectionType]]
EntityBonus = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], float]
RelevanceScore = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan, float], float]


class MedicationKnowledgeEligibilityPolicy:
    """후보의 쌍·엔터티·dense 신뢰도 수용 여부를 현재 기준으로 판정합니다."""

    def __init__(
        self,
        *,
        min_similarity_score: float,
        declared_pair_matches: PairTextMatcher,
        has_declared_pair_key_match: CandidateMatcher,
        requires_entity_pair_match: PlanMatcher,
        matches_any_interaction_pair: CandidateMatcher,
        has_query_entities: PlanMatcher,
        matches_query_target: CandidateMatcher,
        dense_confidence_score: DenseScore,
        eligibility_margin: Margin,
        effective_section_types: SectionTypes,
        entity_match_bonus: EntityBonus,
        relevance_score: RelevanceScore,
    ) -> None:
        self._min_similarity_score = min_similarity_score
        self._declared_pair_matches = declared_pair_matches
        self._has_declared_pair_key_match = has_declared_pair_key_match
        self._requires_entity_pair_match = requires_entity_pair_match
        self._matches_any_interaction_pair = matches_any_interaction_pair
        self._has_query_entities = has_query_entities
        self._matches_query_target = matches_query_target
        self._dense_confidence_score = dense_confidence_score
        self._eligibility_margin = eligibility_margin
        self._effective_section_types = effective_section_types
        self._entity_match_bonus = entity_match_bonus
        self._relevance_score = relevance_score

    def evaluate(
        self,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> MedicationKnowledgeEligibilityReason:
        if plan.interaction_pair is not None and not self._declared_pair_matches(plan, result):
            return MedicationKnowledgeEligibilityReason.PAIR_MISMATCH
        if (
            plan.interaction_pair is None
            and self._requires_entity_pair_match(plan)
            and not self._matches_any_interaction_pair(result, plan)
        ):
            return MedicationKnowledgeEligibilityReason.PAIR_MISMATCH
        if (
            self._has_query_entities(plan)
            and not self._requires_entity_pair_match(plan)
            and plan.interaction_pair is None
            and not self._matches_query_target(result, plan)
        ):
            return MedicationKnowledgeEligibilityReason.ENTITY_MISMATCH
        if result.search_mode == KnowledgeSearchMode.BM25:
            return MedicationKnowledgeEligibilityReason.ELIGIBLE
        return self._evaluate_dense_score(result, plan=plan)

    def _evaluate_dense_score(
        self,
        result: RetrievedKnowledgeChunk,
        *,
        plan: MedicationKnowledgeQueryPlan,
    ) -> MedicationKnowledgeEligibilityReason:
        confidence_score = self._dense_confidence_score(result)
        if confidence_score is None:
            return MedicationKnowledgeEligibilityReason.BELOW_SCORE
        if self._has_declared_pair_key_match(result, plan):
            return MedicationKnowledgeEligibilityReason.ELIGIBLE
        if confidence_score >= self._min_similarity_score:
            return MedicationKnowledgeEligibilityReason.ELIGIBLE

        minimum_raw_score = max(
            0.0,
            self._min_similarity_score - self._eligibility_margin(result, plan),
        )
        if confidence_score < minimum_raw_score:
            return MedicationKnowledgeEligibilityReason.BELOW_SCORE
        if plan.section_types and not set(plan.section_types).intersection(
            self._effective_section_types(result),
        ):
            return MedicationKnowledgeEligibilityReason.BELOW_SCORE
        if self._entity_match_bonus(result, plan) <= 0.0:
            return MedicationKnowledgeEligibilityReason.ENTITY_MISMATCH
        if self._relevance_score(result, plan, confidence_score) < self._min_similarity_score:
            return MedicationKnowledgeEligibilityReason.BELOW_SCORE
        return MedicationKnowledgeEligibilityReason.ELIGIBLE
