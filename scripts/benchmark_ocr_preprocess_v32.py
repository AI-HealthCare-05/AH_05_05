from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image
from scripts.benchmark_ocr_preprocess_v31 import (
    PreprocessCall,
    _enum_value,
    _mime_type,
    run_preprocess_benchmark,
)

SCHEMA_VERSION = "ocr-preprocess-benchmark/v3.2"


def generate_preprocessed_artifact(
    image_bytes: bytes,
    mime_type: str,
    *,
    artifact_dir: Path,
    preprocess_version: str,
    preprocess: PreprocessCall = preprocess_image,
) -> dict[str, object]:
    if not image_bytes or not preprocess_version.startswith("v3.2."):
        raise ValueError("A source image and v3.2 preprocess version are required.")
    result = preprocess(image_bytes, mime_type, preprocess_version=preprocess_version)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "preprocessed.jpg"
    artifact_path.write_bytes(result.template_image.jpeg_bytes)
    payload: dict[str, object] = {
        "schemaVersion": "ocr-preprocess-generation/v3.2",
        "preprocessVersion": preprocess_version,
        "providerJpegSha256": hashlib.sha256(result.template_image.jpeg_bytes).hexdigest(),
        "providerJpegBytes": len(result.template_image.jpeg_bytes),
        "output": {
            "width": result.template_image.width,
            "height": result.template_image.height,
        },
        "quality": {
            "state": _enum_value(result.quality_state),
            "mode": _enum_value(result.preprocessing_mode),
            "reasons": list(result.reasons),
            "operations": list(result.operations),
        },
        "privacy": {
            "sourcePersisted": False,
            "recognizedContentPersisted": False,
            "artifactContainsDocumentImage": True,
        },
    }
    (artifact_dir / "generation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def main() -> int:
    image_value = os.environ.get("OCR_V32_REFERENCE_IMAGE")
    artifact_value = os.environ.get("OCR_V32_ARTIFACT_DIR")
    preprocess_version = os.environ.get("OCR_PREPROCESS_VERSION", "v3.2.1")
    if not image_value or not artifact_value:
        print("OCR_V32_REFERENCE_IMAGE and OCR_V32_ARTIFACT_DIR are required.", file=sys.stderr)
        return 2
    try:
        image_path = Path(image_value)
        artifact_dir = Path(artifact_value)
        if os.environ.get("OCR_V32_GENERATE_ONLY") == "1":
            payload = generate_preprocessed_artifact(
                image_path.read_bytes(),
                _mime_type(image_path),
                artifact_dir=artifact_dir,
                preprocess_version=preprocess_version,
            )
        else:
            payload = run_preprocess_benchmark(
                image_path.read_bytes(),
                _mime_type(image_path),
                artifact_dir=artifact_dir,
                preprocess_version=preprocess_version,
            )
            payload["schemaVersion"] = SCHEMA_VERSION
            payload["baselineVersion"] = "v3.1.3"
            (artifact_dir / "metrics.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"benchmark failed: {type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
