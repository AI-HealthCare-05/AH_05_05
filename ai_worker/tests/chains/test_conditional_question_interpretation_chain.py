import pytest

from ai_worker.chains.conditional_question_interpretation_chain import (
    ConditionalQuestionInterpretationInput,
    ConditionalQuestionInterpretationOutput,
    DirectionalSearchStimulus,
    DirectionalSearchTarget,
    build_conditional_question_interpretation_chain,
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
        candidate_entities={
            "candidate_0": MedicationQueryEntity(
                surface="타이레놀",
                canonical_name="타이레놀",
                entity_type=MedicationQueryEntityType.BRAND_ALIAS,
                kind=InteractionEntityKind.DRUG,
                source=MedicationQueryEntitySource.CATALOG,
            )
        },
        requested_section_types=[KnowledgeSectionType.CAUTION],
        trigger_reasons=["SESSION_REFERENCE"],
        candidate_pair_keys=["candidate_0|candidate_1"],
        allowed_search_terms=["타이레놀", "주의사항"],
    )


def test_input_requires_catalog_candidates_and_safe_trigger_reasons() -> None:
    value = build_input()

    assert value.candidate_entities["candidate_0"].canonical_name == "타이레놀"
    assert value.trigger_reasons == ["SESSION_REFERENCE"]


def test_output_contains_only_structured_fields_not_chain_of_thought() -> None:
    payload = ConditionalQuestionInterpretationOutput(
        normalized_question="그 약의 주의사항도 알려주세요.",
        candidate_entity_keys=["candidate_0"],
        requested_section_types=[KnowledgeSectionType.CAUTION],
        confidence="MEDIUM",
        reason_codes=["SESSION_REFERENCE"],
    )

    assert payload.model_dump() == {
        "interpretation_version": "conditional-question-interpretation-v3",
        "normalized_question": "그 약의 주의사항도 알려주세요.",
        "route": None,
        "candidate_entity_keys": ["candidate_0"],
        "requested_section_types": [KnowledgeSectionType.CAUTION],
        "interaction_pair_keys": [],
        "stimuli": [],
        "confidence": "MEDIUM",
        "reason_codes": ["SESSION_REFERENCE"],
        "needs_clarification": False,
        "clarification_question": None,
    }


def test_output_accepts_candidate_keys_and_route() -> None:
    payload = ConditionalQuestionInterpretationOutput(
        normalized_question="마그네슘과 아연을 같이 먹어도 되나요?",
        route="INTERACTION",
        candidate_entity_keys=["candidate_0", "candidate_1"],
        requested_section_types=[KnowledgeSectionType.INTERACTION],
        interaction_pair_keys=["candidate_0|candidate_1"],
        stimuli=[
            DirectionalSearchStimulus(
                query="마그네슘 아연 상호작용",
                target=DirectionalSearchTarget.INTERACTION_EVIDENCE,
                section_types=[KnowledgeSectionType.INTERACTION],
                purpose="두 성분의 직접 관계를 찾습니다.",
            )
        ],
        confidence="MEDIUM",
        reason_codes=["MULTI_ENTITY"],
    )

    assert payload.candidate_entity_keys == ["candidate_0", "candidate_1"]
    assert payload.route == "INTERACTION"


def test_output_rejects_free_form_entity_names() -> None:
    with pytest.raises(ValueError):
        ConditionalQuestionInterpretationOutput.model_validate(
            {
                "route": "INTERACTION",
                "normalized_question": "임의 약물 상호작용",
                "candidate_entity_keys": [],
                "canonical_entity_names": ["임의 생성 약물"],
                "confidence": "LOW",
            }
        )


def test_rejects_free_form_reasoning_field() -> None:
    with pytest.raises(ValueError):
        ConditionalQuestionInterpretationOutput.model_validate(
            {
                "canonical_entity_names": ["타이레놀"],
                "normalized_question": "타이레놀",
                "requested_section_types": [],
                "confidence": "MEDIUM",
                "reason_codes": [],
                "reasoning": "숨겨진 추론",
            }
        )


def test_output_requires_clarification_question_only_when_needed() -> None:
    with pytest.raises(ValueError, match="확인 질문"):
        ConditionalQuestionInterpretationOutput(
            normalized_question="제품을 확인해 주세요.",
            confidence="LOW",
            needs_clarification=True,
        )

    with pytest.raises(ValueError, match="확인 질문"):
        ConditionalQuestionInterpretationOutput(
            normalized_question="타이레놀의 효능",
            confidence="HIGH",
            clarification_question="제품명을 알려주세요.",
        )


async def test_chain_uses_v7_directional_stage_prompt() -> None:
    observed_messages = []

    class Client:
        async def ainvoke(self, messages):
            observed_messages.extend(messages)
            return {
                "normalized_question": "타이레놀의 주의사항도 알려주세요.",
                "candidate_entity_keys": ["candidate_0"],
                "requested_section_types": ["CAUTION"],
                "confidence": "MEDIUM",
                "reason_codes": ["SESSION_REFERENCE"],
            }

    chain = build_conditional_question_interpretation_chain(
        model="test-model",
        client=Client(),
    )

    output = await chain.ainvoke(build_input())

    assert output.normalized_question == "타이레놀의 주의사항도 알려주세요."
    assert len(observed_messages) == 2
    assert "검색 방향" in observed_messages[0].content
    assert '"candidate_0"' in observed_messages[1].content
    assert '"타이레놀"' in observed_messages[1].content
