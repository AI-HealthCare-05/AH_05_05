from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Body, Depends, File, Header, Path, Response, UploadFile, status

from app.core import config
from app.core.exceptions import OcrJobStateConflictError
from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import (
    DocumentOcrConfirmRequest,
    DocumentOcrConfirmResponse,
    DocumentOcrFailedResponse,
    DocumentOcrField,
    DocumentOcrFields,
    DocumentOcrMedication,
    DocumentOcrPendingResponse,
    DocumentOcrReadyResponse,
    DocumentOcrStatusResponse,
    DocumentOcrUploadResponse,
    MedicationConfirmation,
    MedicationGuideConfirmRequest,
    MedicationReview,
    OcrErrorResponse,
    OcrJobStatusResponse,
)
from app.models.users import User
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService

medication_guide_ocr_router = APIRouter(tags=["medication-guide-ocr"])

CONFIRMED_OCR_RESULT_EXAMPLE = {
    "dispensedDate": "2026-08-25",
    "medications": [
        {
            "tempId": "med-1",
            "name": "에스오메프라졸캡슐",
            "dose": "20mg",
            "efficacy": "위산 과다, 속쓰림, 역류 증상 완화",
            "administration": "아침 식사 30분 전에 물과 함께 복용하세요.",
            "precautions": "캡슐을 씹거나 열지 마세요. 복통이나 설사가 지속되면 상담하세요.",
            "timesPerDay": 1,
            "days": 14,
        },
        {
            "tempId": "med-2",
            "name": "레바미피드정",
            "dose": "100mg",
            "efficacy": "위점막 보호",
            "administration": "아침, 점심, 저녁 식후에 복용하세요.",
            "precautions": "발진이나 가려움이 나타나면 상담하세요.",
            "timesPerDay": 3,
            "days": 14,
        },
        {
            "tempId": "med-3",
            "name": "모사프리드정",
            "dose": "5mg",
            "efficacy": "위장 운동 촉진",
            "administration": "식사 30분 전에 물과 함께 복용하세요.",
            "precautions": "복통이나 설사가 지속되면 상담하세요.",
            "timesPerDay": 3,
            "days": 14,
        },
        {
            "tempId": "med-4",
            "name": "락토바실러스캡슐",
            "dose": "1캡슐",
            "efficacy": "장내 균총 개선",
            "administration": "식후에 미지근한 물과 함께 복용하세요.",
            "precautions": "뜨거운 음료와 함께 복용하지 마세요.",
            "timesPerDay": 2,
            "days": 14,
        },
    ],
}


@medication_guide_ocr_router.post(
    "/ocr/medication-guides",
    response_model=DocumentOcrUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": OcrErrorResponse,
            "description": "요청 용량 초과 (OCR_UPLOAD_TOO_LARGE)",
        },
        status.HTTP_409_CONFLICT: {
            "model": OcrErrorResponse,
            "description": "Idempotency-Key 충돌 (IDEMPOTENCY_CONFLICT)",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": OcrErrorResponse,
            "description": "요청·이미지 검증 실패 (VALIDATION_ERROR, INVALID_IMAGE)",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": OcrErrorResponse,
            "description": "OCR 대기열 오류 (OCR_QUEUE_UNAVAILABLE)",
        },
    },
    summary="조제약 복약안내 OCR 작업 생성",
)
async def submit_medication_guide_ocr(
    file: Annotated[UploadFile, File(description="JPG 또는 PNG 조제약 복약안내 이미지")],
    idempotency_key: Annotated[str, Header(min_length=8, max_length=100)],
    response: Response,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationGuideOcrJobService, Depends(get_medication_guide_ocr_job_service)],
) -> DocumentOcrUploadResponse:
    """조제약 복약안내 이미지를 비동기 OCR 대기열에 등록한다."""

    _set_private_response_headers(response)
    accepted = await service.submit(user, idempotency_key, file)
    return DocumentOcrUploadResponse(
        batch_id=f"b_{accepted.ocr_job_id}",
        document_ids=[int(accepted.ocr_job_id)],
        ocr_status=_to_public_status(accepted.status.value),
    )


@medication_guide_ocr_router.get(
    "/ocr/jobs/{ocrJobId}/image",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/png": {"schema": {"type": "string", "format": "binary"}},
            },
            "description": "원본 문서 이미지",
        },
        status.HTTP_404_NOT_FOUND: {"model": OcrErrorResponse, "description": "OCR 작업 없음 (OCR_JOB_NOT_FOUND)"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": OcrErrorResponse,
            "description": "OCR 작업 ID 검증 실패 (VALIDATION_ERROR)",
        },
    },
    summary="조제약 복약안내 원본 이미지 조회",
)
async def get_medication_guide_ocr_image(
    ocr_job_id: Annotated[int, Path(alias="ocrJobId")],
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationGuideOcrJobService, Depends(get_medication_guide_ocr_job_service)],
) -> Response:
    content, media_type = await service.read_input_bytes(user, ocr_job_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="medication-guide"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@medication_guide_ocr_router.get(
    "/ocr/jobs/{ocrJobId}",
    response_model=DocumentOcrStatusResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": OcrErrorResponse, "description": "OCR 작업 없음 (OCR_JOB_NOT_FOUND)"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": OcrErrorResponse,
            "description": "OCR 작업 ID 검증 실패 (VALIDATION_ERROR)",
        },
    },
    summary="조제약 복약안내 OCR 작업 조회",
)
async def get_medication_guide_ocr_job(
    ocr_job_id: Annotated[int, Path(alias="ocrJobId")],
    response: Response,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationGuideOcrJobService, Depends(get_medication_guide_ocr_job_service)],
) -> DocumentOcrStatusResponse:
    _set_private_response_headers(response)
    return _to_public_ocr_response(await service.get(user, ocr_job_id))


@medication_guide_ocr_router.patch(
    "/ocr/jobs/{ocrJobId}",
    response_model=DocumentOcrConfirmResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": OcrErrorResponse, "description": "OCR 작업 없음 (OCR_JOB_NOT_FOUND)"},
        status.HTTP_409_CONFLICT: {
            "model": OcrErrorResponse,
            "description": "OCR 작업 상태 충돌 (OCR_JOB_STATE_CONFLICT)",
        },
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "model": OcrErrorResponse,
            "description": "OCR 작업 ID 또는 확정 요청 검증 실패 (VALIDATION_ERROR)",
        },
    },
    summary="조제약 복약안내 OCR 결과 확정",
)
async def confirm_medication_guide_ocr_job(
    ocr_job_id: Annotated[int, Path(alias="ocrJobId")],
    request: Annotated[
        DocumentOcrConfirmRequest,
        Body(
            openapi_examples={
                "confirmedOcrResult": {
                    "summary": "OCR 결과를 확인·수정한 최종값",
                    "value": CONFIRMED_OCR_RESULT_EXAMPLE,
                }
            }
        ),
    ],
    response: Response,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[MedicationGuideOcrJobService, Depends(get_medication_guide_ocr_job_service)],
) -> DocumentOcrConfirmResponse:
    _set_private_response_headers(response)
    confirmation = await service.confirm(user, ocr_job_id, _to_service_confirmation(request))
    return DocumentOcrConfirmResponse(
        record_id=int(confirmation.care_episode_id),
        has_medication=bool(request.medications),
    )


def _set_private_response_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"


def _to_service_confirmation(request: DocumentOcrConfirmRequest) -> MedicationGuideConfirmRequest:
    return MedicationGuideConfirmRequest(
        dispensing_date=request.dispensed_date,
        medications=[
            MedicationConfirmation(
                temp_id=medication.temp_id,
                name=medication.name,
                dose=medication.dose,
                efficacy=medication.efficacy,
                administration=medication.administration,
                precautions=medication.precautions,
                times_per_day=medication.times_per_day,
                days=medication.days,
            )
            for medication in request.medications
        ],
    )


def _to_public_ocr_response(status_response: OcrJobStatusResponse) -> DocumentOcrStatusResponse:
    ocr_status = _to_public_status(status_response.status.value)
    if ocr_status == "failed":
        return DocumentOcrFailedResponse(
            batch_id=f"b_{status_response.ocr_job_id}",
            error_code=status_response.error_code or "EXTRACTION_FAILED",
        )
    if ocr_status not in {"ready_for_review", "complete"}:
        return DocumentOcrPendingResponse(
            batch_id=f"b_{status_response.ocr_job_id}",
            ocr_status=cast(Literal["queued", "processing", "cancelled"], ocr_status),
        )

    result = status_response.result
    if result is None:
        raise OcrJobStateConflictError("OCR 검토 결과를 불러올 수 없습니다.")
    dispensing_date = result.dispensing_date
    raw_date_confidence = result.dispensing_date_confidence or 0.0
    if dispensing_date is None:
        raw_date_confidence = 0.0
    elif dispensing_date > datetime.now(config.TIMEZONE).date():
        dispensing_date = None
        raw_date_confidence = 0.0
    dispensed_date_confidence = _confidence_tier(raw_date_confidence)
    medications = [
        DocumentOcrMedication(
            temp_id=medication.row_id,
            name=medication.name,
            dose=medication.dose or "",
            efficacy=medication.efficacy or "",
            administration=medication.administration or "",
            precautions=medication.precautions or "",
            times_per_day=medication.times_per_day,
            days=medication.days,
            confidence=_public_medication_confidence(medication),
        )
        for medication in result.medications
    ]
    low_confidence_count = int(dispensed_date_confidence == "low") + sum(
        medication.confidence == "low" for medication in medications
    )
    return DocumentOcrReadyResponse(
        batch_id=f"b_{status_response.ocr_job_id}",
        ocr_status=cast(Literal["ready_for_review", "complete"], ocr_status),
        document_image_url=f"/api/v1/ocr/jobs/{status_response.ocr_job_id}/image",
        fields=DocumentOcrFields(
            dispensed_date=DocumentOcrField(
                value=dispensing_date.isoformat() if dispensing_date is not None else None,
                confidence=dispensed_date_confidence,
            )
        ),
        medications=medications,
        low_confidence_count=low_confidence_count,
    )


PublicOcrStatus = Literal["queued", "processing", "ready_for_review", "complete", "failed", "cancelled"]


def _to_public_status(status_name: str) -> PublicOcrStatus:
    status_by_name: dict[str, PublicOcrStatus] = {
        "QUEUED": "queued",
        "PROCESSING": "processing",
        "READY_FOR_REVIEW": "ready_for_review",
        "COMPLETE": "complete",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
    }
    return status_by_name[status_name]


def _confidence_tier(confidence: float) -> Literal["high", "medium", "low"]:
    if confidence >= 0.99:
        return "high"
    if confidence >= 0.90:
        return "medium"
    return "low"


def _public_medication_confidence(
    medication: MedicationReview,
) -> Literal["high", "medium", "low"] | None:
    if medication.confidence is None:
        return None
    if medication.needs_review:
        return "low"
    return _confidence_tier(medication.confidence)
