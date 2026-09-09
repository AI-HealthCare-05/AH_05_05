import pytest

from ai_worker.chains.conditional_question_interpretation_chain import (
    ConditionalQuestionInterpretationInput,
    ConditionalQuestionInterpretationOutput,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import (
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)


def build_input() -> ConditionalQuestionInterpretationInput:
    return ConditionalQuestionInterpretationInput(
        question="그 약의 주의사항도 알려줘",
        candidate_entities=[
            MedicationQueryEntity(
                surface="타이레놀",
                canonical_name="타이레놀",
                entity_type=MedicationQueryEntityType.BRAND_ALIAS,
                kind=InteractionEntityKind.DRUG,
                source=MedicationQueryEntitySource.CATALOG,
            )
        ],
        requested_section_types=[KnowledgeSectionType.CAUTION],
        trigger_reasons=["SESSION_REFERENCE"],
    )


def test_input_requires_catalog_candidates_and_safe_trigger_reasons() -> None:
    value = build_input()

    assert value.candidate_entities[0].canonical_name == "타이레놀"
    assert value.trigger_reasons == ["SESSION_REFERENCE"]


def test_output_contains_only_structured_fields_not_chain_of_thought() -> None:
    payload = ConditionalQuestionInterpretationOutput(
        canonical_entity_names=["타이레놀"],
        requested_section_types=[KnowledgeSectionType.CAUTION],
        confidence="MEDIUM",
        reason_codes=["SESSION_REFERENCE"],
    )

    assert payload.model_dump() == {
        "interpretation_version": "conditional-question-interpretation-v1",
        "canonical_entity_names": ["타이레놀"],
        "requested_section_types": [KnowledgeSectionType.CAUTION],
        "confidence": "MEDIUM",
        "reason_codes": ["SESSION_REFERENCE"],
    }


def test_rejects_free_form_reasoning_field() -> None:
    with pytest.raises(ValueError):
        ConditionalQuestionInterpretationOutput.model_validate(
            {
                "canonical_entity_names": ["타이레놀"],
                "requested_section_types": [],
                "confidence": "MEDIUM",
                "reason_codes": [],
                "reasoning": "숨겨진 추론",
            }
        )
