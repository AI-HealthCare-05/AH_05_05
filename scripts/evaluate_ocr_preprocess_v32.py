from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage

VERSIONS = tuple(f"v3.2.{patch}" for patch in range(1, 9))


async def evaluate(image_path: Path, artifact_root: Path) -> int:
    settings = Config()
    endpoint = settings.CLOVA_GENERAL_OCR_INVOKE_URL
    secret = settings.CLOVA_GENERAL_OCR_SECRET
    if endpoint is None or secret is None:
        print("CLOVA General OCR configuration is required.", file=sys.stderr)
        return 2
    image = ValidatedImage(
        filename="reference.jpg",
        media_type="image/jpeg",
        provider_format="jpg",
        content=image_path.read_bytes(),
    )
    async with ClovaGeneralOcrProvider(
        endpoint=endpoint,
        secret=secret.get_secret_value(),
    ) as provider:
        for version in VERSIONS:
            print(f"START {version}", flush=True)
            analysis = await MedicationOcrV3Service(
                provider=provider,
                structurer=None,
                preprocess_version=version,
            ).analyze(image)
            payload = {
                "schemaVersion": analysis.schema_version,
                "preprocessVersion": analysis.preprocess_version,
                "ocrModel": analysis.ocr_model,
                "structuringModel": analysis.structuring_model,
                "llmEnabled": False,
                "projectReview": analysis.project_review,
                "stages": analysis.stages,
                "requiresRecapture": analysis.requires_recapture,
                "recaptureReasons": list(analysis.recapture_reasons),
                "privacy": {
                    "sourcePersisted": False,
                    "ocrRawTextPersisted": False,
                },
            }
            output = artifact_root / version / "ocr-result.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            medications = analysis.project_review.get("medications", [])
            low_count = analysis.project_review.get("lowConfidenceCount", 0)
            print(f"DONE {version} medications={len(medications)} low={low_count}", flush=True)
    return 0


def main() -> int:
    image_value = os.environ.get("OCR_V32_REFERENCE_IMAGE")
    artifact_value = os.environ.get("OCR_V32_ARTIFACT_ROOT")
    if not image_value or not artifact_value:
        print("OCR_V32_REFERENCE_IMAGE and OCR_V32_ARTIFACT_ROOT are required.", file=sys.stderr)
        return 2
    return asyncio.run(evaluate(Path(image_value), Path(artifact_value)))


if __name__ == "__main__":
    raise SystemExit(main())

