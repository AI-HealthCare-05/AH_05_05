from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_NUMERIC_CONDITION_KINDS = {
    "AGE_DAYS",
    "AGE_YEARS",
    "DAILY_DOSE",
    "DURATION_DAYS",
}
_TEXT_CONDITION_KINDS = {
    "PREGNANCY_STATUS",
    "DOSAGE_FORM",
    "ADMINISTRATION_ROUTE",
    "EXCIPIENT_PRESENT",
}


@dataclass(frozen=True)
class MedicationSafetyApprovalIssue:
    rule_key: str
    code: str


@dataclass(frozen=True)
class MedicationSafetyApprovalReport:
    dataset_version: str
    rule_count: int
    valid_count: int
    invalid_count: int
    issue_counts: dict[str, int]


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _condition_issues(condition: object) -> list[str]:
    condition_kind = _enum_value(getattr(condition, "condition_kind", ""))
    if condition_kind in _NUMERIC_CONDITION_KINDS:
        issues = []
        if getattr(condition, "value_min", None) is None:
            issues.append("MISSING_CONDITION_VALUE")
        if not _has_text(getattr(condition, "unit", None)):
            issues.append("MISSING_CONDITION_UNIT")
        if (
            _enum_value(getattr(condition, "comparison_operator", "")) == "BETWEEN"
            and getattr(condition, "value_max", None) is None
        ):
            issues.append("MISSING_CONDITION_MAX_VALUE")
        return issues
    if condition_kind in _TEXT_CONDITION_KINDS:
        return [] if _has_text(getattr(condition, "value_text", None)) else ["MISSING_CONDITION_TEXT"]
    return ["UNSUPPORTED_CONDITION_KIND"]


def _source_is_valid(source: object) -> bool:
    return all(
        _has_text(getattr(source, field_name, None))
        for field_name in ("source_id", "document_id", "record_id", "raw_effect_text")
    )


def validate_rule_for_approval(
    rule: object,
    conditions: Iterable[object],
    sources: Iterable[object],
    *,
    dataset_version: str,
) -> list[str]:
    issues: list[str] = []
    rule_key = str(getattr(rule, "rule_key", ""))
    if _SHA256_PATTERN.fullmatch(rule_key) is None:
        issues.append("INVALID_RULE_KEY")
    if getattr(rule, "rule_dataset_version", None) != dataset_version:
        issues.append("DATASET_VERSION_MISMATCH")
    if getattr(rule, "interaction_entity_id", None) is None:
        issues.append("MISSING_INTERACTION_ENTITY")

    condition_list = list(conditions)
    if not condition_list:
        issues.append("MISSING_CONDITION")
    for condition in condition_list:
        issues.extend(_condition_issues(condition))

    source_list = list(sources)
    if not source_list:
        issues.append("MISSING_SOURCE")
    elif any(not _source_is_valid(source) for source in source_list):
        issues.append("INVALID_SOURCE")

    if (
        _enum_value(getattr(rule, "review_status", "")) == "APPROVED"
        and getattr(rule, "approved_at", None) is None
    ):
        issues.append("APPROVED_AT_REQUIRED")
    return list(dict.fromkeys(issues))


def build_approval_report(
    rules_with_relations: Iterable[tuple[object, Iterable[object], Iterable[object]]],
    *,
    dataset_version: str,
) -> tuple[MedicationSafetyApprovalReport, list[MedicationSafetyApprovalIssue]]:
    rows = list(rules_with_relations)
    issues = [
        MedicationSafetyApprovalIssue(
            rule_key=str(getattr(rule, "rule_key", "")),
            code=code,
        )
        for rule, conditions, sources in rows
        for code in validate_rule_for_approval(
            rule,
            conditions,
            sources,
            dataset_version=dataset_version,
        )
    ]
    invalid_keys = {issue.rule_key for issue in issues}
    issue_counts = dict(sorted(Counter(issue.code for issue in issues).items()))
    return (
        MedicationSafetyApprovalReport(
            dataset_version=dataset_version,
            rule_count=len(rows),
            valid_count=len(rows) - len(invalid_keys),
            invalid_count=len(invalid_keys),
            issue_counts=issue_counts,
        ),
        issues,
    )
