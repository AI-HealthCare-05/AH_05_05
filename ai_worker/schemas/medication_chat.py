from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import SafetyStatus


class MedicationChatRoute(StrEnum):
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    SUPPLEMENT_GUIDE = "SUPPLEMENT_GUIDE"
    ACTIVE_INTAKE = "ACTIVE_INTAKE"
    INTERACTION = "INTERACTION"
    GENERAL_GUIDANCE = "GENERAL_GUIDANCE"
    CLARIFICATION = "CLARIFICATION"
    RESTRICTED = "RESTRICTED"


class MedicationChatSourceKind(StrEnum):
    PATIENT_MEDICATION = "PATIENT_MEDICATION"
    PATIENT_SUPPLEMENT = "PATIENT_SUPPLEMENT"
    MEDICATION_GUIDE = "MEDICATION_GUIDE"
    INTERACTION_RULE = "INTERACTION_RULE"
    PUBLIC_KNOWLEDGE = "PUBLIC_KNOWLEDGE"


class MedicationChatRequest(BaseModel):
    request_id: UUID
    user_id: int = Field(ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class ActiveMedication(BaseModel):
    medication_id: int = Field(ge=1)
    care_episode_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    dose: str | None = None
    efficacy: str | None = None
    administration: str | None = None
    precautions: str | None = None
    times_per_day: int | None = Field(default=None, ge=1)
    note: str | None = None
    days: int | None = Field(default=None, ge=1)
    prescribed_at: date | None = None


class ActiveSupplement(BaseModel):
    registration_id: int = Field(ge=1)
    supplement_nutrient_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    dose_amount: str
    dose_unit: str = Field(min_length=1)
    start_date: date
    end_date: date | None = None
    note: str | None = None


class ActiveIntakeContext(BaseModel):
    user_id: int = Field(ge=1)
    preferred_care_episode_id: int | None = Field(default=None, ge=1)
    medications: list[ActiveMedication] = Field(default_factory=list)
    supplements: list[ActiveSupplement] = Field(default_factory=list)


class MedicationGuideFact(BaseModel):
    medication_guide_id: int = Field(ge=1)
    item_seq: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    manufacturer_name: str = Field(min_length=1)
    efficacy: str
    usage_instructions: str
    pre_use_warning: str
    precautions: str
    drug_food_interactions: str
    adverse_reactions: str
    storage_instructions: str


class MedicationGuideLookup(BaseModel):
    guide: MedicationGuideFact | None = None
    representative_guide: MedicationGuideFact | None = None
    is_ambiguous: bool = False
    candidate_names: list[str] = Field(default_factory=list)


class InteractionRuleFact(BaseModel):
    interaction_rule_id: int = Field(ge=1)
    pair_key: str = Field(min_length=1)
    pair_type: str = Field(min_length=1)
    left_name: str = Field(min_length=1)
    right_name: str = Field(min_length=1)
    risk_level: str = Field(min_length=1)
    effect_texts: list[str] = Field(min_length=1)
    source_titles: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class MedicationChatSource(BaseModel):
    kind: MedicationChatSourceKind
    title: str = Field(min_length=1)
    organization: str | None = None
    url: str | None = None
    medication_id: int | None = Field(default=None, ge=1)
    care_episode_id: int | None = Field(default=None, ge=1)
    user_supplement_id: int | None = Field(default=None, ge=1)
    medication_guide_id: int | None = Field(default=None, ge=1)
    interaction_rule_id: int | None = Field(default=None, ge=1)
    dataset_key: str | None = None
    dataset_version: str | None = None
    vector_chunk_id: str | None = None
    source_page_number: int | None = Field(default=None, ge=1)
    similarity_score: float | None = Field(default=None, ge=-1.0, le=1.0)


class MedicationChatResult(BaseModel):
    request_id: UUID
    answer: str = Field(min_length=1)
    route: MedicationChatRoute
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(default_factory=list)
    sources: list[MedicationChatSource] = Field(default_factory=list)
    model_name: str | None = None
    model_version: str | None = None
    prompt_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    context_hash: str | None = Field(default=None, min_length=64, max_length=64)
