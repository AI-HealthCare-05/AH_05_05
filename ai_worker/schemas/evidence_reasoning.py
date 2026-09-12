from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.knowledge import (
    KnowledgeSectionType,
    normalize_interaction_pair_keys,
)


def _normalize_required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("값은 공백일 수 없습니다.")
    return normalized


def _normalize_required_text_list(values: list[str]) -> list[str]:
    normalized = [_normalize_required_text(value) for value in values]
    return list(dict.fromkeys(normalized))


def _normalize_optional_pair_key(value: str | None) -> str | None:
    if value is None:
        return None
    return normalize_interaction_pair_keys([value])[0]


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

    evidence_id: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=4000)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    pair_keys: list[str] = Field(default_factory=list, max_length=16)
    study_scope: str | None = Field(default=None, max_length=80)

    @field_validator("evidence_id", "content", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("pair_keys")
    @classmethod
    def normalize_pair_keys(cls, values: list[str]) -> list[str]:
        return normalize_interaction_pair_keys(values)

    @field_validator("study_scope", mode="before")
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
    entity_names: list[str] = Field(min_length=2, max_length=12)
    requested_section_types: list[KnowledgeSectionType] = Field(min_length=1, max_length=4)
    interaction_pair_keys: list[str] = Field(default_factory=list, max_length=16)
    evidence_items: list[EvidenceItem] = Field(default_factory=list, max_length=30)
    approved_rules: list[EvidenceItem] = Field(default_factory=list, max_length=30)
    risk_profile: dict[str, str] = Field(default_factory=dict, max_length=8)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("entity_names")
    @classmethod
    def normalize_unique_text(cls, values: list[str]) -> list[str]:
        return _normalize_required_text_list(values)

    @field_validator("interaction_pair_keys")
    @classmethod
    def normalize_interaction_pairs(cls, values: list[str]) -> list[str]:
        return normalize_interaction_pair_keys(values)

    @model_validator(mode="after")
    def require_two_normalized_entities(self) -> "EvidenceReasoningInput":
        if len(self.entity_names) < 2:
            raise ValueError("상호작용 근거 판정에는 두 개 이상의 대상이 필요합니다.")
        return self


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_type: KnowledgeSectionType
    pair_key: str | None
    statement: str = Field(min_length=1, max_length=240)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    scope_note: str | None = Field(default=None, max_length=160)

    @field_validator("statement", mode="before")
    @classmethod
    def strip_statement(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        return _normalize_required_text_list(values)

    @field_validator("pair_key")
    @classmethod
    def normalize_pair_key(cls, value: str | None) -> str | None:
        return _normalize_optional_pair_key(value)

    @field_validator("scope_note", mode="before")
    @classmethod
    def normalize_scope_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_pair_key_for_interaction(self) -> "EvidenceClaim":
        if self.section_type is KnowledgeSectionType.INTERACTION and self.pair_key is None:
            raise ValueError("INTERACTION claim에는 pair_key가 필요합니다.")
        return self


class SupportedEvidenceAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pair_key: str
    statement: str = Field(min_length=1, max_length=240)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("statement", mode="before")
    @classmethod
    def strip_statement(cls, value: str) -> str:
        return _normalize_required_text(value)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        return _normalize_required_text_list(values)

    @field_validator("pair_key")
    @classmethod
    def normalize_pair_key(cls, value: str) -> str:
        return normalize_interaction_pair_keys([value])[0]


class EvidenceReasoningOutput(BaseModel):
    """자유형 추론 원문을 제외한 검증 가능한 근거 판정 결과."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reasoning_status: EvidenceReasoningStatus
    interaction_decision: InteractionEvidenceDecision
    claims: list[EvidenceClaim] = Field(default_factory=list, max_length=4)
    supported_action: SupportedEvidenceAction | None = None
    missing_section_types: list[KnowledgeSectionType] = Field(default_factory=list, max_length=4)
    conflict_evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    conflict_pair_key: str | None = None

    @field_validator("conflict_evidence_ids")
    @classmethod
    def normalize_conflict_evidence_ids(cls, values: list[str]) -> list[str]:
        return _normalize_required_text_list(values)

    @field_validator("conflict_pair_key")
    @classmethod
    def normalize_conflict_pair_key(cls, value: str | None) -> str | None:
        return _normalize_optional_pair_key(value)

    @model_validator(mode="after")
    def validate_decision_contract(self) -> "EvidenceReasoningOutput":
        if self.interaction_decision is InteractionEvidenceDecision.INTERACTION_CONFIRMED and not any(
            claim.section_type is KnowledgeSectionType.INTERACTION for claim in self.claims
        ):
            raise ValueError("INTERACTION_CONFIRMED에는 INTERACTION claim이 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.INTERACTION_CONFIRMED
            and self.reasoning_status
            not in {
                EvidenceReasoningStatus.SUPPORTED,
                EvidenceReasoningStatus.PARTIAL,
            }
        ):
            raise ValueError("INTERACTION_CONFIRMED에는 SUPPORTED 또는 PARTIAL 상태가 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.NO_DIRECT_EVIDENCE
            and self.reasoning_status
            not in {
                EvidenceReasoningStatus.PARTIAL,
                EvidenceReasoningStatus.INSUFFICIENT,
            }
        ):
            raise ValueError("NO_DIRECT_EVIDENCE에는 PARTIAL 또는 INSUFFICIENT 상태가 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.NO_DIRECT_EVIDENCE
            and self.supported_action is not None
        ):
            raise ValueError("NO_DIRECT_EVIDENCE에는 supported_action을 제공할 수 없습니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.CONFLICTING_EVIDENCE
            and len(self.conflict_evidence_ids) < 2
        ):
            raise ValueError("CONFLICTING_EVIDENCE에는 두 개 이상의 충돌 근거 ID가 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.CONFLICTING_EVIDENCE
            and self.conflict_pair_key is None
        ):
            raise ValueError("CONFLICTING_EVIDENCE에는 conflict_pair_key가 필요합니다.")
        if (
            self.interaction_decision is InteractionEvidenceDecision.CONFLICTING_EVIDENCE
            and self.reasoning_status is not EvidenceReasoningStatus.CONFLICTING
        ):
            raise ValueError("CONFLICTING_EVIDENCE에는 CONFLICTING 상태가 필요합니다.")
        if (
            self.interaction_decision is not InteractionEvidenceDecision.CONFLICTING_EVIDENCE
            and self.conflict_pair_key is not None
        ):
            raise ValueError("conflict_pair_key는 CONFLICTING_EVIDENCE에만 사용할 수 있습니다.")
        return self
