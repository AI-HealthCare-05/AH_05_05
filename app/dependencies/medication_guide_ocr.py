from collections.abc import AsyncIterator

import httpx

from app.core import config
from app.core.exceptions import OcrProviderConfigError
from app.services.clova_template_ocr import ClovaTemplateProvider
from app.services.medication_guide_ocr import MedicationGuideService


async def get_medication_guide_service() -> AsyncIterator[MedicationGuideService]:
    template_id = config.CLOVA_TEMPLATE_ID
    if template_id is None:
        raise OcrProviderConfigError()

    async with httpx.AsyncClient() as client:
        yield MedicationGuideService(
            provider=ClovaTemplateProvider(config, client),
            template_id=template_id,
            review_threshold=config.OCR_REVIEW_CONFIDENCE_THRESHOLD,
        )
