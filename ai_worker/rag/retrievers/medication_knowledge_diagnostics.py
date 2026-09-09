from collections.abc import Callable

from ai_worker.rag.retrievers.candidate_retrieval import (
    MedicationKnowledgeCandidateObservation,
)
from ai_worker.schemas.knowledge import (
    KnowledgeCandidateDiagnostic,
    KnowledgeCandidateRejectionReason,
    KnowledgeRetrievalDiagnostics,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan

RankKey = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], tuple[float, float, str]]
EligibilityReason = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], str]
EntityMatched = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], bool]
SectionTypes = Callable[[RetrievedKnowledgeChunk], set]
PairMatched = Callable[[RetrievedKnowledgeChunk, MedicationKnowledgeQueryPlan], bool]
DenseScore = Callable[[RetrievedKnowledgeChunk], float | None]
PlanPredicate = Callable[[MedicationKnowledgeQueryPlan], bool]


class MedicationKnowledgeDiagnosticsBuilder:
    """검색 후보 관측값을 외부 진단 스키마로 변환합니다."""

    def __init__(
        self,
        *,
        rank_key: RankKey,
        eligibility_reason: EligibilityReason,
        entity_matched: EntityMatched,
        effective_section_types: SectionTypes,
        pair_matched: PairMatched,
        dense_score: DenseScore,
        has_query_entities: PlanPredicate,
        pair_required: PlanPredicate,
    ) -> None:
        self._rank_key = rank_key
        self._eligibility_reason = eligibility_reason
        self._entity_matched = entity_matched
        self._effective_section_types = effective_section_types
        self._pair_matched = pair_matched
        self._dense_score = dense_score
        self._has_query_entities = has_query_entities
        self._pair_required = pair_required

    def build(
        self,
        *,
        results: list[RetrievedKnowledgeChunk],
        observations: list[MedicationKnowledgeCandidateObservation],
        eligibility_reasons: list[str],
        selected: list[RetrievedKnowledgeChunk],
        plan: MedicationKnowledgeQueryPlan,
        entity_filtered_count: int,
        broad_candidate_count: int,
        attempted_search_tiers: list,
        selected_search_tier,
        parent_context_child_count: int = 0,
        parent_context_attached_count: int = 0,
        parent_context_rejected_mismatch_count: int = 0,
    ) -> KnowledgeRetrievalDiagnostics:
        return KnowledgeRetrievalDiagnostics(
            raw_candidate_count=len(results),
            entity_filtered_count=entity_filtered_count,
            broad_candidate_count=broad_candidate_count,
            fallback_used=len(attempted_search_tiers) > 1,
            eligible_candidate_count=eligibility_reasons.count("ELIGIBLE"),
            rejected_below_score_count=eligibility_reasons.count("BELOW_SCORE"),
            rejected_entity_mismatch_count=eligibility_reasons.count("ENTITY_MISMATCH"),
            rejected_pair_mismatch_count=eligibility_reasons.count("PAIR_MISMATCH"),
            accepted_count=len(selected),
            parent_context_child_count=parent_context_child_count,
            parent_context_attached_count=parent_context_attached_count,
            parent_context_rejected_mismatch_count=parent_context_rejected_mismatch_count,
            max_raw_score=max((result.similarity_score for result in results), default=None),
            max_score=max((result.similarity_score for result in selected), default=None),
            attempted_search_tiers=attempted_search_tiers,
            selected_search_tier=selected_search_tier,
            candidate_diagnostics=self._candidate_diagnostics(
                observations=observations,
                selected=selected,
                plan=plan,
            ),
        )

    def _candidate_diagnostics(
        self,
        *,
        observations: list[MedicationKnowledgeCandidateObservation],
        selected: list[RetrievedKnowledgeChunk],
        plan: MedicationKnowledgeQueryPlan,
    ) -> list[KnowledgeCandidateDiagnostic]:
        unique_observations: list[MedicationKnowledgeCandidateObservation] = []
        seen_hashes: set[str] = set()
        for observation in observations:
            content_hash = observation.result.metadata.content_hash
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            unique_observations.append(observation)
        ranked = sorted(
            unique_observations,
            key=lambda observation: self._rank_key(observation.result, plan),
            reverse=True,
        )[:20]
        selected_ids = {result.chunk_id for result in selected}
        pair_required = plan.interaction_pair is not None or self._pair_required(plan)
        diagnostics: list[KnowledgeCandidateDiagnostic] = []
        for adjusted_rank, observation in enumerate(ranked, start=1):
            result = observation.result
            reason = self._eligibility_reason(result, plan)
            raw_score = result.similarity_score
            adjusted_score = self._rank_key(result, plan)[0]
            diagnostics.append(
                KnowledgeCandidateDiagnostic(
                    document_id=result.metadata.document_id,
                    chunk_id=result.chunk_id,
                    search_tier=observation.search_tier,
                    raw_rank=observation.raw_rank,
                    raw_similarity_score=raw_score,
                    dense_similarity_score=self._dense_score(result),
                    boost_score=round(adjusted_score - raw_score, 6),
                    adjusted_score=round(adjusted_score, 6),
                    adjusted_rank=adjusted_rank,
                    entity_matched=(not self._has_query_entities(plan) or self._entity_matched(result, plan)),
                    section_matched=(
                        not plan.section_types
                        or bool(set(plan.section_types).intersection(self._effective_section_types(result)))
                    ),
                    pair_matched=self._pair_matched(result, plan) if pair_required else None,
                    eligible=reason == "ELIGIBLE",
                    rejection_reason=(None if reason == "ELIGIBLE" else KnowledgeCandidateRejectionReason(reason)),
                    selected_in_top_5=result.chunk_id in selected_ids,
                )
            )
        return diagnostics
