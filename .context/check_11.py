import asyncio
import json
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.config import Config
from app.services.medication_ocr_v3.pipeline import medication_rows as mr
from app.services.medication_ocr_v3.pipeline.ocr_layout import build_ocr_layout
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import _normalize


class InspectProvider:
    def __init__(self, base):
        self.base = base

    async def recognize(self, content):
        result = await self.base.recognize(content)
        layout = build_ocr_layout(result)
        for candidate in layout.table_candidates:
            print(
                "CANDIDATE",
                json.dumps(
                    {
                        "id": candidate.candidate_id,
                        "bbox": str(candidate.bbox),
                        "headers": candidate.observed_header_coverage,
                        "inferred": candidate.header_inferred,
                        "ambiguous": len(candidate.ambiguous_column_evidence),
                        "eligible": mr._is_semantically_eligible_medication_candidate(candidate),
                        "rows": [[c.text if c else None for c in row.cells] for row in candidate.rows],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        print(
            "CONFLICT",
            mr._has_conflicting_near_duplicate_names(layout.table_candidates),
            mr._has_rejected_complete_duplicate_pair(layout.table_candidates),
            flush=True,
        )
        return result


async def main():
    cfg = Config()
    image = _normalize(Path("C:/Antigravity/blog/oz/healthcare/810final/data/11.heic").read_bytes(), "11.heic")
    with Image.open(BytesIO(image.content)) as preview:
        preview.thumbnail((1600, 1600))
        preview.save(".context/11-preview.jpg")
    async with (
        ClovaGeneralOcrProvider(
            endpoint=cfg.CLOVA_GENERAL_OCR_INVOKE_URL, secret=cfg.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
        ) as provider,
        OpenAIGroundedStructurer(api_key=cfg.OPENAI_API_KEY.get_secret_value(), model=cfg.OPENAI_MODEL) as llm,
    ):
        start = time.monotonic()
        result = await MedicationOcrV3Service(
            provider=InspectProvider(provider),
            structurer=llm,
            preprocess_version=sys.argv[1] if len(sys.argv) > 1 else cfg.OCR_PREPROCESS_VERSION,
        ).analyze(image)
        print(
            json.dumps(
                {
                    "elapsed": round(time.monotonic() - start, 2),
                    "version": result.preprocess_version,
                    "stages": result.stages,
                    "recapture": result.recapture_reasons,
                    "medications": result.project_review.get("medications"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if result.processed_image_bytes:
            with Image.open(BytesIO(result.processed_image_bytes)) as preview:
                preview.thumbnail((1600, 1600))
                preview.save(".context/11-processed.jpg")


asyncio.run(main())
