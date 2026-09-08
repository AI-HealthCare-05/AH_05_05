from ai_worker.rag.query_builders.coverage_gap_query_expander import (
    CoverageGapQueryExpander,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)


def build_plan() -> MedicationKnowledgeQueryPlan:
    return MedicationKnowledgeQueryPlan(
        original_query="마그네슘의 효능과 주의사항을 알려줘",
        expanded_query="마그네슘 효능 주의사항",
        entity_names=["마그네슘"],
        entities=[
            MedicationQueryEntity(
                surface="마그네슘",
                canonical_name="마그네슘",
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.CATALOG,
            )
        ],
        section_types=[
            KnowledgeSectionType.FUNCTION,
            KnowledgeSectionType.CAUTION,
        ],
    )


def test_expands_only_the_missing_requested_section_with_resolved_entities() -> None:
    retry = CoverageGapQueryExpander().build(
        query_plan=build_plan(),
        missing_section_types=[KnowledgeSectionType.CAUTION],
    )

    assert retry is not None
    assert retry.missing_section_types == [KnowledgeSectionType.CAUTION]
    assert retry.query_plan.original_query == "마그네슘의 효능과 주의사항을 알려줘"
    assert retry.query_plan.expanded_query == "마그네슘 주의사항 이상반응"
    assert retry.query_plan.alternate_queries == []


def test_does_not_expand_when_no_supported_section_is_missing() -> None:
    retry = CoverageGapQueryExpander().build(
        query_plan=build_plan(),
        missing_section_types=[],
    )

    assert retry is None
