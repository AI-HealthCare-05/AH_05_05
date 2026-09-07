from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.medication_ocr_v3.pipeline.preprocess import _preprocess_profile
from scripts.benchmark_ocr_preprocess_v31 import main, run_preprocess_benchmark


def _clock(values: list[float]) -> Callable[[], float]:
    iterator: Iterator[float] = iter(values)
    return lambda: next(iterator)


def _result(*, template_bytes: bytes = b"processed-jpeg") -> SimpleNamespace:
    return SimpleNamespace(
        quality_state=SimpleNamespace(value="PROCESSED"),
        preprocessing_mode=SimpleNamespace(value="PERSPECTIVE"),
        correction_preset=SimpleNamespace(value="illumination"),
        grayscale_level=0,
        reasons=("perspective_rectified",),
        operations=("perspective_rectified", "illumination_equalized"),
        template_image=SimpleNamespace(
            jpeg_bytes=template_bytes,
            width=1200,
            height=800,
            used_perspective=True,
            rollback_reason=None,
        ),
        oriented_preview=SimpleNamespace(jpeg_bytes=b"preview-jpeg", width=900, height=600),
        metrics=SimpleNamespace(
            as_dict=lambda: {
                "blurVariance": 123.5,
                "pageCoverage": 0.72,
                "cornerConfidence": 0.94,
            }
        ),
        raw_to_oriented=SimpleNamespace(matrix=(1.0,) * 9),
        raw_to_template=SimpleNamespace(matrix=(2.0,) * 9),
    )


@pytest.mark.parametrize(
    ("version", "iterations", "max_edge", "trigger_confidence"),
    [
        ("v3.1.0", 4, 800, 0.82),
        ("v3.1.1", 3, 800, 0.82),
        ("v3.1.2", 2, 800, 0.82),
        ("v3.1.3", 1, 800, 0.82),
        ("v3.1.4", 3, 700, 0.82),
        ("v3.1.5", 3, 600, 0.82),
        ("v3.1.6", 3, 500, 0.82),
        ("v3.1.7", 3, 800, 0.78),
        ("v3.1.8", 3, 800, 0.74),
    ],
)
def test_preprocess_version_maps_to_the_documented_profile(
    version: str,
    iterations: int,
    max_edge: int,
    trigger_confidence: float,
) -> None:
    profile = _preprocess_profile(version)

    assert profile.grabcut_iterations == iterations
    assert profile.grabcut_max_edge == max_edge
    assert profile.grabcut_trigger_confidence == trigger_confidence


def test_benchmark_records_anonymous_reproducible_baseline(tmp_path: Path) -> None:
    calls = 0

    def preprocess(
        _source: bytes,
        _mime_type: str,
        *,
        preprocess_version: str,
    ) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        assert preprocess_version == "v3.1.8"
        return _result()

    payload = run_preprocess_benchmark(
        b"private-source-bytes",
        "image/jpeg",
        artifact_dir=tmp_path,
        warmups=1,
        measured_runs=2,
        preprocess_version="v3.1.8",
        preprocess=preprocess,
        clock=_clock([1.0, 1.01, 2.0, 2.02]),
        working_set_bytes=lambda: 160,
    )

    assert calls == 3
    assert payload["schemaVersion"] == "ocr-preprocess-benchmark/v3.1"
    assert payload["preprocessVersion"] == "v3.1.8"
    assert payload["photos"] == 1
    assert payload["warmupsPerPhoto"] == 1
    assert payload["measuredRuns"] == 2
    assert payload["preprocessMs"]["samples"] == pytest.approx([10.0, 20.0])
    assert payload["preprocessMs"]["p50"] == pytest.approx(15.0)
    assert payload["preprocessMs"]["p95"] == pytest.approx(19.5)
    assert payload["peakWorkingSetBytes"] == 160
    assert payload["processedArtifactValid"] == 1
    assert payload["qualityStateAcceptable"] == 1
    assert payload["contractMatch"] == 1
    assert payload["privacyFieldsAbsent"] == 1
    assert (tmp_path / "preprocessed.jpg").read_bytes() == b"processed-jpeg"
    assert (tmp_path / "contract.json").is_file()

    rendered = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("private-source", "source_sha", "filename", "ocrtext", "patient"):
        assert forbidden not in rendered


def test_benchmark_rejects_changed_preprocess_contract(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    run_preprocess_benchmark(
        b"source",
        "image/jpeg",
        artifact_dir=baseline_dir,
        warmups=0,
        measured_runs=1,
        preprocess=lambda *_args, **_kwargs: _result(template_bytes=b"baseline"),
        clock=_clock([1.0, 1.01]),
        working_set_bytes=lambda: 100,
    )

    payload = run_preprocess_benchmark(
        b"source",
        "image/jpeg",
        artifact_dir=candidate_dir,
        baseline_contract=baseline_dir / "contract.json",
        warmups=0,
        measured_runs=1,
        preprocess=lambda *_args, **_kwargs: _result(template_bytes=b"changed"),
        clock=_clock([2.0, 2.01]),
        working_set_bytes=lambda: 100,
    )

    assert payload["contractMatch"] == 0
    assert payload["contractMismatches"] == ["templateJpegSha256"]


def test_cli_requires_explicit_artifact_directory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OCR_V31_REFERENCE_IMAGE", "private-reference.jpg")
    monkeypatch.delenv("OCR_V31_ARTIFACT_DIR", raising=False)

    assert main() == 2
    assert "OCR_V31_ARTIFACT_DIR is required." in capsys.readouterr().err

