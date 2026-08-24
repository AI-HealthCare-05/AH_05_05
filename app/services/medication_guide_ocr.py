from typing import Protocol

from fastapi import UploadFile

from app.core.exceptions import NoMedicationsFoundError, OcrProviderError, TemplateNotMatchedError
from app.dtos.medication_guide_ocr import MedicationGuideResult
from app.services.medication_guide_normalizer import OcrPayloadError, normalize_clova_response
from app.services.ocr_image_input import ValidatedImage, validate_image


class TemplateProvider(Protocol):
    async def extract(self, image: ValidatedImage) -> object: ...


class MedicationGuideService:
    def __init__(
        self,
        provider: TemplateProvider,
        template_id: int,
        review_threshold: float,
    ) -> None:
        self._provider = provider
        self._template_id = template_id
        self._review_threshold = review_threshold

    async def extract(self, upload: UploadFile) -> MedicationGuideResult:
        image = await validate_image(upload)
        payload = await self._provider.extract(image)
        try:
            return normalize_clova_response(
                payload,
                expected_template_id=self._template_id,
                review_threshold=self._review_threshold,
            )
        except OcrPayloadError as error:
            if error.code == "TEMPLATE_NOT_MATCHED":
                raise TemplateNotMatchedError() from error
            if error.code == "NO_MEDICATIONS_FOUND":
                raise NoMedicationsFoundError() from error
            raise OcrProviderError() from error
