from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.knowledge import KnowledgeSectionType


class EvidenceReasoningStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class InteractionEvidenceDecision(StrEnum):
    INTERACTION_CONFIRMED = "INTERACTION_CONFIRMED"
    NO_DIRECT_EVIDENCE = "NO_DIRECT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceItem(BaseModel):
    """LLM에 제공하는 ID 기반 근거 단위."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    pair_keys: list[str] = Field(default_factory=list)
    study_scope: str | None = None

    @field_validator("evidence_id", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("pair_keys")
    @classmethod
    def normalize_pair_keys(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("study_scope")
    @classmethod
    def normalize_study_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EvidenceReasoningInput(BaseModel):
    """상호작용 근거 판정 체인의 제한된 입력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1)
    entity_names: list[str] = Field(min_length=2)
    requested_section_types: list[KnowledgeSectionType] = Field(min_length=1)
    interaction_pair_keys: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    approved_rules: list[EvidenceItem] = Field(default_factory=list)
    risk_profile: dict[str, str] = Field(default_factory=dict)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return value.strip()

    @field_validator("entity_names", "interaction_pair_keys")
    @classmethod
    def normalize_unique_text(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def require_two_normalized_entities(self) -> "EvidenceReasoningInput":
        if len(self.entity_names) < 2:
            raise ValueError("상호작용 근거 판정에는 두 개 이상의 대상이 필요합니다.")
        return self


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_type: KnowledgeSectionType
    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    scope_note: str | None = None

    @field_validator("statement")
    @classmethod
    def strip_statement(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @field_validator("scope_note")
    @classmethod
    def normalize_scope_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SupportedEvidenceAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

    @field_validator("statement")
    @classmethod
    def strip_statement(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class EvidenceReasoningOutput(BaseModel):
    """자유형 추론 원문을 제외한 검증 가능한 근거 판정 결과."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning_status: EvidenceReasoningStatus
    interaction_decision: InteractionEvidenceDecision
    claims: list[EvidenceClaim] = Field(default_factory=list)
    supported_action: SupportedEvidenceAction | None = None
    missing_section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    conflict_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("conflict_evidence_ids")
    @classmethod
    def normalize_conflict_evidence_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def validate_decision_contract(self) -> "EvidenceReasoningOutput":
        if self.interaction_decision is InteractionEvidenceDecision.INTERACTION_CONFIRMED and not any(
            claim.section_type is KnowledgeSectionType.INTERACTION for claim in self.claims
        ):
            raise ValueError("INTERACTION_CONFIRMED에는 INTERACTION claim이 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.CONFLICTING_EVIDENCE
            and len(self.conflict_evidence_ids) < 2
        ):
            raise ValueError("CONFLICTING_EVIDENCE에는 두 개 이상의 충돌 근거 ID가 필요합니다.")
        return self
