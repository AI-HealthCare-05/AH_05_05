from datetime import datetime
from io import BytesIO

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import (
    MedicationGuideConfirmRequest,
    MedicationGuideReviewResult,
    MedicationReview,
    OcrConfirmationResponse,
    OcrJobAcceptedResponse,
    OcrJobStatusResponse,
)
from app.main import app
from app.models.enums import OcrJobStatus


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (40, 30), "white").save(stream, format="PNG")
    return stream.getvalue()


class FakeJobService:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []
        self.confirmations: list[tuple[int, MedicationGuideConfirmRequest]] = []

    async def submit(self, user: object, idempotency_key: str, upload: object) -> OcrJobAcceptedResponse:
        self.submissions.append(
            {
                "user": user,
                "idempotency_key": idempotency_key,
                "filename": getattr(upload, "filename", None),
                "media_type": getattr(upload, "content_type", None),
                "content": await upload.read(),  # type: ignore[union-attr]
            }
        )
        return OcrJobAcceptedResponse(
            ocr_job_id="42",
            status=OcrJobStatus.QUEUED,
            status_url="/api/v1/ocr/jobs/42",
        )

    async def get(self, user: object, job_id: int) -> OcrJobStatusResponse:
        assert user is TEST_USER
        assert job_id == 42
        return OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.PROCESSING)

    async def confirm(
        self, user: object, job_id: int, request: MedicationGuideConfirmRequest
    ) -> OcrConfirmationResponse:
        assert user is TEST_USER
        self.confirmations.append((job_id, request))
        return OcrConfirmationResponse(
            ocr_job_id="42",
            care_episode_id="99",
            confirmed_at=datetime.fromisoformat("2026-08-25T14:10:00+09:00"),
        )

    async def read_input_bytes(self, user: object, job_id: int) -> tuple[bytes, str]:
        assert user is TEST_USER
        assert job_id == 42
        return png_bytes(), "image/png"


class PublicOcrFakeJobService(FakeJobService):
    def __init__(self, status_response: OcrJobStatusResponse) -> None:
        super().__init__()
        self.status_response = status_response

    async def get(self, user: object, job_id: int) -> OcrJobStatusResponse:
        assert user is TEST_USER
        assert job_id == 42
        return self.status_response


TEST_USER = object()


async def override_user() -> object:
    return TEST_USER


def install_overrides(service: FakeJobService) -> None:
    app.dependency_overrides[get_request_user] = override_user
    app.dependency_overrides[get_medication_guide_ocr_job_service] = lambda: service


async def test_submit_accepts_one_image_and_returns_queued_job() -> None:
    service = FakeJobService()
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", png_bytes(), "image/png")},
                headers={"Idempotency-Key": "request-key-123"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"batchId": "b_42", "documentIds": [42], "ocrStatus": "queued"}
    assert service.submissions == [
        {
            "user": TEST_USER,
            "idempotency_key": "request-key-123",
            "filename": "guide.png",
            "media_type": "image/png",
            "content": png_bytes(),
        }
    ]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_submit_requires_a_valid_idempotency_key() -> None:
    service = FakeJobService()
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", png_bytes(), "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == "idempotency-key"


async def test_job_status_is_retrieved_for_the_authenticated_user() -> None:
    service = FakeJobService()
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"batchId": "b_42", "ocrStatus": "processing"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_endpoints_require_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/ocr/jobs/42")

    assert response.status_code == 401


async def test_service_app_error_uses_the_global_error_contract() -> None:
    from app.core.exceptions import OcrJobNotFoundError

    class MissingJobService(FakeJobService):
        async def get(self, user: object, job_id: int) -> OcrJobStatusResponse:
            raise OcrJobNotFoundError()

    install_overrides(MissingJobService())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"code": "OCR_JOB_NOT_FOUND", "message": "OCR 작업을 찾을 수 없습니다."}


def test_openapi_exposes_only_the_unified_ocr_contract() -> None:
    paths = app.openapi()["paths"]
    submit_responses = paths["/api/v1/ocr/medication-guides"]["post"]["responses"]

    assert "200" not in submit_responses
    assert submit_responses["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentOcrUploadResponse"
    }
    job_path = paths["/api/v1/ocr/jobs/{ocrJobId}"]
    status_schema = job_path["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert status_schema["discriminator"]["propertyName"] == "ocrStatus"
    assert set(status_schema["discriminator"]["mapping"]) == {
        "cancelled",
        "queued",
        "processing",
        "ready_for_review",
        "complete",
        "failed",
    }
    assert job_path["patch"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentOcrConfirmResponse"
    }
    assert "/api/v1/documents" not in paths
    assert "/api/v1/ocr/jobs/{job_id}/confirm" not in paths


def test_openapi_shows_a_realistic_confirmation_request_instead_of_placeholders() -> None:
    confirmation_content = app.openapi()["paths"]["/api/v1/ocr/jobs/{ocrJobId}"]["patch"]["requestBody"]["content"][
        "application/json"
    ]

    example = confirmation_content["examples"]["confirmedOcrResult"]["value"]
    assert example["dispensedDate"] == "2026-08-25"
    assert len(example["medications"]) == 4
    assert set(example["medications"][0]) == {
        "tempId",
        "name",
        "dose",
        "efficacy",
        "administration",
        "precautions",
        "timesPerDay",
        "days",
    }
    assert example["medications"][0]["efficacy"] == "위산 과다, 속쓰림, 역류 증상 완화"
    assert example["medications"][0]["precautions"] == (
        "캡슐을 씹거나 열지 마세요. 복통이나 설사가 지속되면 상담하세요."
    )


async def test_ocr_upload_returns_the_frontend_envelope_for_a_single_file() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.QUEUED))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", png_bytes(), "image/png")},
                headers={"Idempotency-Key": "request-key-456"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"batchId": "b_42", "documentIds": [42], "ocrStatus": "queued"}
    assert service.submissions[0]["filename"] == "guide.png"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_document_ocr_returns_a_ready_result_with_confidence_tiers_and_exact_low_count() -> None:
    review = MedicationGuideReviewResult(
        dispensing_date="2026-08-25",
        dispensing_date_confidence=0.89,
        medications=[
            MedicationReview(
                row_id="med-1",
                name="고신뢰 약",
                dose="1회 1정",
                efficacy="염증과 통증 완화",
                administration="식후",
                precautions="위장장애가 있으면 상담하세요.",
                times_per_day=3,
                days=5,
                confidence=0.99,
                needs_review=False,
            ),
            MedicationReview(
                row_id="med-2",
                name="중신뢰 약",
                dose="1회 2정",
                administration="점심 식후",
                times_per_day=2,
                days=3,
                confidence=0.90,
                needs_review=False,
            ),
            MedicationReview(
                row_id="med-3",
                name="저신뢰 약",
                dose="필요 시",
                administration="통증 시",
                times_per_day=None,
                days=None,
                confidence=0.899,
                needs_review=True,
            ),
        ],
    )
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW, result=review)
    )
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "batchId": "b_42",
        "ocrStatus": "ready_for_review",
        "documentImageUrl": "/api/v1/ocr/jobs/42/image",
        "fields": {"dispensedDate": {"value": "2026-08-25", "confidence": "low"}},
        "medications": [
            {
                "tempId": "med-1",
                "name": "고신뢰 약",
                "dose": "1회 1정",
                "efficacy": "염증과 통증 완화",
                "administration": "식후",
                "precautions": "위장장애가 있으면 상담하세요.",
                "timesPerDay": 3,
                "days": 5,
                "confidence": "high",
            },
            {
                "tempId": "med-2",
                "name": "중신뢰 약",
                "dose": "1회 2정",
                "efficacy": "",
                "administration": "점심 식후",
                "precautions": "",
                "timesPerDay": 2,
                "days": 3,
                "confidence": "medium",
            },
            {
                "tempId": "med-3",
                "name": "저신뢰 약",
                "dose": "필요 시",
                "efficacy": "",
                "administration": "통증 시",
                "precautions": "",
                "timesPerDay": None,
                "days": None,
                "confidence": "low",
            },
        ],
        "lowConfidenceCount": 2,
    }


async def test_document_ocr_marks_missing_date_and_unresolved_frequency_as_low_confidence() -> None:
    review = MedicationGuideReviewResult(
        dispensing_date=None,
        dispensing_date_confidence=0.999,
        medications=[
            MedicationReview(
                row_id="med-1",
                name="횟수 확인 필요 약",
                times_per_day=None,
                days=5,
                confidence=0.999,
                needs_review=True,
            ),
            MedicationReview(
                row_id="med-2",
                name="파싱 확인 필요 약",
                times_per_day=3,
                days=5,
                confidence=0.999,
                needs_review=True,
            ),
        ],
    )
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW, result=review)
    )
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["fields"]["dispensedDate"] == {"value": None, "confidence": "low"}
    assert [medication["confidence"] for medication in payload["medications"]] == ["low", "low"]
    assert payload["lowConfidenceCount"] == 3


async def test_document_ocr_keeps_explicit_prn_out_of_the_low_confidence_count() -> None:
    review = MedicationGuideReviewResult(
        dispensing_date="2026-08-25",
        dispensing_date_confidence=0.99,
        medications=[
            MedicationReview(
                row_id="med-prn",
                name="필요 시 약",
                administration="통증 시 6시간 이상 간격",
                times_per_day=None,
                days=5,
                confidence=0.95,
                needs_review=False,
            )
        ],
    )
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW, result=review)
    )
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["medications"][0]["timesPerDay"] is None
    assert payload["medications"][0]["confidence"] == "medium"
    assert payload["lowConfidenceCount"] == 0


async def test_document_ocr_omits_result_keys_while_the_job_is_not_ready() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.PROCESSING))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"batchId": "b_42", "ocrStatus": "processing"}


async def test_document_ocr_failed_status_exposes_its_machine_readable_error_code() -> None:
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(
            ocr_job_id="42",
            status=OcrJobStatus.FAILED,
            error_code="EXTRACTION_FAILED",
        )
    )
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "batchId": "b_42",
        "ocrStatus": "failed",
        "errorCode": "EXTRACTION_FAILED",
    }


async def test_document_ocr_keeps_the_result_after_completion() -> None:
    review = MedicationGuideReviewResult(
        dispensing_date="2026-08-25",
        dispensing_date_confidence=0.99,
        medications=[],
    )
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.COMPLETE, result=review)
    )
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["ocrStatus"] == "complete"
    assert response.json()["fields"]["dispensedDate"]["confidence"] == "high"


async def test_document_ocr_omits_confidence_for_a_user_added_completed_medication() -> None:
    review = MedicationGuideReviewResult(
        dispensing_date="2026-08-25",
        dispensing_date_confidence=0.99,
        medications=[
            MedicationReview(
                row_id="med-1",
                name="OCR 약",
                times_per_day=3,
                days=5,
                confidence=0.99,
                needs_review=False,
            ),
            MedicationReview(
                row_id="user-2",
                name="사용자 추가 약",
                dose="",
                efficacy=None,
                administration="",
                precautions=None,
                times_per_day=1,
                days=3,
                confidence=None,
                needs_review=False,
            ),
        ],
        review_issues=[],
    )
    service = PublicOcrFakeJobService(
        OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.COMPLETE, result=review)
    )
    install_overrides(service)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/ocr/jobs/42")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    medications = response.json()["medications"]
    assert medications[0]["confidence"] == "high"
    assert "confidence" not in medications[1]


async def test_document_ocr_confirmation_adapts_the_public_body_to_the_job_service() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW))
    install_overrides(service)
    body = {
        "dispensedDate": "2026-08-25",
        "medications": [
            {
                "tempId": "med-1",
                "name": "약품명",
                "dose": "1회 1정",
                "efficacy": "해열 및 진통",
                "administration": "식후 복용",
                "precautions": "음주를 피하세요.",
                "timesPerDay": 3,
                "days": 5,
            }
        ],
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch("/api/v1/ocr/jobs/42", json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"recordId": 99, "hasMedication": True, "statusCode": "active"}
    assert service.confirmations[0][1].dispensing_date.isoformat() == "2026-08-25"
    medication = service.confirmations[0][1].medications[0]
    assert medication.efficacy == "해열 및 진통"
    assert medication.administration == "식후 복용"
    assert medication.precautions == "음주를 피하세요."


async def test_document_image_is_owner_scoped_and_returns_private_exact_bytes() -> None:
    service = FakeJobService()
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42/image")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == png_bytes()
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "token" not in str(response.request.url)


async def test_document_image_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/ocr/jobs/42/image")

    assert response.status_code == 401


async def test_document_confirmation_accepts_no_medications_and_rejects_a_future_date() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            empty = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={"dispensedDate": "2026-08-25", "medications": []},
            )
            future = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={"dispensedDate": "2999-01-01", "medications": []},
            )
    finally:
        app.dependency_overrides.clear()

    assert empty.status_code == 200
    assert empty.json()["hasMedication"] is False
    assert future.status_code == 422
