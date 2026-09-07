from __future__ import annotations

import pytest

from scripts.evaluate_ocr_candidate_quality import score_review, summarize_runs
from scripts.run_ocr_llm_three_image_experiment import _timings, summarize_experiment


def _ground_truth() -> dict[str, object]:
    return {
        "fields": {"dispensedDate": "2025-10-25", "hospitalName": "한도병원"},
        "medications": [
            {
                "name": "약A",
                "strength": "10mg",
                "doseQuantity": 1,
                "timesPerDay": 2,
                "days": 3,
            },
            {
                "name": "약B",
                "strength": "20mg",
                "doseQuantity": 0.5,
                "timesPerDay": 1,
                "days": 5,
            },
        ],
    }


def test_score_review_counts_missing_and_incorrect_fields() -> None:
    review = {
        "fields": {"dispensedDate": {"value": "2025-10-25"}},
        "medications": [
            {
                "name": "약A",
                "strength": "10mg",
                "doseQuantity": 1,
                "timesPerDay": 2,
                "days": 3,
            },
            {
                "name": "약B",
                "doseQuantity": 1,
                "timesPerDay": 1,
                "days": 5,
            },
        ],
    }

    score = score_review(review, _ground_truth())

    assert score["expectedFieldCount"] == 12
    assert score["extractedFieldCount"] == 10
    assert score["correctFieldCount"] == 9
    assert score["expectedMedicationRowCount"] == 2
    assert score["fullRowExactCount"] == 1
    assert score["fieldExtractionRate"] == pytest.approx(10 / 12)
    assert score["exactFieldAccuracy"] == pytest.approx(9 / 12)
    assert score["fullRowExactRate"] == pytest.approx(0.5)
    assert score["medicationOrderExact"] is True
    assert score["documentFieldsExact"] is False


def test_summarize_runs_reports_exact_result_stability() -> None:
    ground_truth = _ground_truth()
    review = {
        "fields": {
            "dispensedDate": {"value": "2025-10-25"},
            "hospitalName": {"value": "한도병원"},
        },
        "medications": ground_truth["medications"],
    }

    summary = summarize_runs([review, review, review], ground_truth)

    assert summary["runs"] == 3
    assert summary["exactResultStabilityRate"] == 1.0
    assert summary["medicationCountRange"] == [2, 2]
    assert summary["score"]["exactFieldAccuracy"] == 1.0


def test_experiment_timings_aggregate_each_run() -> None:
    runs = [
        {
            "stages": [{"name": "preprocess", "elapsedMs": elapsed_ms}],
            "totalPipelineMs": elapsed_ms + 10,
        }
        for elapsed_ms in (100, 200, 300)
    ]

    timing = _timings(runs)

    assert timing["preprocess"]["p50"] == 200
    assert timing["total"]["max"] == 310


def test_experiment_summary_compares_arbitrary_candidates_to_control() -> None:
    ground_truth = {"fields": {}, "medications": [{"name": "약A"}]}
    manifest = {"version": "test/v1", "images": [{"id": "sample", "groundTruth": ground_truth}]}
    candidates = ("v3.1.1", "v3.1.2", "v3.1.3")
    results = []
    for version, name, total_ms in (
        ("v3.1.1", "약A", 100),
        ("v3.1.2", "약B", 80),
        ("v3.1.3", "약A", 70),
    ):
        review = {"fields": {}, "medications": [{"name": name}], "lowConfidenceCount": 0}
        results.append(
            {
                "imageId": "sample",
                "preprocessVersion": version,
                "projectReview": review,
                "stages": [{"name": "preprocess", "elapsedMs": total_ms, "callCount": 0}],
                "totalPipelineMs": total_ms,
                "avgEvidenceConfidence": 0.9,
                "score": score_review(review, ground_truth),
            }
        )

    summary = summarize_experiment(
        manifest,
        results,
        model="test-model",
        candidates=candidates,
        control="v3.1.1",
        experiment_version="test-experiment/v1",
    )

    assert list(summary["candidates"]) == list(candidates)
    assert summary["experimentVersion"] == "test-experiment/v1"
    assert summary["comparisons"]["v3.1.2"]["exactFieldAccuracyDelta"] == -1
    assert summary["comparisons"]["v3.1.3"]["totalP50MsDeltaByImage"]["sample"] == -30

