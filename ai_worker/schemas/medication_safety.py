from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    InteractionExtractionMethod,
    InteractionReviewStatus,
    InteractionRiskLevel,
    normalize_interaction_name,
)


class MedicationSafetyRuleType(StrEnum):
    PREGNANCY_CONTRAINDICATION = "PREGNANCY_CONTRAINDICATION"
    AGE_CONTRAINDICATION = "AGE_CONTRAINDICATION"
    ELDERLY_CAUTION = "ELDERLY_CAUTION"
    DOSE_CAUTION = "DOSE_CAUTION"
    DURATION_CAUTION = "DURATION_CAUTION"
    DAILY_MAX_DOSE = "DAILY_MAX_DOSE"
    EXCIPIENT_CAUTION = "EXCIPIENT_CAUTION"


class SafetyConditionKind(StrEnum):
    PREGNANCY_STATUS = "PREGNANCY_STATUS"
    AGE_DAYS = "AGE_DAYS"
    AGE_YEARS = "AGE_YEARS"
    DAILY_DOSE = "DAILY_DOSE"
    DURATION_DAYS = "DURATION_DAYS"
    DOSAGE_FORM = "DOSAGE_FORM"
    ADMINISTRATION_ROUTE = "ADMINISTRATION_ROUTE"
    EXCIPIENT_PRESENT = "EXCIPIENT_PRESENT"


class SafetyComparisonOperator(StrEnum):
    EQ = "EQ"
    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"
    BETWEEN = "BETWEEN"
    PRESENT = "PRESENT"


class MedicationSafetyConditionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition_group_no: int = Field(ge=1, le=32767)
    condition_order: int = Field(ge=1, le=32767)
    condition_kind: SafetyConditionKind
    comparison_operator: SafetyComparisonOperator
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    value_text: str | None = None
    unit: str | None = None

    @field_validator("value_text", "unit")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_interaction_name(value) or None

    @model_validator(mode="after")
    def validate_operator_values(self) -> Self:
        if self.comparison_operator == SafetyComparisonOperator.BETWEEN:
            if self.value_min is None or self.value_max is None:
                raise ValueError("BETWEEN 조건은 value_min과 value_max가 모두 필요합니다.")
            if self.value_min > self.value_max:
                raise ValueError("BETWEEN 조건은 value_min이 value_max보다 클 수 없습니다.")
        elif (
            self.comparison_operator
            in {
                SafetyComparisonOperator.LT,
                SafetyComparisonOperator.LTE,
                SafetyComparisonOperator.GT,
                SafetyComparisonOperator.GTE,
            }
            and self.value_min is None
        ):
            raise ValueError("숫자 비교 조건은 value_min이 필요합니다.")
        elif (
            self.comparison_operator
            in {
                SafetyComparisonOperator.EQ,
                SafetyComparisonOperator.PRESENT,
            }
            and self.value_min is None
            and self.value_text is None
        ):
            raise ValueError("EQ/PRESENT 조건은 숫자값 또는 문자열값이 필요합니다.")
        return self

    @property
    def canonical_key(self) -> tuple[object, ...]:
        return (
            self.condition_group_no,
            self.condition_order,
            self.condition_kind.value,
            self.comparison_operator.value,
            str(self.value_min) if self.value_min is not None else None,
            str(self.value_max) if self.value_max is not None else None,
            self.value_text,
            self.unit,
        )


class MedicationSafetySourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    raw_effect_text: str = Field(min_length=1)
    source_published_at: str | None = None
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
    def trim_raw_effect_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("원본 안전 정보는 비어 있을 수 없습니다.")
        return trimmed

    @field_validator("source_published_at", "source_url")
    @classmethod
    def normalize_optional_source_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_interaction_name(value) or None

    @property
    def canonical_key(self) -> tuple[str, str, str]:
        return (self.source_id, self.document_id, self.record_id)


class MedicationSafetyRuleCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "medication-safety-rule-candidate-v1"
    candidate_id: str = ""
    rule_key: str = ""
    dataset_version: str = Field(min_length=1)
    entity: InteractionEntity
    rule_type: MedicationSafetyRuleType
    risk_level: InteractionRiskLevel
    guidance_text: str = Field(min_length=1)
    conditions: list[MedicationSafetyConditionCandidate] = Field(min_length=1)
    sources: list[MedicationSafetySourceRecord] = Field(min_length=1)
    extraction_method: InteractionExtractionMethod = InteractionExtractionMethod.DETERMINISTIC_STRUCTURED
    review_status: InteractionReviewStatus = InteractionReviewStatus.PENDING

    @field_validator("dataset_version", "guidance_text")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = normalize_interaction_name(value)
        if not normalized:
            raise ValueError("필수 문자열은 비어 있을 수 없습니다.")
        return normalized

    @model_validator(mode="after")
    def normalize_and_build_keys(self) -> Self:
        if self.entity.kind != InteractionEntityKind.DRUG:
            raise ValueError("단일 약물 안전 규칙의 entity kind는 DRUG여야 합니다.")
        if self.review_status != InteractionReviewStatus.PENDING:
            raise ValueError("자동 생성 후보의 review_status는 PENDING이어야 합니다.")

        conditions_by_position: dict[tuple[int, int], MedicationSafetyConditionCandidate] = {}
        for condition in self.conditions:
            position = (condition.condition_group_no, condition.condition_order)
            if position in conditions_by_position:
                raise ValueError("같은 조건 그룹과 순서를 중복할 수 없습니다.")
            conditions_by_position[position] = condition
        self.conditions = sorted(
            conditions_by_position.values(),
            key=lambda item: item.canonical_key,
        )

        sources_by_key = {source.canonical_key: source for source in self.sources}
        self.sources = [sources_by_key[key] for key in sorted(sources_by_key)]

        canonical = {
            "entity": self.entity.canonical_key,
            "rule_type": self.rule_type.value,
            "risk_level": self.risk_level.value,
            "conditions": [condition.canonical_key for condition in self.conditions],
        }
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        self.rule_key = hashlib.sha256(encoded).hexdigest()
        self.candidate_id = hashlib.sha256(f"{self.dataset_version}|{self.rule_key}".encode()).hexdigest()
        return self
