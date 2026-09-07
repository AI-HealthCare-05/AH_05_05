from __future__ import annotations

import json

import pytest

from scripts import benchmark_ocr_llm_baseline as subject


def _score(correct: int, total: int) -> dict:
    return {
        "legacyCorrect": correct,
        "legacyTotal": total,
        "predictedRows": 1,
        "fieldCounts": {"strength": {"tp": correct, "fp": 0, "fn": total - correct}},
    }


def test_summary_keeps_call_latency_separate_from_per_document_cost() -> None:
    active = {
        "id": "sample-01",
        "recapture": False,
        "serviceMs": 1400,
        "stages": [{"name": "llm", "elapsedMs": 1000, "callCount": 1}],
        "controlMs": [10, 12, 14],
        "llmCalls": [{"elapsedMs": ms, "status": "succeeded"} for ms in [1000, 2000, 3000]],
        "controlScore": _score(1, 2),
        "llmScores": [_score(2, 2)] * 3,
    }
    recapture = {
        **active,
        "id": "sample-02",
        "recapture": True,
        "serviceMs": 100,
        "stages": [{"name": "llm", "elapsedMs": 0, "callCount": 0}],
        "controlMs": [],
        "llmCalls": [],
        "controlScore": _score(0, 2),
        "llmScores": [_score(0, 2)] * 3,
    }
    result = subject.summarize([active, recapture])
    assert result["llmCallLatencyMs"]["mean"] == 2000
    assert result["llmStageMsPerInput"] == 500
    assert result["llmInvokedDocuments"] == 1
    assert result["serviceLatencyMs"]["mean"] == 750
    assert result["controlPostOcrMs"]["mean"] == 12
    assert result["accuracy"]["control"]["correct"] == 1
    assert result["accuracy"]["llmFirstRun"]["correct"] == 2
    assert result["accuracy"]["llmFirstRun"]["total"] == 4


def test_safe_score_has_no_raw_review_or_document_fields() -> None:
    expected = [
        {
            "name": "테스트정",
            "nameAssessable": True,
            "strength": "10mg",
            "doseQuantity": "1",
            "timesPerDay": 2,
            "days": 3,
        }
    ]
    review = {"fields": {"private": "do-not-save"}, "medications": [expected[0]]}
    result = subject.safe_score(review, expected, [{key: "value" for key in subject.FIELDS}])
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["legacyCorrect"] == 5
    assert "테스트정" not in encoded
    assert "do-not-save" not in encoded


def test_checkpoint_validation_rejects_wrong_sample(tmp_path) -> None:
    from scripts.benchmark_ocr_postprocess import save_checkpoint

    path = tmp_path / "sample-01.json"
    save_checkpoint(path, {"identity": "run", "id": "sample-02", "sourceSha256": "source"})
    with pytest.raises(ValueError, match="sample"):
        subject.load_case(path, "run", {"id": "sample-01", "sha256": "source"})


def test_resume_source_audit_rejects_changed_original(tmp_path) -> None:
    import hashlib

    source = tmp_path / "image.png"
    source.write_bytes(b"original")
    entries = [{"id": "sample-01", "file": "image.png", "sha256": hashlib.sha256(b"original").hexdigest()}]
    subject.validate_sources(entries, tmp_path)
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="source identity"):
        subject.validate_sources(entries, tmp_path)

