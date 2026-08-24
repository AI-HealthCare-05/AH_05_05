from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.dependencies.medication_guide_ocr import get_medication_guide_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import MedicationGuideResult, OcrErrorResponse
from app.models.users import User
from app.services.medication_guide_ocr import MedicationGuideService

medication_guide_ocr_router = APIRouter(
    prefix="/ocr",
    tags=["medication-guide-ocr"],
)


@medication_guide_ocr_router.post(
    "/medication-guides",
    response_model=MedicationGuideResult,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": OcrErrorResponse,
            "description": "요청 용량 초과 (OCR_UPLOAD_TOO_LARGE)",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": OcrErrorResponse,
            "description": (
                "요청·이미지·OCR 결과 검증 실패 "
                "(VALIDATION_ERROR, INVALID_IMAGE, TEMPLATE_NOT_MATCHED, NO_MEDICATIONS_FOUND)"
            ),
        },
        status.HTTP_502_BAD_GATEWAY: {
            "model": OcrErrorResponse,
            "description": "CLOVA OCR 응답 오류 (OCR_PROVIDER_ERROR)",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": OcrErrorResponse,
            "description": "CLOVA OCR 설정 누락 (PROVIDER_CONFIG_MISSING)",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "model": OcrErrorResponse,
            "description": "CLOVA OCR 응답 시간 초과 (OCR_PROVIDER_TIMEOUT)",
        },
    },
    summary="조제약 복약안내 이미지 OCR",
)
async def extract_medication_guide(
    file: Annotated[UploadFile, File(description="JPG 또는 PNG 조제약 복약안내 이미지")],
    response: Response,
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationGuideService, Depends(get_medication_guide_service)],
) -> MedicationGuideResult:
    """등록된 CLOVA Template OCR 양식으로 약 정보와 복약 안내를 구조화한다."""

    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return await service.extract(file)
