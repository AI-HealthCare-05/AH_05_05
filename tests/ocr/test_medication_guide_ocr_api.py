import copy
import json
from io import BytesIO
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.apis.v1.medication_guide_ocr_router import get_medication_guide_service
from app.dependencies.security import get_request_user
from app.main import app
from app.services.medication_guide_ocr import MedicationGuideService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "template_ocr_exact_02_response.json"
MAX_OCR_MULTIPART_REQUEST_BYTES = 51 * 1024 * 1024


def png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (40, 30), "white").save(stream, format="PNG")
    return stream.getvalue()


def load_fixture() -> dict[str, object]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class FixtureProvider:
    async def extract(self, image: object) -> object:
        assert getattr(image, "provider_format", None) == "png"
        return copy.deepcopy(load_fixture())


def override_service() -> MedicationGuideService:
    return MedicationGuideService(
        provider=FixtureProvider(),
        template_id=43199,
        review_threshold=0.9,
    )


async def override_user() -> object:
    return object()


def test_openapi_documents_ocr_runtime_error_contract() -> None:
    responses = app.openapi()["paths"]["/api/v1/ocr/medication-guides"]["post"]["responses"]

    expected_error_codes = {
        "413": ("OCR_UPLOAD_TOO_LARGE",),
        "422": (
            "VALIDATION_ERROR",
            "INVALID_IMAGE",
            "TEMPLATE_NOT_MATCHED",
            "NO_MEDICATIONS_FOUND",
        ),
        "502": ("OCR_PROVIDER_ERROR",),
        "503": ("PROVIDER_CONFIG_MISSING",),
        "504": ("OCR_PROVIDER_TIMEOUT",),
    }

    assert set(responses) == {"200", *expected_error_codes}
    for status_code, error_codes in expected_error_codes.items():
        response = responses[status_code]
        assert response["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/OcrErrorResponse"}
        assert all(error_code in response["description"] for error_code in error_codes)


async def test_ocr_endpoint_validates_image_and_returns_normalized_result() -> None:
    app.dependency_overrides[get_request_user] = override_user
    app.dependency_overrides[get_medication_guide_service] = override_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", png_bytes(), "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["schemaVersion"] == "medication-guide-template/v2"
    assert payload["dispensingDate"] == "2025-04-02"
    assert len(payload["medications"]) == 4
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_invalid_image_uses_project_error_contract() -> None:
    app.dependency_overrides[get_request_user] = override_user
    app.dependency_overrides[get_medication_guide_service] = override_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", b"broken", "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {
        "code": "INVALID_IMAGE",
        "message": "유효한 JPG 또는 PNG 이미지를 선택해 주세요.",
    }


async def test_oversized_ocr_request_is_rejected_before_multipart_parsing() -> None:
    app.dependency_overrides[get_request_user] = override_user
    app.dependency_overrides[get_medication_guide_service] = override_service
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr/medication-guides",
                files={"file": ("guide.png", png_bytes(), "image/png")},
                headers={"Content-Length": str(MAX_OCR_MULTIPART_REQUEST_BYTES + 1)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    assert response.json() == {
        "code": "OCR_UPLOAD_TOO_LARGE",
        "message": "OCR 요청 크기는 51MB를 초과할 수 없습니다.",
    }
