from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
import PIL

from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image

SCHEMA_VERSION = "ocr-preprocess-benchmark/v3.1"
PIPELINE_VERSION = "ocr-pipeline/v3"
PREPROCESSOR_VERSION = "opencv-deterministic/v3"
DEFAULT_WARMUPS = 2
DEFAULT_MEASURED_RUNS = 8


class _ImageBytes(Protocol):
    jpeg_bytes: bytes
    width: int
    height: int


class _PreprocessOutput(Protocol):
    template_image: _ImageBytes
    oriented_preview: _ImageBytes
    quality_state: Any
    preprocessing_mode: Any
    correction_preset: Any
    grayscale_level: int
    reasons: Sequence[str]
    operations: Sequence[str]
    metrics: Any
    raw_to_oriented: Any
    raw_to_template: Any


class PreprocessCall(Protocol):
    def __call__(
        self,
        source_bytes: bytes,
        mime_type: str,
        *,
        preprocess_version: str,
    ) -> _PreprocessOutput: ...


type Clock = Callable[[], float]
type WorkingSetReader = Callable[[], int]


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("At least one measured value is required.")
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _elapsed_summary(samples: Sequence[float]) -> dict[str, object]:
    return {
        "samples": [round(value, 3) for value in samples],
        "p50": round(_percentile(samples, 0.50), 3),
        "p95": round(_percentile(samples, 0.95), 3),
        "max": round(max(samples), 3),
    }


def _working_set_bytes() -> int:
    if sys.platform != "win32":
        try:
            import resource

            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            return value if sys.platform == "darwin" else value * 1024
        except (ImportError, OSError, ValueError):
            return 0

    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("pageFaultCount", ctypes.c_ulong),
            ("peakWorkingSetSize", ctypes.c_size_t),
            ("workingSetSize", ctypes.c_size_t),
            ("quotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("quotaPagedPoolUsage", ctypes.c_size_t),
            ("quotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("quotaNonPagedPoolUsage", ctypes.c_size_t),
            ("pagefileUsage", ctypes.c_size_t),
            ("peakPagefileUsage", ctypes.c_size_t),
        ]

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(_ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    get_process_memory_info.restype = ctypes.c_int
    if not get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb):
        return 0
    return int(counters.peakWorkingSetSize)


def _enum_value(value: object) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _contract(result: _PreprocessOutput) -> dict[str, object]:
    return {
        "templateJpegSha256": hashlib.sha256(result.template_image.jpeg_bytes).hexdigest(),
        "previewJpegSha256": hashlib.sha256(result.oriented_preview.jpeg_bytes).hexdigest(),
        "qualityState": _enum_value(result.quality_state),
        "mode": _enum_value(result.preprocessing_mode),
        "correctionPreset": _enum_value(result.correction_preset),
        "grayscaleLevel": result.grayscale_level,
        "templateDimensions": [result.template_image.width, result.template_image.height],
        "previewDimensions": [result.oriented_preview.width, result.oriented_preview.height],
        "rawToOriented": list(result.raw_to_oriented.matrix),
        "rawToTemplate": list(result.raw_to_template.matrix),
        "reasons": list(result.reasons),
        "operations": list(result.operations),
    }


def _contract_mismatches(
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
) -> list[str]:
    return sorted(key for key in baseline.keys() | candidate.keys() if baseline.get(key) != candidate.get(key))


def _privacy_fields_absent(value: object) -> bool:
    forbidden = ("patient", "filename", "source_sha", "ocrtext", "ocr_text")
    if isinstance(value, Mapping):
        return all(
            not any(token in str(key).lower() for token in forbidden) and _privacy_fields_absent(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return all(_privacy_fields_absent(item) for item in value)
    return True


def run_preprocess_benchmark(
    image_bytes: bytes,
    mime_type: str,
    *,
    artifact_dir: Path,
    baseline_contract: Path | None = None,
    warmups: int = DEFAULT_WARMUPS,
    measured_runs: int = DEFAULT_MEASURED_RUNS,
    preprocess_version: str = "v3.1.1",
    preprocess: PreprocessCall = preprocess_image,
    clock: Clock = time.perf_counter,
    working_set_bytes: WorkingSetReader = _working_set_bytes,
) -> dict[str, object]:
    if not image_bytes or warmups < 0 or measured_runs <= 0:
        raise ValueError("Benchmark input and run counts must be valid.")

    for _ in range(warmups):
        preprocess(image_bytes, mime_type, preprocess_version=preprocess_version)

    samples: list[float] = []
    result: _PreprocessOutput | None = None
    peak_working_set = working_set_bytes()
    for _ in range(measured_runs):
        started = clock()
        result = preprocess(image_bytes, mime_type, preprocess_version=preprocess_version)
        samples.append((clock() - started) * 1000.0)
        peak_working_set = max(peak_working_set, working_set_bytes())
    if result is None:
        raise RuntimeError("Benchmark did not produce a result.")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "preprocessed.jpg").write_bytes(result.template_image.jpeg_bytes)
    current_contract = _contract(result)
    (artifact_dir / "contract.json").write_text(
        json.dumps(current_contract, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    mismatches: list[str] = []
    if baseline_contract is not None:
        baseline = json.loads(baseline_contract.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError("Baseline contract must contain a JSON object.")
        mismatches = _contract_mismatches(baseline, current_contract)

    elapsed = _elapsed_summary(samples)
    payload: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "pipelineVersion": PIPELINE_VERSION,
        "preprocessVersion": preprocess_version,
        "preprocessor": {
            "kind": "deterministic",
            "model": "none",
            "version": PREPROCESSOR_VERSION,
            "libraries": {
                "opencv": cv2.__version__,
                "numpy": np.__version__,
                "pillow": PIL.__version__,
            },
        },
        "photos": 1,
        "warmupsPerPhoto": warmups,
        "measuredRuns": measured_runs,
        "preprocessMs": elapsed,
        "preprocessP50Ms": elapsed["p50"],
        "preprocessP95Ms": elapsed["p95"],
        "preprocessMaxMs": elapsed["max"],
        "peakWorkingSetBytes": peak_working_set,
        "providerJpegBytes": len(result.template_image.jpeg_bytes),
        "previewJpegBytes": len(result.oriented_preview.jpeg_bytes),
        "outputPixels": result.template_image.width * result.template_image.height,
        "processedArtifactValid": int(
            bool(result.template_image.jpeg_bytes)
            and result.template_image.width > 0
            and result.template_image.height > 0
        ),
        "qualityStateAcceptable": int(_enum_value(result.quality_state) == "PROCESSED"),
        "contractMatch": int(not mismatches),
        "contractMismatches": mismatches,
        "quality": {
            "state": _enum_value(result.quality_state),
            "mode": _enum_value(result.preprocessing_mode),
            "correctionPreset": _enum_value(result.correction_preset),
            "grayscaleLevel": result.grayscale_level,
            "reasons": list(result.reasons),
            "operations": list(result.operations),
            "metrics": result.metrics.as_dict(),
        },
        "output": {
            "width": result.template_image.width,
            "height": result.template_image.height,
            "usedPerspective": bool(getattr(result.template_image, "used_perspective", False)),
            "rollbackReason": getattr(result.template_image, "rollback_reason", None),
        },
        "privacy": {
            "sourcePersisted": False,
            "recognizedContentPersisted": False,
            "artifactContainsDocumentImage": True,
        },
    }
    payload["privacyFieldsAbsent"] = int(_privacy_fields_absent(payload))
    return payload


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    raise ValueError("Reference image must be JPEG or PNG.")


def main() -> int:
    image_value = os.environ.get("OCR_V31_REFERENCE_IMAGE")
    if not image_value:
        print("OCR_V31_REFERENCE_IMAGE is required.", file=sys.stderr)
        return 2
    artifact_value = os.environ.get("OCR_V31_ARTIFACT_DIR")
    if not artifact_value:
        print("OCR_V31_ARTIFACT_DIR is required.", file=sys.stderr)
        return 2
    image_path = Path(image_value)
    artifact_dir = Path(artifact_value)
    baseline_value = os.environ.get("OCR_V31_BASELINE_CONTRACT")
    baseline_contract = Path(baseline_value) if baseline_value else None
    preprocess_version = os.environ.get("OCR_PREPROCESS_VERSION", "v3.1.1")
    try:
        payload = run_preprocess_benchmark(
            image_path.read_bytes(),
            _mime_type(image_path),
            artifact_dir=artifact_dir,
            baseline_contract=baseline_contract,
            preprocess_version=preprocess_version,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"benchmark failed: {type(error).__name__}", file=sys.stderr)
        return 1

    (artifact_dir / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
