from dataclasses import dataclass
from decimal import Decimal

from ai_worker.services.medication_safety_approval_service import (
    validate_rule_for_approval,
)


@dataclass
class Rule:
    rule_key: str = "a" * 64
    rule_dataset_version: str = "medication-safety-v2"
    interaction_entity_id: int | None = 1
    review_status: str = "PENDING"
    approved_at: object | None = None


@dataclass
class Condition:
    condition_kind: str = "DAILY_DOSE"
    comparison_operator: str = "GTE"
    value_min: Decimal | None = Decimal("4000")
    value_max: Decimal | None = None
    value_text: str | None = None
    unit: str | None = "mg/day"


@dataclass
class Source:
    source_id: str = "mfds"
    document_id: str = "dur-dose"
    record_id: str = "1"
    raw_effect_text: str = "1일 4000mg 이상 주의"


def test_valid_numeric_rule_has_no_approval_issues() -> None:
    issues = validate_rule_for_approval(
        Rule(),
        [Condition()],
        [Source()],
        dataset_version="medication-safety-v2",
    )

    assert issues == []


def test_numeric_condition_requires_value_and_unit() -> None:
    issues = validate_rule_for_approval(
        Rule(),
        [Condition(value_min=None, unit=None)],
        [Source()],
        dataset_version="medication-safety-v2",
    )

    assert issues == ["MISSING_CONDITION_VALUE", "MISSING_CONDITION_UNIT"]


def test_text_condition_requires_value_text() -> None:
    issues = validate_rule_for_approval(
        Rule(),
        [
            Condition(
                condition_kind="EXCIPIENT_PRESENT",
                comparison_operator="PRESENT",
                value_min=None,
                value_text=None,
                unit=None,
            )
        ],
        [Source()],
        dataset_version="medication-safety-v2",
    )

    assert issues == ["MISSING_CONDITION_TEXT"]


def test_rule_identity_source_and_approval_state_are_validated() -> None:
    issues = validate_rule_for_approval(
        Rule(
            rule_key="not-a-sha256",
            rule_dataset_version="medication-safety-v1",
            interaction_entity_id=None,
            review_status="APPROVED",
        ),
        [Condition()],
        [],
        dataset_version="medication-safety-v2",
    )

    assert issues == [
        "INVALID_RULE_KEY",
        "DATASET_VERSION_MISMATCH",
        "MISSING_INTERACTION_ENTITY",
        "MISSING_SOURCE",
        "APPROVED_AT_REQUIRED",
    ]


def test_blank_source_fields_are_rejected() -> None:
    issues = validate_rule_for_approval(
        Rule(),
        [Condition()],
        [Source(source_id="", raw_effect_text=" ")],
        dataset_version="medication-safety-v2",
    )

    assert issues == ["INVALID_SOURCE"]
