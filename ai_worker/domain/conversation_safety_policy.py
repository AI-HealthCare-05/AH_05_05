from ai_worker.schemas.conversation_gate import (
    ConversationClassification,
    ConversationDisposition,
    ConversationGateDecision,
    ConversationIntent,
    ConversationSafetySignal,
)


class ConversationSafetyPolicy:
    """구조화된 대화 분류에 안전 우선순위를 적용한다."""

    def decide(self, classification: ConversationClassification) -> ConversationGateDecision:
        if classification.safety_signal is ConversationSafetySignal.HEALTH_URGENCY:
            disposition = ConversationDisposition.URGENT
        elif classification.safety_signal is ConversationSafetySignal.HARMFUL_INSTRUCTIONS:
            disposition = ConversationDisposition.BLOCK
        elif classification.intent is ConversationIntent.OFF_TOPIC:
            disposition = ConversationDisposition.REDIRECT
        else:
            disposition = ConversationDisposition.ALLOW

        return ConversationGateDecision(
            classification=classification,
            disposition=disposition,
        )
