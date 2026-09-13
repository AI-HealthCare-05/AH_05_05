import asyncio
from io import BytesIO

import pytest
import starlette.formparsers
from httpx import ASGITransport, AsyncClient

from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import OcrJobAcceptedResponse
from app.main import app
from app.models.enums import OcrJobStatus
from app.services import ocr_memory_upload

TEST_USER = object()


class CaptureUploadService:
    def __init__(self) -> None:
        self.submissions: list[dict[str, object]] = []

    async def submit(self, user: object, idempotency_key: str, upload: object) -> OcrJobAcceptedResponse:
        self.submissions.append(
            {
                "user": user,
                "idempotency_key": idempotency_key,
                "filename": getattr(upload, "filename", None),
                "content_type": getattr(upload, "content_type", None),
                "content": await upload.read(),  # type: ignore[union-attr]
                "file_is_bytes_io": isinstance(getattr(upload, "file", None), BytesIO),
            }
        )
        return OcrJobAcceptedResponse(
            ocr_job_id="42",
            status=OcrJobStatus.QUEUED,
            status_url="/api/v1/ocr/jobs/42",
        )


async def _override_user() -> object:
    return TEST_USER


def _install_overrides(service: CaptureUploadService) -> None:
    app.dependency_overrides[get_request_user] = _override_user
    app.dependency_overrides[get_medication_guide_ocr_job_service] = lambda: service


async def _post_upload(client: AsyncClient, files: object) -> object:
    return await client.post(
        "/api/v1/ocr",
        files=files,
        headers={"Idempotency-Key": "memory-upload-key"},
    )


async def test_ocr_route_keeps_a_multipart_file_larger_than_starlette_spool_limit_in_memory(monkeypatch) -> None:
    """Fails if the route falls back to Starlette's SpooledTemporaryFile parser."""

    service = CaptureUploadService()
    _install_overrides(service)

    def fail_if_tempfile_is_created(*args: object, **kwargs: object) -> object:
        raise AssertionError("OCR upload must not create a SpooledTemporaryFile")

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", fail_if_tempfile_is_created)
    payload = b"x" * (1024 * 1024 + 1)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _post_upload(client, {"file": ("guide.png", payload, "image/png")})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {"batchId": "b_42", "documentIds": [42], "ocrStatus": "queued"}
    assert service.submissions == [
        {
            "user": TEST_USER,
            "idempotency_key": "memory-upload-key",
            "filename": "guide.png",
            "content_type": "image/png",
            "content": payload,
            "file_is_bytes_io": True,
        }
    ]


async def test_ocr_route_authenticates_before_reading_a_large_multipart_body(monkeypatch) -> None:
    """Fails if a missing credential allows the multipart parser to consume the body first."""

    def fail_if_tempfile_is_created(*args: object, **kwargs: object) -> object:
        raise AssertionError("an unauthenticated OCR request must not be parsed")

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", fail_if_tempfile_is_created)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ocr",
            files={"file": ("guide.png", b"x" * (1024 * 1024 + 1), "image/png")},
            headers={"Idempotency-Key": "memory-upload-key"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_ocr_route_admits_only_two_in_memory_uploads_until_one_is_closed(monkeypatch) -> None:
    """Fails if a third concurrent request starts parsing before one admitted upload has closed."""

    class BlockingUploadService:
        def __init__(self) -> None:
            self.entered: asyncio.Queue[int] = asyncio.Queue()
            self.release = [asyncio.Event() for _ in range(3)]
            self.submission_count = 0

        async def submit(self, user: object, idempotency_key: str, upload: object) -> OcrJobAcceptedResponse:
            index = self.submission_count
            self.submission_count += 1
            await self.entered.put(index)
            await self.release[index].wait()
            return OcrJobAcceptedResponse(
                ocr_job_id=str(index + 1),
                status=OcrJobStatus.QUEUED,
                status_url=f"/api/v1/ocr/jobs/{index + 1}",
            )

    for name in ("ocr_memory_upload_semaphore", "ocr_memory_upload_semaphore_loop"):
        if hasattr(app.state, name):
            delattr(app.state, name)

    parsed = 0
    third_parse_started = asyncio.Event()
    original_parse = ocr_memory_upload.parse_ocr_memory_upload

    async def observe_parse(request):
        nonlocal parsed
        parsed += 1
        if parsed == 3:
            third_parse_started.set()
        return await original_parse(request)

    monkeypatch.setattr(ocr_memory_upload, "parse_ocr_memory_upload", observe_parse)
    service = BlockingUploadService()
    _install_overrides(service)  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = asyncio.create_task(_post_upload(client, {"file": ("one.png", b"one", "image/png")}))
            assert await asyncio.wait_for(service.entered.get(), timeout=1) == 0
            second = asyncio.create_task(_post_upload(client, {"file": ("two.png", b"two", "image/png")}))
            assert await asyncio.wait_for(service.entered.get(), timeout=1) == 1
            third = asyncio.create_task(_post_upload(client, {"file": ("three.png", b"three", "image/png")}))

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(third_parse_started.wait(), timeout=0.1)
            assert parsed == 2

            service.release[0].set()
            await asyncio.wait_for(third_parse_started.wait(), timeout=1)
            assert parsed == 3

            service.release[1].set()
            service.release[2].set()
            responses = await asyncio.gather(first, second, third)
    finally:
        for event in service.release:
            event.set()
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [202, 202, 202]


async def test_ocr_preview_routes_admit_only_two_parallel_memory_loads_until_a_response_is_sent() -> None:
    """Fails if a third preview loads its bytes before an admitted response has completed."""

    class BlockingPreviewService:
        def __init__(self) -> None:
            self.entered: asyncio.Queue[int] = asyncio.Queue()
            self.release = [asyncio.Event() for _ in range(3)]
            self.load_count = 0

        async def _read(self, media_type: str) -> tuple[bytes, str]:
            index = self.load_count
            self.load_count += 1
            await self.entered.put(index)
            await self.release[index].wait()
            return f"preview-{index}".encode(), media_type

        async def read_input_bytes(self, user: object, job_id: int) -> tuple[bytes, str]:
            return await self._read("image/png")

        async def read_processed_bytes(self, user: object, job_id: int) -> tuple[bytes, str]:
            return await self._read("image/jpeg")

    for name in ("ocr_memory_upload_semaphore", "ocr_memory_upload_semaphore_loop"):
        if hasattr(app.state, name):
            delattr(app.state, name)

    service = BlockingPreviewService()
    _install_overrides(service)  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = asyncio.create_task(client.get("/api/v1/ocr/jobs/1/image"))
            assert await asyncio.wait_for(service.entered.get(), timeout=1) == 0
            second = asyncio.create_task(client.get("/api/v1/ocr/jobs/2/processed-image"))
            assert await asyncio.wait_for(service.entered.get(), timeout=1) == 1
            third = asyncio.create_task(client.get("/api/v1/ocr/jobs/3/image"))

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(service.entered.get(), timeout=0.1)
            assert service.load_count == 2

            service.release[0].set()
            first_response = await asyncio.wait_for(first, timeout=1)
            assert first_response.content == b"preview-0"
            assert await asyncio.wait_for(service.entered.get(), timeout=1) == 2

            service.release[1].set()
            service.release[2].set()
            second_response, third_response = await asyncio.gather(second, third)
    finally:
        for event in service.release:
            event.set()
        app.dependency_overrides.clear()

    assert [second_response.content, third_response.content] == [b"preview-1", b"preview-2"]


async def test_ocr_preview_memory_slots_are_released_after_load_errors() -> None:
    """Fails if two failed preview loads exhaust the shared in-memory admission gate."""

    from app.core.exceptions import OcrJobNotFoundError

    class ErrorThenSuccessPreviewService:
        def __init__(self) -> None:
            self.calls = 0

        async def read_input_bytes(self, user: object, job_id: int) -> tuple[bytes, str]:
            self.calls += 1
            if self.calls < 3:
                raise OcrJobNotFoundError()
            return b"available", "image/png"

    for name in ("ocr_memory_upload_semaphore", "ocr_memory_upload_semaphore_loop"):
        if hasattr(app.state, name):
            delattr(app.state, name)

    service = ErrorThenSuccessPreviewService()
    _install_overrides(service)  # type: ignore[arg-type]
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/api/v1/ocr/jobs/1/image")
            second = await client.get("/api/v1/ocr/jobs/2/image")
            third = await asyncio.wait_for(client.get("/api/v1/ocr/jobs/3/image"), timeout=1)
    finally:
        app.dependency_overrides.clear()

    assert [first.status_code, second.status_code] == [404, 404]
    assert third.status_code == 200
    assert third.content == b"available"


async def test_ocr_route_rejects_duplicate_file_parts_with_the_api_error_envelope() -> None:
    """Fails if a second file can be parsed or errors outside the public envelope."""

    service = CaptureUploadService()
    _install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _post_upload(
                client,
                [
                    ("file", ("one.png", b"one", "image/png")),
                    ("file", ("two.png", b"two", "image/png")),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == "file"
    assert service.submissions == []


async def test_ocr_route_rejects_malformed_multipart_with_the_api_error_envelope() -> None:
    """Fails if malformed multipart reaches the OCR service or leaks Starlette's default error body."""

    service = CaptureUploadService()
    _install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ocr",
                content=b"--broken\r\nnot-a-valid-part\r\n--broken--\r\n",
                headers={
                    "Content-Type": "multipart/form-data; boundary=broken",
                    "Idempotency-Key": "memory-upload-key",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == "file"
    assert service.submissions == []


async def test_ocr_route_rejects_a_body_that_exceeds_its_in_memory_cap(monkeypatch) -> None:
    """Fails if the route can retain a body beyond its route-local bounded-memory limit."""

    monkeypatch.setattr(ocr_memory_upload, "MAX_OCR_REQUEST_BYTES", 512)
    monkeypatch.setattr(ocr_memory_upload, "MAX_OCR_FILE_BYTES", 400)
    service = CaptureUploadService()
    _install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _post_upload(client, {"file": ("guide.png", b"x" * 600, "image/png")})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 413
    assert response.json()["code"] == "OCR_UPLOAD_TOO_LARGE"
    assert service.submissions == []


async def test_ocr_route_accepts_the_existing_single_file_multipart_contract() -> None:
    """Fails if the in-memory parser changes the established OCR upload contract."""

    service = CaptureUploadService()
    _install_overrides(service)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await _post_upload(client, {"file": ("guide.png", b"image", "image/png")})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert service.submissions[0]["content"] == b"image"


def test_ocr_route_keeps_the_multipart_file_openapi_contract() -> None:
    request_body = app.openapi()["paths"]["/api/v1/ocr"]["post"]["requestBody"]

    assert request_body["required"] is True
    assert request_body["content"]["multipart/form-data"]["schema"] == {
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {
                "type": "string",
                "format": "binary",
                "description": "JPG 또는 PNG 조제약 복약안내 이미지",
            }
        },
    }
