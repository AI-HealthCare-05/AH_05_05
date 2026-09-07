from __future__ import annotations

import importlib
import importlib.util
import json

import pytest


def _module():
    path = "scripts.benchmark_ocr_semantic_review"
    assert importlib.util.find_spec(path) is not None, "same-OCR semantic benchmark is missing"
    return importlib.import_module(path)


def test_recovered_answers_and_newly_wrong_answers_are_counted_separately():
    module = _module()
    truth = [
        {
            "name": "감마정",
            "nameAssessable": True,
            "strength": "100mg",
            "doseQuantity": "1",
            "timesPerDay": 2,
            "days": 5,
        }
    ]
    statuses = [{field: "value" for field in module.FIELDS}]
    before = module.field_outcomes(
        truth, [{"name": "감마정", "doseQuantity": "1", "timesPerDay": 2, "days": 5}], statuses
    )
    after = module.field_outcomes(
        truth, [{"name": "감마정", "strength": "100mg", "doseQuantity": "2", "timesPerDay": 2, "days": 5}], statuses
    )
    comparison = module.compare_outcomes(before, after)
    assert comparison["restored"] == ["row-0001:strength"]
    assert comparison["harmed"] == ["row-0001:doseQuantity"]
    assert comparison["newFalsePositives"] == ["row-0001:doseQuantity"]


def test_unreadable_fields_are_not_scored_as_accuracy_gains_but_absent_claims_are_errors():
    module = _module()
    truth = [
        {
            "name": "감마정",
            "nameAssessable": True,
            "strength": None,
            "doseQuantity": "1",
            "timesPerDay": 2,
            "days": None,
        }
    ]
    statuses = [
        {"name": "value", "strength": "absent", "doseQuantity": "value", "timesPerDay": "value", "days": "unreadable"}
    ]
    base = {"name": "감마정", "doseQuantity": "1", "timesPerDay": 2}
    before = module.field_outcomes(truth, [base], statuses)
    after = module.field_outcomes(truth, [{**base, "strength": "10mg", "days": 5}], statuses)
    comparison = module.compare_outcomes(before, after)
    assert before["row-0001:strength"] == "absent"
    assert comparison["restored"] == []
    assert comparison["harmed"] == []
    assert comparison["newFalsePositives"] == ["row-0001:strength"]
    assert "row-0001:days" not in after


@pytest.mark.asyncio
async def test_interrupted_batch_reuses_only_completed_checkpoint_units(tmp_path):
    module = _module()
    calls = []
    entries = [{"id": "sample-01", "sha256": "one"}, {"id": "sample-02", "sha256": "two"}]

    async def interrupted(entry):
        calls.append(entry["id"])
        if entry["id"] == "sample-02":
            raise RuntimeError("interruption")
        return {"id": entry["id"], "sourceSha256": entry["sha256"], "complete": True}

    with pytest.raises(RuntimeError, match="interruption"):
        await module.run_cached_cases(entries, tmp_path, "fixed", interrupted)
    assert calls == ["sample-01", "sample-02"]
    assert (tmp_path / "sample-01.json").exists()
    assert not (tmp_path / "sample-02.json").exists()
    calls.clear()

    async def resumed(entry):
        calls.append(entry["id"])
        return {"id": entry["id"], "sourceSha256": entry["sha256"], "complete": True}

    result = await module.run_cached_cases(entries, tmp_path, "fixed", resumed)
    assert calls == ["sample-02"]
    assert [case["id"] for case in result] == ["sample-01", "sample-02"]
    calls.clear()
    assert await module.run_cached_cases(entries, tmp_path, "fixed", resumed, resume_only=True) == result
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["corrupt", "stale", "wrong-sample"])
async def test_resume_rejects_untrusted_checkpoints_without_external_calls(tmp_path, kind):
    module = _module()
    entry = {"id": "sample-01", "sha256": "source"}
    path = tmp_path / "sample-01.json"
    payload = {
        "identity": "stale" if kind == "stale" else "fixed",
        "id": "other" if kind == "wrong-sample" else "sample-01",
        "sourceSha256": "source",
        "complete": True,
    }
    module.save_checkpoint(path, payload)
    if kind == "corrupt":
        raw = json.loads(path.read_text())
        raw["payload"]["sourceSha256"] = "tampered"
        path.write_text(json.dumps(raw))

    async def forbidden(_entry):
        pytest.fail("resume must not make a new provider call")

    with pytest.raises(ValueError):
        await module.run_cached_cases([entry], tmp_path, "fixed", forbidden, resume_only=True)


def test_summary_keeps_live_service_and_same_ocr_replay_metrics_separate():
    module = _module()
    truth = [
        {
            "name": "감마정",
            "nameAssessable": True,
            "strength": "100mg",
            "doseQuantity": "1",
            "timesPerDay": 2,
            "days": 5,
        }
    ]
    statuses = [{field: "value" for field in module.FIELDS}]
    result = module._score_review({"medications": [dict(truth[0])]}, truth, statuses)
    run = {"postOcrMs": 12.5, "original": result, "corrected": result}
    unchanged = module.compare_outcomes(result["outcomes"], result["outcomes"])
    case = {
        "id": "sample-01",
        "recapture": False,
        "serviceNoLlmMs": 90.0,
        "arms": {
            "noLLM": [run],
            "legacy": [{**run, "comparisonVsNoLlmOriginal": unchanged, "comparisonVsNoLlmCorrected": unchanged}],
            "semantic": [
                {
                    **run,
                    "comparisonVsNoLlmOriginal": unchanged,
                    "comparisonVsNoLlmCorrected": unchanged,
                    "comparisonVsLegacyOriginal": unchanged,
                    "comparisonVsLegacyCorrected": unchanged,
                }
            ],
        },
        "llmCalls": {"legacy": [], "semantic": []},
    }

    summary = module.summarize([case], repeats=1)

    assert summary["serviceNoLlm"]["oneLiveServiceCallPerCase"] is True
    assert summary["serviceNoLlm"]["serviceMs"]["median"] == 90.0
    assert summary["postOcrReplay"]["arms"]["semantic"]["repeats"][0]["corrected"]["falsePositives"] == 0
    assert (
        summary["postOcrReplay"]["arms"]["semantic"]["repeats"][0]["comparisonVsLegacy"]["corrected"]["restored"][
            "count"
        ]
        == 0
    )

