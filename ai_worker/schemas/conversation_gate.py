from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_worker.schemas.medication_search import MedicationQuestionConfidence


class ConversationIntent(StrEnum):
    GREETING = "GREETING"
    CASUAL = "CASUAL"
    VAGUE_SYMPTOM = "VAGUE_SYMPTOM"
    SPECIFIC_SYMPTOM = "SPECIFIC_SYMPTOM"
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


class ConversationGateDecision(BaseModel):
    """서버 정책을 적용한 대화 Gate의 최종 결정이다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: ConversationClassification
    disposition: ConversationDisposition
