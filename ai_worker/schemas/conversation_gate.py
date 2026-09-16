from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.domain.chat_content_compactor import CHAT_CONTENT_MAX_LENGTH
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope
from ai_worker.schemas.medication_search import MedicationQuestionConfidence


class ConversationIntent(StrEnum):
    GREETING = "GREETING"
    CASUAL = "CASUAL"
    GENERAL_HEALTH_FOLLOW_UP = "GENERAL_HEALTH_FOLLOW_UP"
    VAGUE_SYMPTOM = "VAGUE_SYMPTOM"
    SPECIFIC_SYMPTOM = "SPECIFIC_SYMPTOM"
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    MEDICATION_GUIDE_FOLLOW_UP = "MEDICATION_GUIDE_FOLLOW_UP"
    SYMPTOM_MEDICATION_GUIDANCE = "SYMPTOM_MEDICATION_GUIDANCE"
    ACTIVE_MEDICATION_LIST = "ACTIVE_MEDICATION_LIST"
    ACTIVE_SUPPLEMENT_LIST = "ACTIVE_SUPPLEMENT_LIST"
    SYMPTOM_INTERACTION_FOLLOW_UP = "SYMPTOM_INTERACTION_FOLLOW_UP"
    FOLLOW_UP_SCHEDULE = "FOLLOW_UP_SCHEDULE"
    MEDICATION_NOTE_SUMMARY = "MEDICATION_NOTE_SUMMARY"
    OFF_TOPIC = "OFF_TOPIC"
    SENSITIVE_REQUEST = "SENSITIVE_REQUEST"


class ConversationSafetySignal(StrEnum):
    NONE = "NONE"
    HARMFUL_INSTRUCTIONS = "HARMFUL_INSTRUCTIONS"
    HEALTH_URGENCY = "HEALTH_URGENCY"


class ConversationDisposition(StrEnum):
    ALLOW = "ALLOW"
    REDIRECT = "REDIRECT"
    BLOCK = "BLOCK"
    URGENT = "URGENT"


class SymptomFollowUpField(StrEnum):
    LOCATION = "LOCATION"
    ONSET = "ONSET"
    SEVERITY = "SEVERITY"
    ASSOCIATED_SYMPTOMS = "ASSOCIATED_SYMPTOMS"


class ConversationClassification(BaseModel):
    """대화 Gate LLM이 반환할 수 있는 최소 분류 결과다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: ConversationIntent
    safety_signal: ConversationSafetySignal
    confidence: MedicationQuestionConfidence
    follow_up_fields: list[SymptomFollowUpField] = Field(default_factory=list, max_length=3)
    symptom_context: str | None = Field(default=None, max_length=CHAT_CONTENT_MAX_LENGTH)
    note_summary_scope: MedicationNoteSummaryScope | None = None
    interaction_reference_names: list[str] = Field(default_factory=list, max_length=2)

    @field_validator("interaction_reference_names")
    @classmethod
    def normalize_interaction_reference_names(cls, value: list[str]) -> list[str]:
        normalized = [name.strip() for name in value if name.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("상호작용 참조 대상은 중복될 수 없습니다.")
        return normalized

    @model_validator(mode="before")
    @classmethod
    def clear_fields_outside_their_intent(cls, value: Any) -> Any:
        """의도와 무관한 보조 필드는 거부하지 않고 비운다.

        OpenAI strict 모드는 교차 필드 조건을 스키마로 표현할 수 없고 모든 속성을
        required로 내리므로, 모델은 매 호출에서 보조 필드를 채울 수밖에 없다.
        보조 필드 하나 때문에 분류 전체를 버리면 의도 분기를 잃고 규칙 기반 경로로
        조용히 떨어진다. 실제로 고정 평가셋에서 이 손실이 반복 관측됐다.
        """

        if not isinstance(value, dict):
            return value
        intent = value.get("intent")
        intent = getattr(intent, "value", intent)
        normalized = dict(value)
        if intent != ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE.value:
            normalized["symptom_context"] = None
        if intent != ConversationIntent.MEDICATION_NOTE_SUMMARY.value:
            normalized["note_summary_scope"] = None
        references = normalized.get("interaction_reference_names") or []
        if intent != ConversationIntent.SYMPTOM_INTERACTION_FOLLOW_UP.value or len(references) != 2:
            normalized["interaction_reference_names"] = []
        return normalized

    @model_validator(mode="after")
    def validate_required_fields_for_intent(self) -> "ConversationClassification":
        if self.intent is ConversationIntent.MEDICATION_NOTE_SUMMARY and self.note_summary_scope is None:
            raise ValueError("MEDICATION_NOTE_SUMMARY에는 note_summary_scope가 필요합니다.")
        if self.intent is ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE and not self.symptom_context:
            raise ValueError("SYMPTOM_MEDICATION_GUIDANCE에는 확인된 symptom_context가 필요합니다.")
        return self


class ConversationGateDecision(BaseModel):
    """서버 정책을 적용한 대화 Gate의 최종 결정이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: ConversationClassification
    disposition: ConversationDisposition
