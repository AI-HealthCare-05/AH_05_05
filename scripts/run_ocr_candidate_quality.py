from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage

CANDIDATES = ("v3.2.1", "v3.2.2", "v3.2.7")
REPEATS = 3


async def run(image_path: Path, output_root: Path) -> int:
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
        for version in CANDIDATES:
            for repeat in range(1, REPEATS + 1):
                print(f"START {version} run={repeat}", flush=True)
                analysis = await MedicationOcrV3Service(
                    provider=provider,
                    structurer=None,
                    preprocess_version=version,
                ).analyze(image)
                payload = {
                    "schemaVersion": analysis.schema_version,
                    "preprocessVersion": version,
                    "run": repeat,
                    "llmEnabled": False,
                    "projectReview": analysis.project_review,
                    "stages": analysis.stages,
                    "avgEvidenceConfidence": (
                        statistics.fmean(analysis.confidence_values) if analysis.confidence_values else None
                    ),
                    "privacy": {"sourcePersisted": False, "ocrRawTextPersisted": False},
                }
                output = output_root / version / f"run-{repeat}.json"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                medications = analysis.project_review.get("medications", [])
                print(f"DONE {version} run={repeat} medications={len(medications)}", flush=True)
    return 0


def main() -> int:
    image_value = os.environ.get("OCR_V32_REFERENCE_IMAGE")
    output_value = os.environ.get("OCR_V32_QUALITY_ROOT")
    if not image_value or not output_value:
        print("OCR_V32_REFERENCE_IMAGE and OCR_V32_QUALITY_ROOT are required.", file=sys.stderr)
        return 2
    return asyncio.run(run(Path(image_value), Path(output_value)))


if __name__ == "__main__":
    raise SystemExit(main())

