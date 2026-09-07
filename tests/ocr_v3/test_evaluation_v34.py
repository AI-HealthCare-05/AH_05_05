from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import evaluate_ocr_v34 as evaluator_module
from scripts.evaluate_ocr_v34 import evaluate_runs, main, score_sample

FIELDS = ("name", "strength", "doseQuantity", "timesPerDay", "days")


def _row(name: str, *, strength: str | None = "10mg") -> dict[str, object]:
    return {
        "name": name,
        "nameAssessable": True,
        "strength": strength,
        "doseQuantity": "1",
        "timesPerDay": "2",
        "days": "3",
    }


def _prediction(name: str, *, strength: str | None = "10mg") -> dict[str, object]:
    return {
        "name": name,
        "strength": strength,
        "doseQuantity": "1",
        "timesPerDay": "2",
        "days": "3",
    }


def _truth(samples: list[tuple[str, list[dict[str, object]]]]) -> dict[str, object]:
    return {"samples": [{"id": sample_id, "rows": rows} for sample_id, rows in samples]}


def _statuses(
    samples: list[tuple[str, list[dict[str, str]]]],
) -> dict[str, object]:
    return {"samples": [{"id": sample_id, "rows": rows} for sample_id, rows in samples]}


def _all_value_status(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    return [{field: "value" for field in FIELDS} for _ in rows]


def _run(sample_id: str, medications: list[dict[str, object]], version: str = "candidate") -> dict[str, object]:
    return {
        "id": sample_id,
        "version": version,
        "review": {"medications": medications},
        "recapture": False,
        "wallMs": 1.0,
        "stages": [],
    }


def test_matching_is_order_independent_and_preserves_legacy_accuracy() -> None:
    rows = [_row("medicine-a"), _row("medicine-b", strength="20mg")]
    truth = _truth([("sample-01", rows)])
    statuses = _statuses([("sample-01", _all_value_status(rows))])
    runs = [_run("sample-01", [_prediction("medicine-b", strength="20mg"), _prediction("medicine-a")])]

    result = evaluate_runs(runs, truth, statuses)
    summary = result["summaries"]["all16"][0]

    assert summary["legacyComparable"] == {"correct": 10, "total": 10, "accuracy": 1.0}
    assert summary["fields"]["micro"]["tp"] == 10
    assert summary["fields"]["micro"]["fp"] == 0
    assert summary["fields"]["micro"]["fn"] == 0
    assert summary["rows"]["exact"] == 2
    assert summary["rows"]["f1"] == 1.0
    assert summary["documents"]["success"] == 1


def test_matching_prefers_name_identity_over_an_unrelated_identical_regimen() -> None:
    first = _row("medicine-a", strength="10mg")
    second = _row("medicine-b", strength="20mg")
    second.update({"doseQuantity": "2", "timesPerDay": "3", "days": "4"})
    first_prediction = _prediction("medicine-a", strength="10mg")
    first_prediction.update({"doseQuantity": "2", "timesPerDay": "3", "days": "4"})
    second_prediction = _prediction("medicine-b", strength="20mg")
    truth = _truth([("sample-01", [first, second])])
    statuses = _statuses([("sample-01", _all_value_status([first, second]))])

    result = evaluate_runs(
        [_run("sample-01", [first_prediction, second_prediction])],
        truth,
        statuses,
    )

    assert result["summaries"]["all16"][0]["legacyComparable"] == {
        "correct": 4,
        "total": 10,
        "accuracy": 0.4,
    }


def test_matching_ties_cannot_change_per_field_scores_when_predictions_are_reordered() -> None:
    first = _row("unreadable-a", strength=None)
    first.update({"doseQuantity": "1", "timesPerDay": "1", "days": "1", "nameAssessable": False})
    second = _row("unreadable-b", strength=None)
    second.update({"doseQuantity": "1", "timesPerDay": "2", "days": "2", "nameAssessable": False})
    statuses = [
        {
            "name": "unreadable",
            "strength": "absent",
            "doseQuantity": "value",
            "timesPerDay": "value",
            "days": "value",
        },
        {
            "name": "unreadable",
            "strength": "absent",
            "doseQuantity": "value",
            "timesPerDay": "value",
            "days": "value",
        },
    ]
    prediction_a = {"doseQuantity": "1", "timesPerDay": "1", "days": "2"}
    prediction_b = {"doseQuantity": "1", "timesPerDay": "2", "days": "1"}

    forward = score_sample([first, second], [prediction_a, prediction_b], statuses)
    reversed_order = score_sample([first, second], [prediction_b, prediction_a], statuses)

    assert forward["fieldCounts"] == reversed_order["fieldCounts"]
    assert forward["legacyCorrect"] == reversed_order["legacyCorrect"]
    assert forward["strictExact"] == reversed_order["strictExact"]


def test_extra_rows_absent_claims_and_substitutions_are_false_positives() -> None:
    truth = _truth([("sample-01", [_row("medicine-a", strength=None)])])
    statuses = _statuses(
        [
            (
                "sample-01",
                [
                    {
                        "name": "value",
                        "strength": "absent",
                        "doseQuantity": "value",
                        "timesPerDay": "unreadable",
                        "days": "value",
                    }
                ],
            )
        ]
    )
    matched: dict[str, object] = {
        "name": "medicine-a",
        "strength": "5mg",
        "doseQuantity": "1",
        "timesPerDay": "99",
        "days": "8",
    }
    extra = _prediction("extra-medicine")

    result = evaluate_runs([_run("sample-01", [extra, matched])], truth, statuses)
    summary = result["summaries"]["all16"][0]
    micro = summary["fields"]["micro"]

    assert summary["sourceStatusSupport"] == {"value": 3, "absent": 1, "unreadable": 1}
    assert (micro["tp"], micro["fp"], micro["fn"]) == (2, 7, 1)
    assert micro["unreadableClaims"] == 1
    assert summary["rows"]["tp"] == 0
    assert summary["rows"]["fp"] == 2
    assert summary["rows"]["fn"] == 1
    assert summary["rows"]["f1"] == 0.0
    assert summary["documents"]["success"] == 0


def test_missing_row_is_a_row_and_field_false_negative() -> None:
    rows = [_row("medicine-a"), _row("medicine-b", strength="20mg")]
    truth = _truth([("sample-01", rows)])
    statuses = _statuses([("sample-01", _all_value_status(rows))])

    result = evaluate_runs([_run("sample-01", [_prediction("medicine-a")])], truth, statuses)
    summary = result["summaries"]["all16"][0]

    assert summary["legacyComparable"] == {"correct": 5, "total": 10, "accuracy": 0.5}
    assert summary["fields"]["micro"]["fn"] == 5
    assert summary["rows"]["tp"] == 1
    assert summary["rows"]["fp"] == 0
    assert summary["rows"]["fn"] == 1
    assert summary["rows"]["fullFiveLegacyExact"] == 1
    assert summary["rows"]["fullFiveLegacyAssessable"] == 2
    assert summary["rows"]["strictExactRate"] == 0.5


def test_unreadable_claim_is_reported_but_not_scored_as_false_positive() -> None:
    row = _row("medicine-a", strength=None)
    truth = _truth([("sample-01", [row])])
    statuses = _statuses(
        [
            (
                "sample-01",
                [
                    {
                        "name": "value",
                        "strength": "unreadable",
                        "doseQuantity": "value",
                        "timesPerDay": "value",
                        "days": "value",
                    }
                ],
            )
        ]
    )
    prediction = _prediction("medicine-a", strength="unverifiable")

    result = evaluate_runs([_run("sample-01", [prediction])], truth, statuses)
    micro = result["summaries"]["all16"][0]["fields"]["micro"]

    assert (micro["tp"], micro["fp"], micro["fn"]) == (4, 0, 0)
    assert micro["unreadableClaims"] == 1


def test_default_document_grouping_weights_samples_08_and_11_as_one_of_15_groups() -> None:
    samples = [(f"sample-{index:02}", [_row(f"medicine-{index:02}")]) for index in range(1, 17)]
    truth = _truth(samples)
    statuses = _statuses([(sample_id, _all_value_status(rows)) for sample_id, rows in samples])
    runs = [
        _run(sample_id, [_prediction("wrong" if sample_id == "sample-11" else str(rows[0]["name"]))])
        for sample_id, rows in samples
    ]

    result = evaluate_runs(runs, truth, statuses)
    all16 = result["summaries"]["all16"][0]

    assert all16["documents"]["success"] == 15
    assert all16["documents"]["total"] == 16
    assert all16["documents"]["groupCount"] == 15
    assert all16["documents"]["groupMacroSuccessRate"] == pytest.approx(14.5 / 15)
    assert result["summaries"]["original8"][0]["images"] == 8
    assert result["summaries"]["additional8"][0]["images"] == 8


def test_statuses_must_cover_every_row_and_cannot_mark_unassessable_name_as_value() -> None:
    row = _row("tentative")
    row["nameAssessable"] = False
    truth = _truth([("sample-01", [row])])
    statuses = _statuses([("sample-01", _all_value_status([row]))])

    with pytest.raises(ValueError, match="unassessable name"):
        evaluate_runs([_run("sample-01", [_prediction("tentative")])], truth, statuses)


def test_cli_writes_a_json_report(tmp_path: Path) -> None:
    row = _row("medicine-a")
    inputs = {
        "results": [_run("sample-01", [_prediction("medicine-a")])],
        "truth": _truth([("sample-01", [row])]),
        "statuses": _statuses([("sample-01", _all_value_status([row]))]),
    }
    paths: dict[str, Path] = {}
    for name, payload in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths[name] = path
    output = tmp_path / "evaluation.json"
    output.write_text("stale and invalid", encoding="utf-8")

    exit_code = main(
        [
            "--results",
            str(paths["results"]),
            "--truth",
            str(paths["truth"]),
            "--statuses",
            str(paths["statuses"]),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schemaVersion"] == "ocr-v3.4-evaluation/v1"
    assert report["provenance"] == {
        "resultsSha256": hashlib.sha256(paths["results"].read_bytes()).hexdigest(),
        "truthSha256": hashlib.sha256(paths["truth"].read_bytes()).hexdigest(),
        "statusesSha256": hashlib.sha256(paths["statuses"].read_bytes()).hexdigest(),
        "evaluatorSha256": hashlib.sha256(Path(evaluator_module.__file__).read_bytes()).hexdigest(),
        "timingsSha256": None,
    }
    assert list(tmp_path.glob(".evaluation.json.*.tmp")) == []


def test_wrapped_runs_are_separated_by_variant_and_accept_new_timings_shape() -> None:
    row = _row("medicine-a")
    truth = _truth([("sample-01", [row])])
    statuses = _statuses([("sample-01", _all_value_status([row]))])
    identity_run = {**_run("sample-01", [_prediction("medicine-a")]), "variant": "identity"}
    adaptive_run = {**_run("sample-01", [_prediction("wrong")]), "variant": "adaptive"}
    results = {"identity": "evidence-hash", "runs": [identity_run, adaptive_run]}
    timings = {
        "identity": "evidence-hash",
        "runs": [
            {"id": "sample-01", "variant": "identity", "timesMs": {"candidate": [1.0, 3.0, 5.0]}},
            {"id": "sample-01", "variant": "adaptive", "timesMs": {"candidate": [2.0, 4.0, 6.0]}},
        ],
    }

    result = evaluate_runs(results, truth, statuses, timings=timings)

    assert result["identity"] == "evidence-hash"
    assert set(result["variants"]) == {"identity", "adaptive"}
    assert "summaries" not in result
    assert result["variants"]["identity"]["summaries"]["all16"][0]["legacyComparable"]["correct"] == 5
    assert result["variants"]["adaptive"]["summaries"]["all16"][0]["legacyComparable"]["correct"] == 4
    assert result["variants"]["identity"]["summaries"]["all16"][0]["timing"]["preprocessMeanOfMediansMs"] == 3.0
    assert result["variants"]["adaptive"]["summaries"]["all16"][0]["timing"]["preprocessMeanOfMediansMs"] == 4.0


def test_frozen_16_by_3_results_reproduce_the_legacy_baseline() -> None:
    data_dir = Path(__file__).resolve().parents[3] / "ocr-16-three-versions-20260907"
    if not data_dir.exists():
        pytest.skip("The frozen local OCR-16 evidence bundle is not present.")
    truth = json.loads((data_dir / "ground-truth.json").read_text(encoding="utf-8"))
    runs = json.loads((data_dir / "results.json").read_text(encoding="utf-8"))
    status_dir = data_dir.parent / "ocr-v34-adaptive-20260907"
    status_samples = []
    if status_dir.exists():
        for filename in ("source-status-01-08.json", "source-status-09-16.json"):
            status_samples.extend(json.loads((status_dir / filename).read_text(encoding="utf-8"))["samples"])
        status_counts = {status: 0 for status in ("value", "absent", "unreadable")}
        for sample in status_samples:
            for row in sample["rows"]:
                for status in row.values():
                    status_counts[status] += 1
        assert status_counts == {"value": 309, "absent": 44, "unreadable": 32}
    else:
        for sample in truth["samples"]:
            status_rows = []
            for row in sample["rows"]:
                status_rows.append(
                    {
                        field: (
                            "unreadable"
                            if field == "name" and not row["nameAssessable"]
                            else "value"
                            if row[field] is not None
                            else "unreadable"
                        )
                        for field in FIELDS
                    }
                )
            status_samples.append({"id": sample["id"], "rows": status_rows})

    result = evaluate_runs(runs, truth, {"samples": status_samples})
    by_version = {summary["version"]: summary for summary in result["summaries"]["all16"]}

    assert {
        version: (summary["legacyComparable"]["correct"], summary["legacyComparable"]["total"])
        for version, summary in by_version.items()
    } == {"v3.1.3": (239, 309), "v3.2.7": (238, 309), "v3.3.1": (238, 309)}
    assert {
        version: (summary["rows"]["fullFiveLegacyExact"], summary["rows"]["fullFiveLegacyAssessable"])
        for version, summary in by_version.items()
    } == {"v3.1.3": (13, 22), "v3.2.7": (13, 22), "v3.3.1": (13, 22)}
    if status_dir.exists():
        assert {
            version: (
                summary["fields"]["micro"]["tp"],
                summary["fields"]["micro"]["fp"],
                summary["fields"]["micro"]["fn"],
            )
            for version, summary in by_version.items()
        } == {"v3.1.3": (239, 9, 70), "v3.2.7": (238, 8, 71), "v3.3.1": (238, 10, 71)}

