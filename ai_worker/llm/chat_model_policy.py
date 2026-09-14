from enum import StrEnum

from ai_worker.schemas.knowledge import KnowledgeSectionType


class ChatModelStage(StrEnum):
    CONVERSATION_GATE = "conversation_gate"
    CONDITIONAL_QUESTION_INTERPRETATION = "conditional_question_interpretation"
    INTERACTION_EVIDENCE_REASONING = "interaction_evidence_reasoning"
    ANSWER_GENERATION = "answer_generation"
    CONVERSATION_RESPONSE = "conversation_response"
    MEDICATION_NOTE_SUMMARY = "medication_note_summary"


class ChatModelPolicy:
    """정확도가 필요한 추론 단계에만 상위 모델을 쓰는 명시적 정책."""

    _ACCURATE_REASONING_STAGES = frozenset(
        {
            ChatModelStage.CONDITIONAL_QUESTION_INTERPRETATION,
            ChatModelStage.INTERACTION_EVIDENCE_REASONING,
        }
    )

    def __init__(
        self,
        *,
        fast_model: str,
        accurate_model: str,
        high_accuracy_routing_enabled: bool,
    ) -> None:
        self._fast_model = fast_model.strip()
        self._accurate_model = accurate_model.strip()
        self._high_accuracy_routing_enabled = high_accuracy_routing_enabled
        if not self._fast_model or not self._accurate_model:
            raise ValueError("채팅 모델명은 비어 있을 수 없습니다.")

    def model_for(
        self,
        stage: ChatModelStage,
        *,
        requested_section_types: list[KnowledgeSectionType] | None = None,
    ) -> str:
        if not self._high_accuracy_routing_enabled:
            return self._fast_model
        if stage in self._ACCURATE_REASONING_STAGES:
            return self._accurate_model
        if stage is ChatModelStage.ANSWER_GENERATION:
            sections = set(requested_section_types or [])
            if KnowledgeSectionType.INTERACTION in sections or len(sections) > 1:
                return self._accurate_model
        return self._fast_model
