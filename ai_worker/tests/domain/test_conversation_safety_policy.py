import pytest
from pydantic import ValidationError

from ai_worker.domain.conversation_safety_policy import ConversationSafetyPolicy
from ai_worker.schemas.conversation_gate import ConversationClassification


def test_health_urgency_wins_over_sensitive_topic() -> None:
    classification = ConversationClassification(
        intent="SPECIFIC_SYMPTOM",
        safety_signal="HEALTH_URGENCY",
        confidence="HIGH",
        follow_up_fields=["ASSOCIATED_SYMPTOMS"],
    )

    decision = ConversationSafetyPolicy().decide(classification)

    assert decision.disposition == "URGENT"


def test_harmful_instructions_are_blocked() -> None:
    classification = ConversationClassification(
        intent="SENSITIVE_REQUEST",
        safety_signal="HARMFUL_INSTRUCTIONS",
        confidence="HIGH",
    )

    assert ConversationSafetyPolicy().decide(classification).disposition == "BLOCK"


def test_off_topic_conversation_is_redirected_without_harmful_flag() -> None:
    classification = ConversationClassification(
        intent="OFF_TOPIC",
        safety_signal="NONE",
        confidence="HIGH",
    )

    assert ConversationSafetyPolicy().decide(classification).disposition == "REDIRECT"


def test_conversation_classification_rejects_unapproved_model_fields() -> None:
    with pytest.raises(ValidationError):
        ConversationClassification(
            intent="GREETING",
            safety_signal="NONE",
            confidence="HIGH",
            reasoning="사용자에게 노출하지 않을 추론",
        )
