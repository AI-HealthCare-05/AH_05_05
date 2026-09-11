import pytest
from pydantic import ValidationError

from ai_worker.domain.conversation_safety_policy import ConversationSafetyPolicy
from ai_worker.schemas.conversation_gate import ConversationClassification
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope


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


def test_medication_note_summary_is_allowed_when_no_safety_signal_exists() -> None:
    classification = ConversationClassification(
        intent="MEDICATION_NOTE_SUMMARY",
        safety_signal="NONE",
        confidence="HIGH",
        note_summary_scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
    )

    assert ConversationSafetyPolicy().decide(classification).disposition == "ALLOW"


def test_conversation_classification_rejects_unapproved_model_fields() -> None:
    with pytest.raises(ValidationError):
        ConversationClassification(
            intent="GREETING",
            safety_signal="NONE",
            confidence="HIGH",
            reasoning="사용자에게 노출하지 않을 추론",
        )
