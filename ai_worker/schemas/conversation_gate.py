from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.domain.chat_content_compactor import CHAT_CONTENT_MAX_LENGTH
from ai_worker.schemas.medication_note_summary import MedicationNoteSummaryScope
from ai_worker.schemas.medication_search import MedicationQuestionConfidence


class ConversationIntent(StrEnum):
    GREETING = "GREETING"
    CASUAL = "CASUAL"
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

    @model_validator(mode="after")
    def validate_note_summary_scope(self) -> "ConversationClassification":
        is_note_summary = self.intent is ConversationIntent.MEDICATION_NOTE_SUMMARY
        if is_note_summary and self.note_summary_scope is None:
            raise ValueError("MEDICATION_NOTE_SUMMARY에는 note_summary_scope가 필요합니다.")
        if not is_note_summary and self.note_summary_scope is not None:
            raise ValueError("복약메모 요약이 아닌 intent에는 note_summary_scope를 사용할 수 없습니다.")
        if self.interaction_reference_names and self.intent is not ConversationIntent.SYMPTOM_INTERACTION_FOLLOW_UP:
            raise ValueError("상호작용 후속 질문이 아닌 intent에는 참조 대상을 사용할 수 없습니다.")
        if self.interaction_reference_names and len(self.interaction_reference_names) != 2:
            raise ValueError("상호작용 참조 대상은 두 개여야 합니다.")
        if self.intent is ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE and not self.symptom_context:
            raise ValueError("SYMPTOM_MEDICATION_GUIDANCE에는 확인된 symptom_context가 필요합니다.")
        if self.intent is not ConversationIntent.SYMPTOM_MEDICATION_GUIDANCE and self.symptom_context is not None:
            raise ValueError("증상 기반 약 정보 요청이 아닌 intent에는 symptom_context를 사용할 수 없습니다.")
        return self


class ConversationGateDecision(BaseModel):
    """서버 정책을 적용한 대화 Gate의 최종 결정이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: ConversationClassification
    disposition: ConversationDisposition
