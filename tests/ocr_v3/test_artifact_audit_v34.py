from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.audit_ocr_v34_artifacts import AuditError, audit_artifacts, digest, main


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checkpoint(path: Path, result: dict[str, Any]) -> None:
    _write_json(path, {"result": result, "checksum": digest(result)})


def _valid_artifacts(tmp_path: Path) -> dict[str, Path]:
    directory = tmp_path / "experiment"
    code_root = tmp_path / "code"
    source_directory = tmp_path / "sources"
    truth = tmp_path / "ground-truth.json"
    statuses = tmp_path / "source-status.json"
    evaluator = tmp_path / "evaluate_ocr_v34.py"
    _write_json(truth, {"samples": [{"id": "sample-01"}, {"id": "sample-02"}]})
    _write_json(statuses, {"samples": [{"id": "sample-01"}, {"id": "sample-02"}]})
    evaluator.write_text("# frozen evaluator\n", encoding="utf-8")
    app_file = code_root / "app" / "services" / "medication_ocr_v3" / "pipeline.py"
    benchmark = code_root / "scripts" / "benchmark_ocr_v34.py"
    config_py = code_root / "app" / "core" / "config.py"
    app_file.parent.mkdir(parents=True)
    benchmark.parent.mkdir(parents=True)
    config_py.parent.mkdir(parents=True)
    app_file.write_bytes(b"# app code\n")
    benchmark.write_bytes(b"# benchmark\n")
    config_py.write_bytes(b"# config\n")
    source_directory.mkdir()
    (source_directory / "one.png").write_bytes(b"one source")
    (source_directory / "two.png").write_bytes(b"two source")
    file_name = "app/services/medication_ocr_v3/pipeline.py"
    code_hash = hashlib.sha256()
    code_hash.update(file_name.encode() + app_file.read_bytes())

    manifest: dict[str, Any] = {
        "schemaVersion": "ocr-v34-adaptive/1",
        "images": [
            {"id": "sample-01", "file": "one.png", "sha256": _file_hash(source_directory / "one.png")},
            {"id": "sample-02", "file": "two.png", "sha256": _file_hash(source_directory / "two.png")},
        ],
        "versions": ["v1", "v2"],
        "truthSha256": _file_hash(truth),
        "config": {"llm": False, "ocrRepeats": 1, "localRepeats": 3, "variants": ["identity"]},
        "code": {
            "fileMap": [{"path": file_name, "sha256": _file_hash(app_file)}],
            "codeHash": code_hash.hexdigest(),
            "harnessSha256": _file_hash(benchmark),
        },
        "runtime": {"configPySha256": _file_hash(config_py)},
    }
    manifest["configHash"] = digest(manifest["config"])
    identity = digest(manifest)
    _write_json(directory / "manifest.json", manifest)

    runs = []
    for image in manifest["images"]:
        for version, wall_ms in (("v1", 10.0), ("v2", 20.0)):
            run = {
                "id": image["id"],
                "sha256": image["sha256"],
                "version": version,
                "variant": "identity",
                "identity": identity,
                "wallMs": wall_ms + (5.0 if image["id"] == "sample-02" else 0.0),
                "providerCallCount": 1,
                "transform": {
                    "sourceSha256": image["sha256"],
                    "transformedSha256": image["sha256"],
                    "parameters": {"name": "identity"},
                },
                "review": {"medications": []},
            }
            runs.append(run)
            _checkpoint(directory / "runs" / f"{image['id']}-{version}-identity.json", run)
    _write_json(directory / "results.json", {"identity": identity, "runs": runs})

    timing_runs = []
    for index, image in enumerate(manifest["images"]):
        timing = {
            "id": image["id"],
            "sha256": image["sha256"],
            "version": "timings",
            "variant": "identity",
            "identity": identity,
            "transform": {
                "sourceSha256": image["sha256"],
                "transformedSha256": image["sha256"],
                "parameters": {"name": "identity"},
            },
            "timesMs": {"v1": [1.0 + index, 2.0 + index, 9.0 + index], "v2": [3.0, 4.0, 5.0]},
        }
        timing_runs.append(timing)
        _checkpoint(directory / "timings" / f"{image['id']}-identity.json", timing)
    timings = directory / "local-timings.json"
    _write_json(timings, {"identity": identity, "runs": timing_runs})

    results = directory / "results.json"
    scores = directory / "scores.json"
    _write_json(
        scores,
        {
            "schemaVersion": "ocr-v3.4-evaluation/v1",
            "identity": identity,
            "provenance": {
                "resultsSha256": _file_hash(results),
                "truthSha256": _file_hash(truth),
                "statusesSha256": _file_hash(statuses),
                "evaluatorSha256": _file_hash(evaluator),
                "timingsSha256": _file_hash(timings),
            },
        },
    )
    return {
        "directory": directory,
        "truth": truth,
        "statuses": statuses,
        "evaluator": evaluator,
        "timings": timings,
        "scores": scores,
        "code_root": code_root,
        "source_directory": source_directory,
    }


def _audit(paths: dict[str, Path], *, without_timings: bool = False) -> dict[str, Any]:
    return audit_artifacts(
        directory=paths["directory"],
        truth_path=paths["truth"],
        statuses_path=paths["statuses"],
        evaluator_path=paths["evaluator"],
        scores_path=paths["scores"],
        timings_path=None if without_timings else paths["timings"],
        without_timings=without_timings,
        code_root=paths["code_root"],
        source_directory=paths["source_directory"],
    )


def test_valid_artifacts_report_complete_grids_and_latency_statistics(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)

    report = _audit(paths)

    assert report["valid"] is True
    assert report["identity"] == json.loads((paths["directory"] / "results.json").read_text())["identity"]
    assert report["grid"] == {
        "images": 2,
        "versions": 2,
        "variants": 1,
        "resultRuns": 4,
        "timingRuns": 2,
        "localRepeats": 3,
    }
    stats = report["latencyMs"]
    assert stats["aggregation"] == "mean/median/p95(linear) across per-image-variant observations"
    assert stats["localThreeRepeatMedianByVersion"]["v1"] == {
        "count": 2,
        "mean": 2.5,
        "median": 2.5,
        "p95": 2.95,
    }
    assert stats["fullWallByVersion"]["v2"]["median"] == 22.5


def test_missing_result_grid_cell_is_rejected(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    results_path = paths["directory"] / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["runs"].pop()
    _write_json(results_path, results)

    with pytest.raises(AuditError, match="result grid mismatch.*missing"):
        _audit(paths)


def test_duplicate_manifest_version_is_rejected(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    manifest_path = paths["directory"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["versions"] = ["v1", "v1"]
    _write_json(manifest_path, manifest)

    with pytest.raises(AuditError, match="manifest versions contains duplicates"):
        _audit(paths)


@pytest.mark.parametrize("bad_times", [[1.0, 2.0], [1.0, float("nan"), 3.0], [1.0, float("inf"), 3.0]])
def test_timing_repeats_must_be_exactly_three_finite_values(tmp_path: Path, bad_times: list[float]) -> None:
    paths = _valid_artifacts(tmp_path)
    timings = json.loads(paths["timings"].read_text(encoding="utf-8"))
    timings["runs"][0]["timesMs"]["v1"] = bad_times
    _write_json(paths["timings"], timings)

    with pytest.raises(AuditError, match="timing values"):
        _audit(paths)


def test_timing_versions_must_exactly_match_manifest(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    timings = json.loads(paths["timings"].read_text(encoding="utf-8"))
    timings["runs"][0]["timesMs"] = {"v1": [1.0, 2.0, 3.0]}
    _write_json(paths["timings"], timings)

    with pytest.raises(AuditError, match="timing version keys"):
        _audit(paths)


def test_modified_checkpoint_payload_is_rejected_even_with_valid_old_checksum(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    checkpoint = paths["directory"] / "runs" / "sample-01-v1-identity.json"
    envelope = json.loads(checkpoint.read_text(encoding="utf-8"))
    envelope["result"]["wallMs"] = 999.0
    _write_json(checkpoint, envelope)

    with pytest.raises(AuditError, match="checkpoint checksum mismatch"):
        _audit(paths)


def test_scores_provenance_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
    scores["provenance"]["resultsSha256"] = "0" * 64
    _write_json(paths["scores"], scores)

    with pytest.raises(AuditError, match="scores provenance resultsSha256"):
        _audit(paths)


@pytest.mark.parametrize(("field", "value"), [("llm", True), ("ocrRepeats", 2)])
def test_provider_execution_config_is_strict(tmp_path: Path, field: str, value: object) -> None:
    paths = _valid_artifacts(tmp_path)
    manifest_path = paths["directory"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["config"][field] = value
    manifest["configHash"] = digest(manifest["config"])
    _write_json(manifest_path, manifest)

    with pytest.raises(AuditError, match=field):
        _audit(paths)


def test_provider_call_count_cannot_exceed_one(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    results_path = paths["directory"] / "results.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["runs"][0]["providerCallCount"] = 2
    run = results["runs"][0]
    _write_json(results_path, results)
    _checkpoint(paths["directory"] / "runs" / f"{run['id']}-{run['version']}-{run['variant']}.json", run)
    scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
    scores["provenance"]["resultsSha256"] = _file_hash(results_path)
    _write_json(paths["scores"], scores)

    with pytest.raises(AuditError, match="providerCallCount"):
        _audit(paths)


def test_residual_inflight_marker_is_rejected(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    (paths["directory"] / "runs" / "sample-01-v1-identity.inflight").write_text("in progress", encoding="utf-8")

    with pytest.raises(AuditError, match="inflight"):
        _audit(paths)


@pytest.mark.parametrize(
    ("relative_path", "message"),
    [
        ("app/services/medication_ocr_v3/pipeline.py", "code file hash"),
        ("scripts/benchmark_ocr_v34.py", "benchmark harness hash"),
        ("app/core/config.py", "config.py hash"),
    ],
)
def test_current_code_hashes_must_match_manifest(tmp_path: Path, relative_path: str, message: str) -> None:
    paths = _valid_artifacts(tmp_path)
    (paths["code_root"] / relative_path).write_text("# modified\n", encoding="utf-8")

    with pytest.raises(AuditError, match=message):
        _audit(paths)


def test_source_file_hash_must_match_manifest(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    (paths["source_directory"] / "one.png").write_bytes(b"modified source")

    with pytest.raises(AuditError, match="source file hash"):
        _audit(paths)


def test_truth_hash_must_match_manifest(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    paths["truth"].write_text("{}", encoding="utf-8")

    with pytest.raises(AuditError, match="manifest truthSha256"):
        _audit(paths)


def test_without_timings_is_explicit_and_requires_null_score_provenance(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    scores = json.loads(paths["scores"].read_text(encoding="utf-8"))
    scores["provenance"]["timingsSha256"] = None
    _write_json(paths["scores"], scores)

    report = _audit(paths, without_timings=True)

    assert report["grid"]["timingRuns"] is None
    assert report["latencyMs"]["localThreeRepeatMedianByVersion"] is None
    assert report["checks"]["timings"] == "explicitly omitted"


def test_cli_writes_compact_atomic_report_and_requires_timings_by_default(tmp_path: Path) -> None:
    paths = _valid_artifacts(tmp_path)
    output = tmp_path / "audit.json"
    output.write_text("stale", encoding="utf-8")

    assert (
        main(
            [
                "--directory",
                str(paths["directory"]),
                "--truth",
                str(paths["truth"]),
                "--statuses",
                str(paths["statuses"]),
                "--evaluator",
                str(paths["evaluator"]),
                "--code-root",
                str(paths["code_root"]),
                "--source-directory",
                str(paths["source_directory"]),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    raw = output.read_text(encoding="utf-8")
    assert json.loads(raw)["valid"] is True
    assert "\n" not in raw.rstrip("\n")
    assert list(tmp_path.glob(".audit.json.*.tmp")) == []
