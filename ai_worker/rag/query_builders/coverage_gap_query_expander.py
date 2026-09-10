from dataclasses import dataclass

from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan


@dataclass(frozen=True)
class CoverageGapRetry:
    """근거가 부족할 때 한 번만 실행할 수 있는 확장 검색 계획."""

    query_plan: MedicationKnowledgeQueryPlan
    missing_section_types: list[KnowledgeSectionType]


class CoverageGapQueryExpander:
    """확정 엔터티와 부족한 답변 항목으로만 재검색 질의를 만든다."""

    _SECTION_TERMS = {
        KnowledgeSectionType.FUNCTION: ("효능", "기능성"),
        KnowledgeSectionType.DAILY_INTAKE: ("일일 섭취량", "복용법"),
        KnowledgeSectionType.CAUTION: ("주의사항", "이상반응"),
        KnowledgeSectionType.INTERACTION: ("상호작용", "병용"),
    }

    def build(
        self,
        *,
        query_plan: MedicationKnowledgeQueryPlan,
        missing_section_types: list[KnowledgeSectionType],
    ) -> CoverageGapRetry | None:
        supported_missing = [section for section in missing_section_types if section in self._SECTION_TERMS]
        if not supported_missing or not query_plan.entity_names:
            return None

        terms = self._unique_terms(
            [
                *self._searchable_entity_names(query_plan),
                *(term for section in supported_missing for term in self._SECTION_TERMS[section]),
            ]
        )
        return CoverageGapRetry(
            query_plan=query_plan.model_copy(
                update={
                    "expanded_query": " ".join(terms),
                    "alternate_queries": [],
                }
            ),
            missing_section_types=supported_missing,
        )

    @staticmethod
    def _searchable_entity_names(
        query_plan: MedicationKnowledgeQueryPlan,
    ) -> list[str]:
        """정식명은 유지하고 검수된 별칭만 재검색 질의에 보탠다."""
        if not query_plan.entities:
            return query_plan.entity_names
        return [
            expression
            for entity in query_plan.entities
            for expression in [entity.canonical_name, *entity.search_aliases]
        ]

    @staticmethod
    def _unique_terms(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))
