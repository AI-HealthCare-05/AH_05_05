"""Run the OCR service without DB writes or persistent image/OCR caches.

Usage: python docs/debug/diagnose_mobile_photo.py PHOTO --expect-count 3
"""

import argparse
import asyncio
import io
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import UploadFile  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402

from app.core.config import Config  # noqa: E402
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider  # noqa: E402
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer  # noqa: E402
from app.services.medication_ocr_v3.service import MedicationOcrV3Service  # noqa: E402
from app.services.ocr_image_input import validate_image  # noqa: E402


async def main(args: argparse.Namespace) -> None:
    logging.disable(logging.CRITICAL)
    config = Config()
    source = Path(args.photo)
    mime = "image/jpeg" if source.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    upload = UploadFile(
        filename=source.name, file=io.BytesIO(source.read_bytes()), headers=Headers({"content-type": mime})
    )
    try:
        validated = await validate_image(upload)
    finally:
        await upload.close()
    async with (
        ClovaGeneralOcrProvider(
            endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL,
            secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value(),
        ) as provider,
        OpenAIGroundedStructurer(
            api_key=config.OPENAI_API_KEY.get_secret_value(),
            model=config.OPENAI_MODEL,
        ) as structurer,
    ):
        service = MedicationOcrV3Service(
            provider=provider, structurer=structurer, preprocess_version=config.OCR_PREPROCESS_VERSION
        )
        result = await asyncio.wait_for(service.analyze(validated), timeout=120)
    medications = result.project_review.get("medications", [])
    print(
        json.dumps(
            {
                "file": source.name,
                "preprocess": result.preprocess_version,
                "stages": result.stages,
                "recapture": result.requires_recapture,
                "medications": medications,
            },
            ensure_ascii=False,
        )
    )
    assert not result.requires_recapture, "Image requires recapture"
    if args.expect_count is not None:
        assert len(medications) == args.expect_count, "Unexpected medication count"
    if args.expect_name_only:
        assert all(not {"doseQuantity", "timesPerDay", "days"}.intersection(row) for row in medications)
    if args.expect_schedule:
        dose, times, days = args.expect_schedule.split(",")
        assert all(
            row.get("doseQuantity") == dose and row.get("timesPerDay") == int(times) and row.get("days") == int(days)
            for row in medications
        ), "Unexpected regimen"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo")
    parser.add_argument("--expect-count", type=int)
    parser.add_argument("--expect-name-only", action="store_true")
    parser.add_argument("--expect-schedule", help="Expected dose,times,days for every row")
    asyncio.run(main(parser.parse_args()))
