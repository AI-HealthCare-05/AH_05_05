from collections.abc import AsyncIterator

from app.core import config
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService
from app.services.ocr_volatile_storage import VolatileOcrStorage


async def get_medication_guide_ocr_job_service() -> AsyncIterator[MedicationGuideOcrJobService]:
    storage = VolatileOcrStorage(config.OCR_IMAGE_REDIS_URL, config.OCR_REVIEW_TTL_MINUTES * 60)
    try:
        yield MedicationGuideOcrJobService(storage=storage)
    finally:
        await storage.aclose()
