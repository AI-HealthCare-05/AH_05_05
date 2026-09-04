import re
import unicodedata

from ai_worker.schemas.knowledge import (
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import (
    InteractionRuleFact,
    MedicationEvidenceCoverage,
    MedicationGuideLookup,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan


class MedicationEvidenceCoverageEvaluator:
    """질문 항목마다 답변에 사용할 수 있는 근거가 있는지 판정한다."""

    _SUPPORTED_SECTIONS = (
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
        KnowledgeSectionType.CAUTION,
        KnowledgeSectionType.INTERACTION,
    )
    _EMPTY_VALUES = {
        "",
        "-",
        "없음",
        "없습니다",
        "해당 없음",
        "해당없음",
        "자료 없음",
        "정보 없음",
    }

    def evaluate(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        guide_lookup: MedicationGuideLookup,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
    ) -> MedicationEvidenceCoverage:
        requested = [section for section in self._SUPPORTED_SECTIONS if section in query_plan.section_types]
        covered = self._covered_non_interaction_sections(
            requested=requested,
            guide_lookup=guide_lookup,
            chunks=chunks,
        )
        verified_pair_keys = self._verified_interaction_pair_keys(
            query_plan=query_plan,
            rules=rules,
            chunks=chunks,
        )
        if KnowledgeSectionType.INTERACTION in requested and verified_pair_keys:
            covered.append(KnowledgeSectionType.INTERACTION)

        return MedicationEvidenceCoverage(
            requested_section_types=requested,
            covered_section_types=covered,
            missing_section_types=[section for section in requested if section not in covered],
            verified_interaction_pair_keys=verified_pair_keys,
        )

    def _covered_non_interaction_sections(
        self,
        *,
        requested: list[KnowledgeSectionType],
        guide_lookup: MedicationGuideLookup,
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[KnowledgeSectionType]:
        available: set[KnowledgeSectionType] = {chunk.metadata.section_type for chunk in chunks}
        guide = guide_lookup.guide
        if guide is not None:
            if self._has_value(guide.efficacy):
                available.add(KnowledgeSectionType.FUNCTION)
            if self._has_value(guide.usage_instructions):
                available.add(KnowledgeSectionType.DAILY_INTAKE)
            if any(
                self._has_value(value)
                for value in (
                    guide.pre_use_warning,
                    guide.precautions,
                    guide.adverse_reactions,
                )
            ):
                available.add(KnowledgeSectionType.CAUTION)

        return [
            section for section in requested if section != KnowledgeSectionType.INTERACTION and section in available
        ]

    def _verified_interaction_pair_keys(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        rules: list[InteractionRuleFact],
        chunks: list[RetrievedKnowledgeChunk],
    ) -> list[str]:
        requested_keys = set(query_plan.interaction_pair_keys)
        if not requested_keys:
            return []

        verified = requested_keys.intersection(rule.pair_key for rule in rules)
        for chunk in chunks:
            chunk_keys = set(chunk.metadata.interaction_pair_keys)
            verified.update(requested_keys.intersection(chunk_keys))
            if chunk_keys or chunk.metadata.section_type != KnowledgeSectionType.INTERACTION:
                continue
            for pair in query_plan.interaction_pairs:
                if pair.pair_key not in requested_keys:
                    continue
                if self._same_sentence_contains_pair(
                    chunk.content,
                    left_name=pair.left_name,
                    right_name=pair.right_name,
                ):
                    verified.add(pair.pair_key)
        return [key for key in query_plan.interaction_pair_keys if key in verified]

    @classmethod
    def _same_sentence_contains_pair(
        cls,
        content: str,
        *,
        left_name: str,
        right_name: str,
    ) -> bool:
        left = cls._normalize(left_name)
        right = cls._normalize(right_name)
        return any(
            left in cls._normalize(sentence) and right in cls._normalize(sentence)
            for sentence in re.split(r"[.!?。！？\n]+", content)
            if sentence.strip()
        )

    @classmethod
    def _has_value(cls, value: str) -> bool:
        return value.strip() not in cls._EMPTY_VALUES

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[^0-9a-z가-힣]", "", normalized)
