from ai_worker.llm.chat_model_policy import (
    ChatModelPolicy,
    ChatModelStage,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


def test_model_policy_keeps_low_cost_stages_on_fast_model() -> None:
    policy = ChatModelPolicy(
        fast_model="gpt-4o-mini",
        accurate_model="gpt-4o-2024-11-20",
        high_accuracy_routing_enabled=True,
    )

    assert policy.model_for(ChatModelStage.CONVERSATION_GATE) == "gpt-4o-mini"
    assert policy.model_for(ChatModelStage.CONVERSATION_RESPONSE) == "gpt-4o-mini"
    assert policy.model_for(ChatModelStage.MEDICATION_NOTE_SUMMARY) == "gpt-4o-mini"


def test_model_policy_uses_accurate_model_only_for_enabled_reasoning_stages() -> None:
    policy = ChatModelPolicy(
        fast_model="gpt-4o-mini",
        accurate_model="gpt-4o-2024-11-20",
        high_accuracy_routing_enabled=True,
    )

    assert policy.model_for(ChatModelStage.CONDITIONAL_QUESTION_INTERPRETATION) == "gpt-4o-2024-11-20"
    assert policy.model_for(ChatModelStage.INTERACTION_EVIDENCE_REASONING) == "gpt-4o-2024-11-20"
    assert (
        policy.model_for(
            ChatModelStage.ANSWER_GENERATION,
            requested_section_types=[KnowledgeSectionType.FUNCTION],
        )
        == "gpt-4o-mini"
    )


def test_model_policy_can_keep_all_stages_on_fast_model_during_baseline_evaluation() -> None:
    policy = ChatModelPolicy(
        fast_model="gpt-4o-mini",
        accurate_model="gpt-4o-2024-11-20",
        high_accuracy_routing_enabled=False,
    )

    assert policy.model_for(ChatModelStage.CONDITIONAL_QUESTION_INTERPRETATION) == "gpt-4o-mini"
    assert policy.model_for(ChatModelStage.INTERACTION_EVIDENCE_REASONING) == "gpt-4o-mini"
