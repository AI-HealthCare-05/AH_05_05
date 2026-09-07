"""Evaluate OCR medication rows without depending on their output order.

The legacy comparable metric intentionally keeps the five-field denominator used
by ``score_ocr16.py``.  The primary confusion metrics additionally distinguish a
source-absent value from one that a reviewer could not read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any

FIELDS = ("name", "strength", "doseQuantity", "timesPerDay", "days")
REGIMEN_FIELDS = ("doseQuantity", "timesPerDay", "days")
SOURCE_STATUSES = ("value", "absent", "unreadable")
MAX_ROWS = 10
SCHEMA_VERSION = "ocr-v3.4-evaluation/v1"


def name_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    for old, new in (
        ("밀리그램", "mg"),
        ("마이크로그램", "ug"),
        ("밀리리터", "ml"),
        ("그램", "g"),
        ("퍼센트", "%"),
    ):
        text = text.replace(old, new)
    text = re.sub(
        r"\(([^)]*)\)",
        lambda match: match[1] if re.fullmatch(r"[\d\s./%a-z+-]+", match[1]) else "",
        text,
    )
    return re.sub(r"[\s_(),\[\]]", "", text)


def number_key(value: object) -> Decimal | None:
    if value is None:
        return None
    text = re.sub(r"\s*(정|캡슐|포|ml|mL)$", "", str(value).strip())
    try:
        result = Decimal(text)
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def strength_key(value: object) -> object:
    text = re.sub(r"/(?:1)?(?:정|캡슐|포)$", "", name_key(value))
    match = re.fullmatch(r"(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)*)\s*(mg|ug|g|ml|%)", text)
    if not match:
        return text
    values, unit = match.groups()
    factor = {"g": Decimal(1000), "mg": Decimal(1), "ug": Decimal("0.001")}.get(unit, Decimal(1))
    normalized_unit = "mg" if unit in {"g", "mg", "ug"} else unit
    return normalized_unit, tuple(Decimal(value) * factor for value in values.split("/"))


def _claimed(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _normalized(field: str, value: object) -> object:
    if field == "name":
        return name_key(value)
    if field == "strength":
        return strength_key(value)
    return number_key(value)


def _equal(field: str, expected: object, actual: object) -> bool:
    if not _claimed(actual):
        return False
    expected_key = _normalized(field, expected)
    actual_key = _normalized(field, actual)
    return expected_key is not None and actual_key is not None and expected_key == actual_key


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _with_rates(counts: Mapping[str, int]) -> dict[str, int | float | None]:
    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {**counts, "precision": precision, "recall": recall, "f1": f1}


def _legacy_assessable(row: Mapping[str, Any], field: str) -> bool:
    return row.get(field) is not None and (field != "name" or bool(row.get("nameAssessable")))


def _index_status_samples(status_samples: object) -> dict[str, list[Mapping[str, str]]]:
    if not isinstance(status_samples, list):
        raise ValueError("statuses.samples must be a list")
    indexed_statuses: dict[str, list[Mapping[str, str]]] = {}
    for sample in status_samples:
        if not isinstance(sample, Mapping) or not isinstance(sample.get("id"), str):
            raise ValueError("every status sample needs a string id")
        sample_id = sample["id"]
        if sample_id in indexed_statuses:
            raise ValueError(f"duplicate status sample: {sample_id}")
        rows = sample.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"status rows must be a list: {sample_id}")
        indexed_statuses[sample_id] = rows
    return indexed_statuses


def _validate_status_field(
    sample_id: str,
    row_index: int,
    field: str,
    row: Mapping[str, Any],
    source_status: object,
) -> None:
    location = f"{sample_id} row {row_index} {field}"
    if source_status not in SOURCE_STATUSES:
        raise ValueError(f"invalid source status: {location}")
    if source_status == "value" and row[field] is None:
        raise ValueError(f"value status requires frozen truth: {location}")
    if source_status == "absent" and row[field] is not None:
        raise ValueError(f"absent status conflicts with frozen truth: {location}")
    if field == "name" and source_status == "value" and not row.get("nameAssessable"):
        raise ValueError(f"unassessable name cannot have value status: {location}")


def _validate_sample_rows(sample: Mapping[str, Any], status_rows: list[Mapping[str, str]]) -> None:
    sample_id = sample["id"]
    rows = sample.get("rows")
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS:
        raise ValueError(f"truth rows must contain 1..{MAX_ROWS} rows: {sample_id}")
    if len(status_rows) != len(rows):
        raise ValueError(f"status row count does not match truth: {sample_id}")
    for row_index, (row, status_row) in enumerate(zip(rows, status_rows, strict=True), start=1):
        if not isinstance(row, Mapping) or any(field not in row for field in FIELDS):
            raise ValueError(f"truth row is missing a five-field value: {sample_id} row {row_index}")
        if not isinstance(status_row, Mapping) or set(status_row) != set(FIELDS):
            raise ValueError(f"status row must contain exactly the five fields: {sample_id} row {row_index}")
        for field in FIELDS:
            _validate_status_field(sample_id, row_index, field, row, status_row[field])


def _validate_truth_and_statuses(
    truth: Mapping[str, Any], statuses: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], dict[str, list[Mapping[str, str]]]]:
    truth_samples = truth.get("samples")
    if not isinstance(truth_samples, list) or not truth_samples:
        raise ValueError("truth.samples must be a non-empty list")
    truth_ids = [sample.get("id") for sample in truth_samples if isinstance(sample, Mapping)]
    if (
        len(truth_ids) != len(truth_samples)
        or not all(isinstance(sample_id, str) for sample_id in truth_ids)
        or len(set(truth_ids)) != len(truth_ids)
    ):
        raise ValueError("truth sample ids must be present and unique")
    indexed_statuses = _index_status_samples(statuses.get("samples"))
    if set(indexed_statuses) != set(truth_ids):
        raise ValueError("status sample ids must exactly match truth sample ids")
    for sample in truth_samples:
        _validate_sample_rows(sample, indexed_statuses[sample["id"]])
    return truth_samples, indexed_statuses


def _prediction_rows(run: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    review = run.get("review")
    medications = review.get("medications") if isinstance(review, Mapping) else None
    if not isinstance(medications, list) or len(medications) > MAX_ROWS:
        raise ValueError(f"predicted medications must be a list of at most {MAX_ROWS} rows")
    if not all(isinstance(row, Mapping) for row in medications):
        raise ValueError("every predicted medication row must be an object")
    return medications


def _pair_features(
    gold: Mapping[str, Any], predicted: Mapping[str, Any], statuses: Mapping[str, str]
) -> tuple[bool, tuple[int, ...], bool]:
    exact = {field: statuses[field] == "value" and _equal(field, gold[field], predicted.get(field)) for field in FIELDS}
    name_hit = int(exact["name"])
    strength_hit = int(exact["strength"])
    regimen_hits = sum(int(exact[field]) for field in REGIMEN_FIELDS)
    absent_claims = tuple(-int(statuses[field] == "absent" and _claimed(predicted.get(field))) for field in FIELDS)
    unreadable_claims = tuple(
        -int(statuses[field] == "unreadable" and _claimed(predicted.get(field))) for field in FIELDS
    )
    legacy_fields = [field for field in FIELDS if _legacy_assessable(gold, field)]
    legacy_hits = sum(_equal(field, gold[field], predicted.get(field)) for field in legacy_fields)
    legacy_full_exact = int(len(legacy_fields) == len(FIELDS) and legacy_hits == len(FIELDS))
    assessable = any(statuses[field] != "unreadable" for field in FIELDS)
    strict_exact = assessable and all(
        exact[field]
        if statuses[field] == "value"
        else not _claimed(predicted.get(field))
        if statuses[field] == "absent"
        else True
        for field in FIELDS
    )
    admissible = bool(name_hit or strength_hit or regimen_hits >= 2)
    features = (
        name_hit,
        strength_hit,
        sum(exact.values()),
        *(int(exact[field]) for field in FIELDS),
        legacy_hits,
        int(strict_exact),
        legacy_full_exact,
        *absent_claims,
        *unreadable_claims,
        1,
    )
    return admissible, features, strict_exact


def match_rows(
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, str]],
) -> tuple[int | None, ...]:
    """Return one prediction index per truth row using a bounded, one-to-one DP."""

    if len(expected) != len(statuses):
        raise ValueError("matching requires one status row per truth row")
    if len(expected) > MAX_ROWS or len(predicted) > MAX_ROWS:
        raise ValueError(f"matching supports at most {MAX_ROWS} rows per side")
    pair = [
        [_pair_features(gold, actual, status) for actual in predicted]
        for gold, status in zip(expected, statuses, strict=True)
    ]
    empty_status = {field: "unreadable" for field in FIELDS}
    feature_width = len(_pair_features({}, {}, empty_status)[1])
    zero_score = (0,) * (feature_width + 1)

    @cache
    def solve(gold_index: int, used_mask: int) -> tuple[tuple[int, ...], tuple[int | None, ...]]:
        if gold_index == len(expected):
            return zero_score, ()
        tail_score, tail_mapping = solve(gold_index + 1, used_mask)
        best = (tail_score, (None, *tail_mapping))
        for predicted_index in range(len(predicted)):
            if used_mask & (1 << predicted_index) or not pair[gold_index][predicted_index][0]:
                continue
            candidate_tail, candidate_mapping = solve(gold_index + 1, used_mask | (1 << predicted_index))
            features = pair[gold_index][predicted_index][1]
            order_tie = -abs(gold_index - predicted_index)
            candidate_score = tuple(a + b for a, b in zip((*features, order_tie), candidate_tail, strict=True))
            candidate = (candidate_score, (predicted_index, *candidate_mapping))
            if candidate_score > best[0]:
                best = candidate
        return best

    return solve(0, 0)[1]


def _empty_field_counts() -> dict[str, int]:
    return {"tp": 0, "fp": 0, "fn": 0, "unreadableClaims": 0, "unreadableAbstentions": 0, "absentCorrect": 0}


def _score_field(
    field: str,
    gold: Mapping[str, Any],
    actual: Mapping[str, Any],
    source_status: str,
    counts: dict[str, int],
    row_strict: bool,
    matched: bool,
) -> bool:
    claimed = _claimed(actual.get(field))
    if source_status == "value":
        if _equal(field, gold[field], actual.get(field)):
            counts["tp"] += 1
            return row_strict
        counts["fn"] += 1
        counts["fp"] += int(claimed)
        return False
    if source_status == "absent":
        if claimed:
            counts["fp"] += 1
            return False
        counts["absentCorrect"] += int(matched)
        return row_strict
    counts["unreadableClaims" if claimed else "unreadableAbstentions"] += 1
    return row_strict


def _score_matched_row(
    gold: Mapping[str, Any],
    actual: Mapping[str, Any],
    status_row: Mapping[str, str],
    by_field: Mapping[str, dict[str, int]],
    matched: bool,
) -> tuple[int, int, int, bool, bool]:
    legacy_fields = [field for field in FIELDS if _legacy_assessable(gold, field)]
    legacy_correct = sum(_equal(field, gold[field], actual.get(field)) for field in legacy_fields)
    full_five_correct = int(len(legacy_fields) == len(FIELDS) and legacy_correct == len(FIELDS))
    assessable = any(status_row[field] != "unreadable" for field in FIELDS)
    row_strict = matched and assessable
    for field in FIELDS:
        row_strict = _score_field(field, gold, actual, status_row[field], by_field[field], row_strict, matched)
    return legacy_correct, len(legacy_fields), full_five_correct, assessable, row_strict


def score_sample(
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    mapping = match_rows(expected, predicted, statuses)
    matched_predictions = {index for index in mapping if index is not None}
    by_field = {field: _empty_field_counts() for field in FIELDS}
    legacy_correct = legacy_total = 0
    full_five_correct = full_five_total = 0
    strict_exact = 0
    strict_assessable = 0

    for gold, status_row, predicted_index in zip(expected, statuses, mapping, strict=True):
        actual = {} if predicted_index is None else predicted[predicted_index]
        row_score = _score_matched_row(
            gold,
            actual,
            status_row,
            by_field,
            predicted_index is not None,
        )
        row_legacy_correct, row_legacy_total, row_full_five_correct, assessable, row_strict = row_score
        legacy_correct += row_legacy_correct
        legacy_total += row_legacy_total
        if row_legacy_total == len(FIELDS):
            full_five_total += 1
            full_five_correct += row_full_five_correct
        strict_assessable += int(assessable)
        strict_exact += int(row_strict)

    for predicted_index, actual in enumerate(predicted):
        if predicted_index in matched_predictions:
            continue
        for field in FIELDS:
            by_field[field]["fp"] += int(_claimed(actual.get(field)))

    micro = {key: sum(field_counts[key] for field_counts in by_field.values()) for key in _empty_field_counts()}
    status_support = {
        source_status: sum(status_row[field] == source_status for status_row in statuses for field in FIELDS)
        for source_status in SOURCE_STATUSES
    }
    row_counts = {"tp": strict_exact, "fp": len(predicted) - strict_exact, "fn": len(expected) - strict_exact}
    document_success = int(
        len(predicted) == len(expected) and strict_exact == len(expected) and micro["fp"] == 0 and micro["fn"] == 0
    )
    return {
        "expectedRows": len(expected),
        "predictedRows": len(predicted),
        "mapping": [None if index is None else index + 1 for index in mapping],
        "legacyCorrect": legacy_correct,
        "legacyTotal": legacy_total,
        "fullFiveLegacyExact": full_five_correct,
        "fullFiveLegacyAssessable": full_five_total,
        "strictExact": strict_exact,
        "strictAssessable": strict_assessable,
        "fieldCounts": by_field,
        "sourceStatusSupport": status_support,
        "rowCounts": row_counts,
        "documentSuccess": document_success,
    }


def _timing_summary(
    runs: Sequence[Mapping[str, Any]],
    timings: Mapping[str, Any] | None,
    sample_ids: set[str],
    version: str,
    variant: str,
) -> dict[str, int | float | None]:
    selected = [
        run for run in runs if run["id"] in sample_ids and run["version"] == version and _variant(run) == variant
    ]
    wall = [float(run["wallMs"]) for run in selected if isinstance(run.get("wallMs"), (int, float))]
    ocr_stages = [
        stage
        for run in selected
        for stage in run.get("stages", [])
        if isinstance(stage, Mapping) and stage.get("name") == "ocr"
    ]
    result: dict[str, int | float | None] = {
        "wallMeanMs": statistics.mean(wall) if wall else None,
        "wallMedianMs": statistics.median(wall) if wall else None,
        "ocrCalls": sum(int(stage.get("callCount", 0)) for stage in ocr_stages),
        "llmCalls": sum(
            int(stage.get("callCount", 0))
            for run in selected
            for stage in run.get("stages", [])
            if isinstance(stage, Mapping) and stage.get("name") == "llm"
        ),
    }
    called = [float(stage["elapsedMs"]) for stage in ocr_stages if stage.get("callCount") and "elapsedMs" in stage]
    result["ocrMeanCalledMs"] = statistics.mean(called) if called else None
    local_runs = timings.get("runs") if isinstance(timings, Mapping) else None
    local_medians = []
    if isinstance(local_runs, list):
        for item in local_runs:
            if not isinstance(item, Mapping) or item.get("id") not in sample_ids or _variant(item) != variant:
                continue
            timing_map = item.get("timesMs", item.get("times"))
            values = timing_map.get(version) if isinstance(timing_map, Mapping) else None
            if isinstance(values, list) and values:
                local_medians.append(statistics.median(float(value) for value in values))
    result["preprocessMeanOfMediansMs"] = statistics.mean(local_medians) if local_medians else None
    return result


def _summarize(
    details: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    sample_ids: Sequence[str],
    document_groups: Mapping[str, str],
    timings: Mapping[str, Any] | None,
    variant: str,
) -> list[dict[str, Any]]:
    selected_ids = set(sample_ids)
    versions = sorted(
        {str(detail["version"]) for detail in details if detail["id"] in selected_ids and detail["variant"] == variant}
    )
    summaries = []
    for version in versions:
        selected = [
            detail
            for detail in details
            if detail["id"] in selected_ids and detail["version"] == version and detail["variant"] == variant
        ]
        if not selected:
            continue
        per_field: dict[str, dict[str, int | float | None]] = {}
        for field in FIELDS:
            counts = {
                key: sum(detail["score"]["fieldCounts"][field][key] for detail in selected)
                for key in _empty_field_counts()
            }
            per_field[field] = _with_rates(counts)
        micro_counts = {
            key: sum(detail["score"]["fieldCounts"][field][key] for detail in selected for field in FIELDS)
            for key in _empty_field_counts()
        }
        row_counts = {key: sum(detail["score"]["rowCounts"][key] for detail in selected) for key in ("tp", "fp", "fn")}
        document_success = {detail["id"]: detail["score"]["documentSuccess"] for detail in selected}
        grouped: dict[str, list[int]] = {}
        for sample_id, success in document_success.items():
            grouped.setdefault(document_groups[sample_id], []).append(success)
        group_means = [statistics.mean(values) for values in grouped.values()]
        legacy_correct = sum(detail["score"]["legacyCorrect"] for detail in selected)
        legacy_total = sum(detail["score"]["legacyTotal"] for detail in selected)
        strict_exact = sum(detail["score"]["strictExact"] for detail in selected)
        strict_assessable = sum(detail["score"]["strictAssessable"] for detail in selected)
        status_support = {
            source_status: sum(detail["score"]["sourceStatusSupport"][source_status] for detail in selected)
            for source_status in SOURCE_STATUSES
        }
        summaries.append(
            {
                "version": version,
                "images": len(selected),
                "legacyComparable": {
                    "correct": legacy_correct,
                    "total": legacy_total,
                    "accuracy": _ratio(legacy_correct, legacy_total),
                },
                "sourceStatusSupport": status_support,
                "fields": {"micro": _with_rates(micro_counts), "byField": per_field},
                "rows": {
                    **_with_rates(row_counts),
                    "exact": strict_exact,
                    "strictAssessable": strict_assessable,
                    "strictExactRate": _ratio(strict_exact, strict_assessable),
                    "fullFiveLegacyExact": sum(detail["score"]["fullFiveLegacyExact"] for detail in selected),
                    "fullFiveLegacyAssessable": sum(detail["score"]["fullFiveLegacyAssessable"] for detail in selected),
                },
                "documents": {
                    "success": sum(document_success.values()),
                    "total": len(document_success),
                    "successRate": _ratio(sum(document_success.values()), len(document_success)),
                    "groupCount": len(grouped),
                    "groupMacroSuccessRate": statistics.mean(group_means) if group_means else None,
                },
                "timing": _timing_summary(runs, timings, selected_ids, version, variant),
            }
        )
    return summaries


def _variant(run: Mapping[str, Any]) -> str:
    value = run.get("variant", "default")
    if not isinstance(value, str) or not value:
        raise ValueError("run variant must be a non-empty string")
    return value


def _unwrap_runs(
    results: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> tuple[object, Sequence[Mapping[str, Any]]]:
    if isinstance(results, Mapping):
        return results.get("identity"), results.get("runs", [])
    return None, results


def _validate_runs(
    runs: Sequence[Mapping[str, Any]],
    truth_by_id: Mapping[str, Mapping[str, Any]],
    identity: object,
) -> list[Mapping[str, Any]]:
    if not isinstance(runs, Sequence) or not runs:
        raise ValueError("runs must be a non-empty sequence")
    seen: set[tuple[str, str, str]] = set()
    normalized = []
    for run in runs:
        if not isinstance(run, Mapping) or run.get("id") not in truth_by_id or not isinstance(run.get("version"), str):
            raise ValueError("each run needs a known id and string version")
        variant = _variant(run)
        key = (str(run["id"]), str(run["version"]), variant)
        if key in seen:
            raise ValueError(f"duplicate run: {key[0]} {key[1]} {key[2]}")
        if identity is not None and run.get("identity", identity) != identity:
            raise ValueError(f"run identity does not match result identity: {key[0]} {key[1]} {key[2]}")
        seen.add(key)
        _prediction_rows(run)
        normalized.append(run)
    expected_ids = set(truth_by_id)
    variant_versions = {(_variant(run), run["version"]) for run in normalized}
    for variant, version in variant_versions:
        version_ids = {run["id"] for run in normalized if run["version"] == version and _variant(run) == variant}
        if version_ids != expected_ids:
            raise ValueError(f"variant/version does not cover every truth sample: {variant} {version}")
    return normalized


def _resolve_document_groups(
    sample_ids: Sequence[str],
    statuses: Mapping[str, Any],
    document_groups: Mapping[str, str] | None,
) -> dict[str, str]:
    groups = {sample_id: sample_id for sample_id in sample_ids}
    if "sample-08" in groups and "sample-11" in groups:
        groups["sample-08"] = groups["sample-11"] = "same-document-08-11"
    status_samples = statuses.get("samples")
    if isinstance(status_samples, list):
        for sample in status_samples:
            if not isinstance(sample, Mapping) or sample.get("id") not in groups:
                continue
            group = sample.get("documentGroup", sample.get("sourceGroup"))
            if isinstance(group, str) and group:
                groups[sample["id"]] = group
    status_groups = statuses.get("documentGroups")
    if isinstance(status_groups, Mapping):
        groups.update({str(key): str(value) for key, value in status_groups.items() if key in groups})
    if document_groups is not None:
        if set(document_groups) != set(sample_ids):
            raise ValueError("document_groups must cover every sample id")
        groups.update(document_groups)
    return groups


def evaluate_runs(
    runs: Sequence[Mapping[str, Any]] | Mapping[str, Any],
    truth: Mapping[str, Any],
    statuses: Mapping[str, Any],
    *,
    timings: Mapping[str, Any] | None = None,
    document_groups: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    truth_samples, indexed_statuses = _validate_truth_and_statuses(truth, statuses)
    truth_by_id = {sample["id"]: sample for sample in truth_samples}
    sample_ids = list(truth_by_id)
    identity, unwrapped_runs = _unwrap_runs(runs)
    normalized_runs = _validate_runs(unwrapped_runs, truth_by_id, identity)
    if identity is not None and isinstance(timings, Mapping) and timings.get("identity", identity) != identity:
        raise ValueError("timings identity does not match result identity")
    groups = _resolve_document_groups(sample_ids, statuses, document_groups)

    details = []
    for run in normalized_runs:
        expected = truth_by_id[run["id"]]["rows"]
        score = score_sample(expected, _prediction_rows(run), indexed_statuses[run["id"]])
        details.append(
            {
                "id": run["id"],
                "version": run["version"],
                "variant": _variant(run),
                "recapture": bool(run.get("recapture")),
                "score": score,
            }
        )
    slices = {
        "all16": sample_ids,
        "original8": sample_ids[:8],
        "additional8": sample_ids[8:],
    }
    variants = {}
    for variant in sorted({_variant(run) for run in normalized_runs}):
        variant_details = [detail for detail in details if detail["variant"] == variant]
        variants[variant] = {
            "summaries": {
                label: _summarize(details, normalized_runs, ids, groups, timings, variant)
                for label, ids in slices.items()
            },
            "details": variant_details,
        }
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "identity": identity,
        "sourceStatusSemantics": {
            "value": "scored as TP, FP, or FN",
            "absent": "a claim is FP; omission is not a scored event",
            "unreadable": "excluded from TP/FP/FN and reported as claim or abstention",
        },
        "documentGroups": groups,
        "variants": variants,
    }
    if len(variants) == 1:
        only_variant = next(iter(variants.values()))
        report.update(only_variant)
    return report


def _load_json_with_sha256(path: Path) -> tuple[Any, str]:
    content = path.read_bytes()
    return json.loads(content), hashlib.sha256(content).hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--statuses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timings", type=Path)
    args = parser.parse_args(argv)
    results, results_sha256 = _load_json_with_sha256(args.results)
    truth, truth_sha256 = _load_json_with_sha256(args.truth)
    statuses, statuses_sha256 = _load_json_with_sha256(args.statuses)
    timings, timings_sha256 = _load_json_with_sha256(args.timings) if args.timings else (None, None)
    report = evaluate_runs(
        results,
        truth,
        statuses,
        timings=timings,
    )
    report["provenance"] = {
        "resultsSha256": results_sha256,
        "truthSha256": truth_sha256,
        "statusesSha256": statuses_sha256,
        "evaluatorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timingsSha256": timings_sha256,
    }
    _atomic_write_json(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
