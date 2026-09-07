from __future__ import annotations

import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

MEDICATION_FIELDS = ("name", "strength", "doseQuantity", "timesPerDay", "days")
DOCUMENT_FIELDS = ("dispensedDate", "hospitalName")


def _value(value: object) -> object:
    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    return value


def _present(value: object) -> bool:
    return value is not None and value != ""


def score_review(review: Mapping[str, Any], ground_truth: Mapping[str, Any]) -> dict[str, object]:
    actual_fields = review.get("fields") if isinstance(review.get("fields"), Mapping) else {}
    expected_fields = ground_truth.get("fields") if isinstance(ground_truth.get("fields"), Mapping) else {}
    actual_medications = review.get("medications") if isinstance(review.get("medications"), list) else []
    expected_medications = ground_truth.get("medications") if isinstance(ground_truth.get("medications"), list) else []

    expected_count = extracted_count = correct_count = 0
    field_counts: dict[str, dict[str, int]] = {
        field: {"expected": 0, "extracted": 0, "correct": 0} for field in (*DOCUMENT_FIELDS, *MEDICATION_FIELDS)
    }

    def compare(field: str, actual: object, expected: object) -> bool:
        nonlocal expected_count, extracted_count, correct_count
        expected_count += 1
        field_counts[field]["expected"] += 1
        if _present(actual):
            extracted_count += 1
            field_counts[field]["extracted"] += 1
        matched = actual == expected
        if matched:
            correct_count += 1
            field_counts[field]["correct"] += 1
        return matched

    document_matches = []
    for field in DOCUMENT_FIELDS:
        if field in expected_fields:
            document_matches.append(compare(field, _value(actual_fields.get(field)), expected_fields[field]))

    full_rows = 0
    for index, expected_row in enumerate(expected_medications):
        actual_row = actual_medications[index] if index < len(actual_medications) else {}
        if not isinstance(actual_row, Mapping):
            actual_row = {}
        row_matches = [
            compare(field, _value(actual_row.get(field)), expected_row[field])
            for field in MEDICATION_FIELDS
            if field in expected_row
        ]
        if row_matches and all(row_matches):
            full_rows += 1

    expected_names = [row.get("name") for row in expected_medications]
    actual_names = [row.get("name") for row in actual_medications if isinstance(row, Mapping)]
    per_field = {
        field: {
            **counts,
            "extractionRate": counts["extracted"] / counts["expected"] if counts["expected"] else 1.0,
            "accuracy": counts["correct"] / counts["expected"] if counts["expected"] else 1.0,
        }
        for field, counts in field_counts.items()
    }
    return {
        "expectedFieldCount": expected_count,
        "extractedFieldCount": extracted_count,
        "correctFieldCount": correct_count,
        "expectedMedicationRowCount": len(expected_medications),
        "fullRowExactCount": full_rows,
        "fieldExtractionRate": extracted_count / expected_count if expected_count else 1.0,
        "exactFieldAccuracy": correct_count / expected_count if expected_count else 1.0,
        "fullRowExactRate": full_rows / len(expected_medications) if expected_medications else 1.0,
        "medicationOrderExact": actual_names == expected_names,
        "documentFieldsExact": all(document_matches),
        "perField": per_field,
    }


def summarize_runs(
    reviews: Sequence[Mapping[str, Any]],
    ground_truth: Mapping[str, Any],
) -> dict[str, object]:
    if not reviews:
        raise ValueError("At least one OCR review is required.")
    scores = [score_review(review, ground_truth) for review in reviews]
    serialized = [json.dumps(review, ensure_ascii=False, sort_keys=True) for review in reviews]
    medication_counts = [
        len(review.get("medications", [])) if isinstance(review.get("medications"), list) else 0 for review in reviews
    ]
    mean_keys = ("fieldExtractionRate", "exactFieldAccuracy", "fullRowExactRate")
    aggregate_score = {key: sum(float(score[key]) for score in scores) / len(scores) for key in mean_keys}
    return {
        "runs": len(reviews),
        "exactResultStabilityRate": max(Counter(serialized).values()) / len(serialized),
        "medicationCountRange": [min(medication_counts), max(medication_counts)],
        "score": aggregate_score,
        "perRunScores": scores,
    }


def main() -> int:
    root_value = os.environ.get("OCR_V32_QUALITY_ROOT")
    truth_value = os.environ.get("OCR_V32_GROUND_TRUTH")
    if not root_value or not truth_value:
        print("OCR_V32_QUALITY_ROOT and OCR_V32_GROUND_TRUTH are required.", file=sys.stderr)
        return 2
    root = Path(root_value)
    ground_truth = json.loads(Path(truth_value).read_text(encoding="utf-8"))
    summaries: dict[str, object] = {}
    for candidate_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        reviews = []
        for run_path in sorted(candidate_dir.glob("run-*.json")):
            payload = json.loads(run_path.read_text(encoding="utf-8"))
            reviews.append(payload["projectReview"])
        if reviews:
            summaries[candidate_dir.name] = summarize_runs(reviews, ground_truth)
    output = {"groundTruthVersion": "ref002/v1", "candidates": summaries}
    (root / "quality-summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

