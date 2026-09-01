from datetime import datetime, timedelta
from io import BytesIO

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.core import config
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

    async def read_processed_bytes(self, user: object, job_id: int) -> tuple[bytes, str]:
        assert user is TEST_USER
        assert job_id == 42
        return b"processed-jpeg", "image/jpeg"


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
                "/api/v1/ocr",
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
                "/api/v1/ocr",
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
    submit_responses = paths["/api/v1/ocr"]["post"]["responses"]

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
    assert "/api/v1/ocr/medication-guides" not in paths
    assert "/api/v1/ocr/jobs/{job_id}/confirm" not in paths


def test_ocr_file_routes_extend_timeout_without_weakening_fast_job_routes() -> None:
    route_timeouts: dict[tuple[str, str], float | None] = {}
    target_paths = {
        "/api/v1/ocr",
        "/api/v1/ocr/jobs/{ocrJobId}",
        "/api/v1/ocr/jobs/{ocrJobId}/image",
        "/api/v1/ocr/jobs/{ocrJobId}/processed-image",
    }
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if path not in target_paths:
            continue
        timeout = getattr(route.endpoint, "__api_timeout_seconds__", None)
        for method in getattr(route, "methods", set()):
            route_timeouts[(method, path)] = timeout

    assert route_timeouts == {
        ("POST", "/api/v1/ocr"): 10.0,
        ("GET", "/api/v1/ocr/jobs/{ocrJobId}"): None,
        ("PATCH", "/api/v1/ocr/jobs/{ocrJobId}"): None,
        ("GET", "/api/v1/ocr/jobs/{ocrJobId}/image"): 10.0,
        ("GET", "/api/v1/ocr/jobs/{ocrJobId}/processed-image"): 10.0,
    }


def test_openapi_documents_ocr_timeout_and_public_text_limits() -> None:
    openapi = app.openapi()
    paths = openapi["paths"]
    timeout_operations = (
        paths["/api/v1/ocr"]["post"],
        paths["/api/v1/ocr/jobs/{ocrJobId}/image"]["get"],
        paths["/api/v1/ocr/jobs/{ocrJobId}/processed-image"]["get"],
    )
    expected_error_schema = {"$ref": "#/components/schemas/OcrErrorResponse"}
    for operation in timeout_operations:
        assert operation["responses"]["504"]["content"]["application/json"]["schema"] == expected_error_schema

    schemas = openapi["components"]["schemas"]
    for schema_name in ("DocumentOcrMedication", "DocumentMedicationConfirmation"):
        properties = schemas[schema_name]["properties"]
        assert properties["name"]["maxLength"] == 100
        assert properties["strength"]["maxLength"] == 50
        assert properties["doseQuantity"]["maxLength"] == 50


def test_openapi_documents_ocr_path_validation_with_the_runtime_error_contract() -> None:
    paths = app.openapi()["paths"]
    expected_schema = {"$ref": "#/components/schemas/OcrErrorResponse"}

    operations = (
        paths["/api/v1/ocr/jobs/{ocrJobId}"]["get"],
        paths["/api/v1/ocr/jobs/{ocrJobId}"]["patch"],
        paths["/api/v1/ocr/jobs/{ocrJobId}/image"]["get"],
        paths["/api/v1/ocr/jobs/{ocrJobId}/processed-image"]["get"],
    )

    for operation in operations:
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == expected_schema


def test_openapi_documents_ocr_images_as_binary_responses() -> None:
    image_content = app.openapi()["paths"]["/api/v1/ocr/jobs/{ocrJobId}/image"]["get"]["responses"]["200"]["content"]
    processed_content = app.openapi()["paths"]["/api/v1/ocr/jobs/{ocrJobId}/processed-image"]["get"]["responses"]["200"]["content"]
    expected_schema = {"type": "string", "format": "binary"}

    assert image_content["image/jpeg"]["schema"] == expected_schema
    assert image_content["image/png"]["schema"] == expected_schema
    assert processed_content["image/jpeg"]["schema"] == expected_schema


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
        "strength",
        "doseQuantity",
        "timesPerDay",
        "days",
    }
    assert example["medications"][0]["strength"] == "20mg"
    assert example["medications"][0]["doseQuantity"] == "1캡슐"


async def test_ocr_upload_returns_the_frontend_envelope_for_a_single_file() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.QUEUED))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr",
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
        fields={"dispensedDate": {"value": "2026-08-25", "confidence": "medium"}},
        medications=[
            MedicationReview(
                temp_id="med-1",
                name="고신뢰 약",
                strength="500mg",
                dose_quantity="1정",
                times_per_day=3,
                days=5,
                confidence="high",
            ),
            MedicationReview(
                temp_id="med-2",
                name="중신뢰 약",
                times_per_day=2,
                confidence="medium",
            ),
            MedicationReview(
                temp_id="med-3",
                name="저신뢰 약",
                confidence="low",
            ),
        ],
        low_confidence_count=1,
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
        "fields": {"dispensedDate": {"value": "2026-08-25", "confidence": "medium"}},
        "medications": [
            {
                "tempId": "med-1",
                "name": "고신뢰 약",
                "strength": "500mg",
                "doseQuantity": "1정",
                "timesPerDay": 3,
                "days": 5,
                "confidence": "high",
            },
            {
                "tempId": "med-2",
                "name": "중신뢰 약",
                "timesPerDay": 2,
                "confidence": "medium",
            },
            {
                "tempId": "med-3",
                "name": "저신뢰 약",
                "confidence": "low",
            },
        ],
        "lowConfidenceCount": 1,
    }


async def test_document_ocr_marks_missing_date_and_unresolved_frequency_as_low_confidence() -> None:
    review = MedicationGuideReviewResult(
        fields={},
        medications=[
            MedicationReview(
                temp_id="med-1",
                name="횟수 확인 필요 약",
                days=5,
                confidence="low",
            ),
            MedicationReview(
                temp_id="med-2",
                name="파싱 확인 필요 약",
                times_per_day=3,
                days=5,
                confidence="low",
            ),
        ],
        low_confidence_count=3,
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
    assert payload["fields"] == {}
    assert "timesPerDay" not in payload["medications"][0]
    assert [medication["confidence"] for medication in payload["medications"]] == ["low", "low"]
    assert payload["lowConfidenceCount"] == 3


async def test_completed_document_ocr_omits_missing_prn_frequency_from_the_public_result() -> None:
    review = MedicationGuideReviewResult(
        fields={"dispensedDate": {"value": "2026-08-25", "confidence": "high"}},
        medications=[
            MedicationReview(
                temp_id="med-prn",
                name="필요 시 약",
                days=5,
                confidence="high",
            )
        ],
        low_confidence_count=0,
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
    payload = response.json()
    assert "timesPerDay" not in payload["medications"][0]
    assert payload["medications"][0]["confidence"] == "high"
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
        fields={"dispensedDate": {"value": "2026-08-25", "confidence": "high"}},
        medications=[],
        low_confidence_count=0,
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
        fields={"dispensedDate": {"value": "2026-08-25", "confidence": "high"}},
        medications=[
            MedicationReview(
                temp_id="med-1",
                name="OCR 약",
                times_per_day=3,
                days=5,
                confidence="high",
            ),
            MedicationReview(
                temp_id="user-2",
                name="사용자 추가 약",
                times_per_day=1,
                days=3,
                confidence=None,
            ),
        ],
        low_confidence_count=0,
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
                "strength": "500mg",
                "doseQuantity": "1.5정",
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
    assert medication.strength == "500mg"
    assert medication.dose_quantity == "1.5정"


async def test_document_confirmation_rejects_confidence_and_removed_clinical_fields() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            confidence = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약", "confidence": "high"}],
                },
            )
            clinical = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약", "efficacy": "효능"}],
                },
            )
            legacy_dose_object = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약", "doseQuantity": {"value": 1}}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert confidence.status_code == 422
    assert clinical.status_code == 422
    assert legacy_dose_object.status_code == 422


async def test_document_confirmation_enforces_public_text_lengths() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW))
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            too_long_name = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약" * 101}],
                },
            )
            too_long_strength = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약", "strength": "1" * 51}],
                },
            )
            too_long_dose_quantity = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={
                    "dispensedDate": "2026-08-25",
                    "medications": [{"tempId": "med-1", "name": "약", "doseQuantity": "1" * 51}],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert too_long_name.status_code == 422
    assert too_long_strength.status_code == 422
    assert too_long_dose_quantity.status_code == 422
    assert service.confirmations == []


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


async def test_processed_document_image_is_private_and_returns_exact_bytes() -> None:
    service = FakeJobService()
    install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ocr/jobs/42/processed-image")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"processed-jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_document_confirmation_accepts_no_medications_and_the_future_date_boundary() -> None:
    service = PublicOcrFakeJobService(OcrJobStatusResponse(ocr_job_id="42", status=OcrJobStatus.READY_FOR_REVIEW))
    install_overrides(service)
    today = datetime.now(config.TIMEZONE).date()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            empty = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={"dispensedDate": "2026-08-25", "medications": []},
            )
            future_day_31 = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={"dispensedDate": (today + timedelta(days=31)).isoformat(), "medications": []},
            )
            future_day_32 = await client.patch(
                "/api/v1/ocr/jobs/42",
                json={"dispensedDate": (today + timedelta(days=32)).isoformat(), "medications": []},
            )
    finally:
        app.dependency_overrides.clear()

    assert empty.status_code == 200
    assert empty.json()["hasMedication"] is False
    assert future_day_31.status_code == 200
    assert future_day_32.status_code == 422
