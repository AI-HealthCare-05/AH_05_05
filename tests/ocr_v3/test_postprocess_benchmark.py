from __future__ import annotations

import json
from copy import deepcopy

import pytest


def test_postprocess_summary_excludes_raw_text_and_preserves_error_counts() -> None:
    from scripts.benchmark_ocr_postprocess import summarize

    cases = [{"id": "sample-01", "ocrMs": 1234, "recapture": False}]
    runs = [
        {
            "id": "sample-01",
            "samplesMs": [8, 10, 12],
            "review": {
                "medications": [
                    {"name": "테스트정", "doseQuantity": "2정", "timesPerDay": 3, "days": 5},
                ]
            },
            "llmRequired": False,
        }
    ]
    truth = {
        "samples": [
            {
                "id": "sample-01",
                "rows": [
                    {
                        "name": "테스트정",
                        "nameAssessable": True,
                        "strength": None,
                        "doseQuantity": "1정",
                        "timesPerDay": 3,
                        "days": 5,
                    },
                ],
            }
        ]
    }
    statuses = {
        "samples": [
            {
                "id": "sample-01",
                "rows": [
                    {
                        "name": "value",
                        "strength": "absent",
                        "doseQuantity": "value",
                        "timesPerDay": "value",
                        "days": "value",
                    },
                ],
            }
        ]
    }
    summary = summarize(cases, runs, truth, statuses)
    assert summary["post_ocr_ms"] == 10
    assert summary["field_accuracy"] == 0.75
    assert summary["correct_fields"] == 3
    assert summary["false_positives"] == 1
    assert "테스트정" not in json.dumps(summary, ensure_ascii=False)
    assert "review" not in summary["cases"][0]


def test_postprocess_checkpoint_rejects_tampered_metrics(tmp_path) -> None:
    from scripts.benchmark_ocr_postprocess import load_checkpoint, save_checkpoint

    path = tmp_path / "result.json"
    save_checkpoint(path, {"identity": "abc", "post_ocr_ms": 10})
    assert load_checkpoint(path, "abc")["post_ocr_ms"] == 10
    with pytest.raises(ValueError, match="identity"):
        load_checkpoint(path, "different")
    value = json.loads(path.read_text())
    value["payload"]["post_ocr_ms"] = 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checksum"):
        load_checkpoint(path, "abc")


def test_adjudication_requires_exact_provenance_and_keeps_original_truth() -> None:
    from scripts.benchmark_ocr_postprocess import apply_adjudications, digest

    truth = {"samples": [{"id": "sample-01", "rows": [{"name": "오기정"}]}]}
    original = deepcopy(truth)
    manifest = {"images": [{"id": "sample-01", "sha256": "source-hash"}]}
    correction = {
        "baseTruthSha256": digest(truth),
        "replacements": [
            {
                "id": "sample-01",
                "sourceSha256": "source-hash",
                "row": 0,
                "field": "name",
                "old": "오기정",
                "new": "원문정",
            }
        ],
    }
    result = apply_adjudications(truth, manifest, correction)
    assert result["samples"][0]["rows"][0]["name"] == "원문정"
    assert truth == original
    for key, bad_value in [("sourceSha256", "stale"), ("old", "different")]:
        tampered = deepcopy(correction)
        tampered["replacements"][0][key] = bad_value
        with pytest.raises(ValueError, match="adjudication"):
            apply_adjudications(truth, manifest, tampered)
    with pytest.raises(ValueError, match="adjudication"):
        apply_adjudications(truth, manifest, {**correction, "baseTruthSha256": "stale"})

