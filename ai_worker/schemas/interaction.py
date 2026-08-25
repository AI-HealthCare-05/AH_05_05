import hashlib
import re
import unicodedata
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InteractionEntityKind(StrEnum):
    DRUG = "DRUG"
    SUPPLEMENT = "SUPPLEMENT"
    FOOD = "FOOD"


class InteractionPairType(StrEnum):
    DRUG_DRUG = "DRUG_DRUG"
    DRUG_SUPPLEMENT = "DRUG_SUPPLEMENT"
    SUPPLEMENT_SUPPLEMENT = "SUPPLEMENT_SUPPLEMENT"
    DRUG_FOOD = "DRUG_FOOD"


class InteractionRiskLevel(StrEnum):
    CONTRAINDICATED = "CONTRAINDICATED"
    HIGH_CAUTION = "HIGH_CAUTION"
    CAUTION = "CAUTION"
    INFORMATIONAL = "INFORMATIONAL"
    UNKNOWN = "UNKNOWN"


class InteractionReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class InteractionExtractionMethod(StrEnum):
    DETERMINISTIC_STRUCTURED = "DETERMINISTIC_STRUCTURED"
    MANUAL_ANNOTATION = "MANUAL_ANNOTATION"


def normalize_interaction_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


class InteractionEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: InteractionEntityKind
    display_name: str = Field(min_length=1)
    normalized_name: str | None = None
    source_code: str | None = None

    @model_validator(mode="after")
    def normalize_names(self) -> Self:
        display_name = normalize_interaction_name(self.display_name)
        if not display_name:
            raise ValueError("상호작용 주체 이름은 비어 있을 수 없습니다.")

        normalized_name = normalize_interaction_name(self.normalized_name or display_name).casefold()
        if not normalized_name:
            raise ValueError("상호작용 주체 정규화 이름은 비어 있을 수 없습니다.")

        self.display_name = display_name
        self.normalized_name = normalized_name
        if self.source_code is not None:
            self.source_code = normalize_interaction_name(self.source_code) or None
        return self

    @property
    def canonical_key(self) -> str:
        return f"{self.kind.value}:{self.normalized_name}"


class InteractionSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    raw_effect_text: str | None = None
    source_url: str | None = None

    @field_validator("source_id", "document_id", "record_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("출처 식별자는 비어 있을 수 없습니다.")
        return normalized

    @field_validator("raw_effect_text")
    @classmethod
    def preserve_non_blank_raw_effect(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("원본 금기 내용은 공백일 수 없습니다.")
        return value


_PAIR_TYPE_BY_ENTITY_KINDS = {
    frozenset({InteractionEntityKind.DRUG}): InteractionPairType.DRUG_DRUG,
    frozenset(
        {
            InteractionEntityKind.DRUG,
            InteractionEntityKind.SUPPLEMENT,
        }
    ): InteractionPairType.DRUG_SUPPLEMENT,
    frozenset({InteractionEntityKind.SUPPLEMENT}): InteractionPairType.SUPPLEMENT_SUPPLEMENT,
    frozenset(
        {
            InteractionEntityKind.DRUG,
            InteractionEntityKind.FOOD,
        }
    ): InteractionPairType.DRUG_FOOD,
}


def build_interaction_pair_key(
    left_entity: InteractionEntity,
    right_entity: InteractionEntity,
) -> str:
    canonical_entities = sorted([left_entity.canonical_key, right_entity.canonical_key])
    raw_key = "|".join(canonical_entities)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class InteractionRuleCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "interaction-rule-candidate-v1"
    candidate_id: str = ""
    pair_key: str = ""
    dataset_version: str = Field(min_length=1)
    pair_type: InteractionPairType
    left_entity: InteractionEntity
    right_entity: InteractionEntity
    risk_level: InteractionRiskLevel
    effect_summaries: list[str] = Field(min_length=1)
    source_records: list[InteractionSourceRecord] = Field(min_length=1)
    evidence_chunk_ids: list[str] = Field(default_factory=list)
    extraction_method: InteractionExtractionMethod = InteractionExtractionMethod.DETERMINISTIC_STRUCTURED
    review_status: InteractionReviewStatus = InteractionReviewStatus.PENDING

    @field_validator("dataset_version")
    @classmethod
    def normalize_dataset_version(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("dataset_version은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("effect_summaries")
    @classmethod
    def normalize_effect_summaries(cls, values: list[str]) -> list[str]:
        return _normalize_unique_text(values, field_name="금기 내용")

    @field_validator("source_records")
    @classmethod
    def normalize_source_records(
        cls,
        values: list[InteractionSourceRecord],
    ) -> list[InteractionSourceRecord]:
        normalized: list[InteractionSourceRecord] = []
        seen: set[tuple[str, str, str]] = set()
        for value in values:
            key = (value.source_id, value.document_id, value.record_id)
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        if not normalized:
            raise ValueError("출처 레코드는 하나 이상 필요합니다.")
        return normalized

    @field_validator("evidence_chunk_ids")
    @classmethod
    def normalize_evidence_chunk_ids(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = normalize_interaction_name(value)
            if item and item not in seen:
                normalized.append(item)
                seen.add(item)
        for value in normalized:
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError("근거 청크 ID는 SHA-256 형식이어야 합니다.")
        return normalized

    @model_validator(mode="after")
    def validate_and_build_identifiers(self) -> Self:
        expected_pair_type = _PAIR_TYPE_BY_ENTITY_KINDS.get(
            frozenset(
                {
                    self.left_entity.kind,
                    self.right_entity.kind,
                }
            )
        )
        if expected_pair_type != self.pair_type:
            raise ValueError("pair_type이 상호작용 주체 종류와 일치하지 않습니다.")
        if self.left_entity.canonical_key == self.right_entity.canonical_key:
            raise ValueError("같은 상호작용 주체를 한 조합에 중복할 수 없습니다.")
        if self.review_status != InteractionReviewStatus.PENDING:
            raise ValueError("자동 생성 후보의 review_status는 PENDING이어야 합니다.")

        self.pair_key = build_interaction_pair_key(
            self.left_entity,
            self.right_entity,
        )
        candidate_key = "|".join(
            [
                self.dataset_version,
                self.pair_key,
                self.risk_level.value,
            ]
        )
        self.candidate_id = hashlib.sha256(candidate_key.encode("utf-8")).hexdigest()
        return self


def _normalize_unique_text(
    values: list[str],
    *,
    field_name: str,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = normalize_interaction_name(value)
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    if not normalized:
        raise ValueError(f"{field_name}은 하나 이상 필요합니다.")
    return normalized
