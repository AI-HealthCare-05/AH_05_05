import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from arq import Retry
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers
from tortoise.contrib.test import TestCase
from tortoise.exceptions import OperationalError

from app.core import config
from app.core.exceptions import (
    OcrIdempotencyConflictError,
    OcrJobNotFoundError,
    OcrJobStateConflictError,
    OcrQueueUnavailableError,
)
from app.dtos.medication_guide_ocr import (
    Medication as ExtractedMedication,
)
from app.dtos.medication_guide_ocr import (
    MedicationGuideConfirmRequest,
    MedicationGuideOcrJobStatus,
    MedicationGuideResult,
)
from app.models.care import CareEpisode
from app.models.enums import AccountStatus, MealSlot, OcrJobStatus
from app.models.medications import Medication, MedicationDose, MedicationNote
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr_jobs import (
    MedicationGuideOcrJobService,
    TemporaryOcrStorage,
    build_review_result,
)


def png_bytes(color: str = "white") -> bytes:
    stream = BytesIO()
    Image.new("RGB", (40, 30), color).save(stream, format="PNG")
    return stream.getvalue()


def upload(content: bytes | None = None) -> UploadFile:
    return UploadFile(
        file=BytesIO(content or png_bytes()),
        filename="guide.png",
        headers=Headers({"content-type": "image/png"}),
    )


async def create_user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="hashed-password",
        status=AccountStatus.ACTIVE,
        name="OCR 테스트 사용자",
    )


def confirm_request(*, name: str = "수정한 약품 10mg", alias: str | None = None) -> MedicationGuideConfirmRequest:
    payload: dict[str, object] = {
        "dispensingDate": "2026-08-25",
        "medications": [
            {
                "tempId": "med-1",
                "name": name,
                "strength": "10mg",
                "doseQuantity": "1.5정",
                "timesPerDay": 3,
                "days": 5,
            },
            {"tempId": "user-2", "name": "추가한 약품", "timesPerDay": 1, "days": 3},
            {"tempId": "user-3", "name": "필요 시 약품", "timesPerDay": None},
        ],
    }
    if alias is not None:
        payload["alias"] = alias
    return MedicationGuideConfirmRequest.model_validate(payload)


def test_review_projection_marks_values_outside_public_ranges_for_review() -> None:
    extracted = MedicationGuideResult(
        medications=[
            ExtractedMedication(
                row_id="med-1",
                name="범위 초과 약품",
                times_per_day=7,
                days=400,
                confidence=0.99,
                needs_review=False,
                source_field_names=[],
            )
        ]
    )

    review = build_review_result(extracted)
    payload = review.model_dump(mode="json", by_alias=True)

    assert "timesPerDay" not in payload["medications"][0]
    assert "days" not in payload["medications"][0]
    assert payload["medications"][0]["confidence"] == "low"
    assert payload["lowConfidenceCount"] == 2


class FakeRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        self.enqueued.append((args, kwargs))
        return object()


class FailingRedis(FakeRedis):
    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis unavailable")


def successful_stages() -> list[dict[str, object]]:
    return [
        {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
        {"name": "ocr", "status": "succeeded", "elapsedMs": 20, "callCount": 1},
        {"name": "candidate", "status": "succeeded", "elapsedMs": 2, "callCount": 0},
        {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "validate", "status": "succeeded", "elapsedMs": 1, "callCount": 0},
    ]


def provider_failure_stages(*, code: str = "OCR_TIMEOUT") -> list[dict[str, object]]:
    return [
        {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
        {"name": "ocr", "status": "failed", "elapsedMs": 20, "callCount": 1, "code": code},
        {"name": "candidate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
    ]


def fallback_failure_stages(*, code: str) -> list[dict[str, object]]:
    return [
        {"name": "preprocess", "status": "failed", "elapsedMs": 0, "callCount": 0, "code": code},
        {"name": "ocr", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "candidate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
    ]


class FixtureAnalyzer:
    async def analyze(self, _image: object) -> object:
        return SimpleNamespace(
            project_review={
                "fields": {"dispensedDate": {"value": "2025-04-02", "confidence": "high"}},
                "medications": [
                    {
                        "tempId": "med-1",
                        "name": "에스오메프라졸캡슐",
                        "strength": "20mg",
                        "doseQuantity": "1캡슐",
                        "timesPerDay": 1,
                        "days": 14,
                        "confidence": "high",
                        "efficacy": "must not cross the public boundary",
                    },
                    {
                        "tempId": "med-2",
                        "name": "단위 미추출 약",
                        "doseQuantity": "2",
                        "confidence": "medium",
                    },
                ],
                "lowConfidenceCount": 0,
            },
            stages=successful_stages(),
            confidence_values=[0.95, 0.91, 0.69],
            ocr_model="clova-general-v2",
            structuring_model="deterministic-v3",
            prompt_version="medication_grounding_v3",
            schema_version="medication-guide-review/v3",
            requires_recapture=False,
            processed_image_bytes=b"processed-review-jpeg",
        )


class RecaptureAnalyzer(FixtureAnalyzer):
    async def analyze(self, image: object) -> object:
        analysis = await super().analyze(image)
        analysis.project_review = {"fields": {}, "medications": [], "lowConfidenceCount": 0}
        analysis.stages = [
            {
                "name": "preprocess",
                "status": "succeeded",
                "elapsedMs": 4,
                "callCount": 0,
                "code": "RECAPTURE_REQUIRED",
            },
            *(
                {"name": name, "status": "skipped", "elapsedMs": 0, "callCount": 0}
                for name in ("ocr", "candidate", "llm", "validate")
            ),
        ]
        analysis.confidence_values = []
        analysis.requires_recapture = True
        return analysis


class TimeoutThenSuccessAnalyzer(FixtureAnalyzer):
    def __init__(self) -> None:
        self.calls = 0

    async def analyze(self, image: object) -> object:
        from app.core.exceptions import OcrProviderTimeoutError

        self.calls += 1
        if self.calls == 1:
            raise OcrProviderTimeoutError()
        return await super().analyze(image)


class AlwaysTimeoutAnalyzer:
    async def analyze(self, _image: object) -> object:
        from app.core.exceptions import OcrProviderTimeoutError

        error = OcrProviderTimeoutError()
        error.stages = provider_failure_stages()  # type: ignore[attr-defined]
        raise error


class PermanentFailureAnalyzer:
    async def analyze(self, _image: object) -> object:
        from app.core.exceptions import OcrProviderError

        error = OcrProviderError()
        error.stages = provider_failure_stages(code="OCR_PROVIDER_ERROR")  # type: ignore[attr-defined]
        raise error


class UnexpectedFailureAnalyzer:
    async def analyze(self, _image: object) -> object:
        raise RuntimeError("unexpected extraction failure")


class InvalidProjectionAnalyzer(FixtureAnalyzer):
    async def analyze(self, image: object) -> object:
        analysis = await super().analyze(image)
        del analysis.project_review["medications"][0]["confidence"]
        return analysis


class InvalidStageAnalyzer(FixtureAnalyzer):
    async def analyze(self, image: object) -> object:
        analysis = await super().analyze(image)
        analysis.stages[0]["elapsedMs"] = True
        return analysis


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("elapsedMs", True),
        ("elapsedMs", 1.5),
        ("callCount", False),
        ("callCount", "1"),
        ("code", None),
        ("code", "   "),
        ("code", 123),
    ],
)
def test_stage_validation_rejects_non_exact_scalar_types(field: str, value: object) -> None:
    stages = successful_stages()
    stages[0][field] = value

    with pytest.raises(ValueError):
        MedicationGuideOcrJobService._validated_stage_results(stages)


@pytest.mark.parametrize(
    "dose_quantity",
    [
        {"value": 1, "unit": "정"},
        None,
        "",
        "   ",
        "1" * 51,
        1,
        [],
    ],
)
def test_ready_projection_omits_the_entire_invalid_dose_quantity(dose_quantity: object) -> None:
    payload = MedicationGuideOcrJobService._project_review_payload(
        {
            "fields": {},
            "medications": [
                {
                    "tempId": "med-1",
                    "name": "테스트 약",
                    "doseQuantity": dose_quantity,
                    "confidence": "high",
                }
            ],
            "lowConfidenceCount": 0,
        }
    )

    assert payload["medications"][0] == {
        "tempId": "med-1",
        "name": "테스트 약",
        "confidence": "high",
    }


def test_ready_projection_omits_explicit_null_times_per_day() -> None:
    payload = MedicationGuideOcrJobService._project_review_payload(
        {
            "fields": {},
            "medications": [
                {
                    "tempId": "med-prn",
                    "name": "필요 시 약",
                    "timesPerDay": None,
                    "confidence": "high",
                }
            ],
            "lowConfidenceCount": 0,
        }
    )

    assert "timesPerDay" not in payload["medications"][0]


class TestMedicationGuideOcrJobService(TestCase):
    async def test_submit_creates_user_scoped_job_and_reuses_same_file(self) -> None:
        user = await create_user("ocr-submit@example.com")
        redis = FakeRedis()
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=redis)

            first = await service.submit(user, "request-key-123", upload())
            second = await service.submit(user, "request-key-123", upload())

            assert first == second
            assert first.status is MedicationGuideOcrJobStatus.QUEUED
            assert first.ocr_job_id.isdecimal()
            job = await OcrJob.get(id=int(first.ocr_job_id))
            assert job.user_id == user.id
            assert job.care_episode_id is None
            assert job.structuring_model is None
            assert job.prompt_version is None
            assert job.input_manifest["contentSha256"]
            assert Path(directory, str(job.input_manifest["storageKey"])).is_file()
            assert len(redis.enqueued) == 1
            assert redis.enqueued[0][0] == ("process_medication_guide_ocr", job.id)
            assert redis.enqueued[0][1]["_job_id"] == f"ocr:{job.id}"
            assert redis.enqueued[0][1]["_queue_name"] == config.OCR_QUEUE_NAME

            with pytest.raises(OcrIdempotencyConflictError):
                await service.submit(user, "request-key-123", upload(png_bytes("black")))

            other_user = await create_user("ocr-submit-other@example.com")
            other = await service.submit(other_user, "request-key-123", upload())
            assert other.ocr_job_id != first.ocr_job_id
            assert len(redis.enqueued) == 2

    async def test_submit_marks_job_failed_and_removes_image_when_queue_is_unavailable(self) -> None:
        user = await create_user("ocr-queue-failure@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FailingRedis(),
            )

            with pytest.raises(OcrQueueUnavailableError):
                await service.submit(user, "queue-failure-key", upload())

            failed = await OcrJob.get(user=user)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "WORKER_INTERRUPTED"
            assert failed.started_at is not None
            assert list(Path(directory).iterdir()) == []

    async def test_submit_removes_image_when_database_create_fails(self) -> None:
        user = await create_user("ocr-database-failure@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            with patch.object(OcrJob, "create", AsyncMock(side_effect=OperationalError("database unavailable"))):
                with pytest.raises(OperationalError, match="database unavailable"):
                    await service.submit(user, "database-failure-key", upload())

            assert list(Path(directory).iterdir()) == []

    async def test_process_retries_once_then_publishes_review_result_and_preserves_image(self) -> None:
        user = await create_user("ocr-process@example.com")
        redis = FakeRedis()
        analyzer = TimeoutThenSuccessAnalyzer()
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=redis)
            accepted = await service.submit(user, "request-key-456", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            stored_path = Path(directory, str(job.input_manifest["storageKey"]))

            with pytest.raises(Retry):
                await service.process(job.id, analyzer, job_try=1)

            retrying = await OcrJob.get(id=job.id)
            assert retrying.status is OcrJobStatus.PROCESSING
            assert stored_path.is_file()

            await service.process(job.id, analyzer, job_try=2)

            ready = await OcrJob.get(id=job.id)
            assert ready.status is OcrJobStatus.READY_FOR_REVIEW
            assert ready.ready_at is not None
            assert ready.expires_at == ready.ready_at + timedelta(minutes=60)
            assert ready.structured_result["medications"][0]["name"] == "에스오메프라졸캡슐"
            assert ready.structured_result["medications"][0]["strength"] == "20mg"
            assert ready.structured_result["medications"][0]["doseQuantity"] == "1캡슐"
            assert set(ready.structured_result["medications"][0]) == {
                "tempId",
                "name",
                "strength",
                "doseQuantity",
                "timesPerDay",
                "days",
                "confidence",
            }
            assert ready.structured_result["medications"][1] == {
                "tempId": "med-2",
                "name": "단위 미추출 약",
                "doseQuantity": "2",
                "confidence": "medium",
            }
            assert ready.stage_results == [
                {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
                {"name": "ocr", "status": "succeeded", "elapsedMs": 20, "callCount": 1},
                {"name": "candidate", "status": "succeeded", "elapsedMs": 2, "callCount": 0},
                {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "validate", "status": "succeeded", "elapsedMs": 1, "callCount": 0},
            ]
            assert ready.avg_field_confidence == Decimal("0.8500")
            assert ready.confidence_field_count == 3
            assert ready.ocr_model == "clova-general-v2"
            assert ready.structuring_model == "deterministic-v3"
            assert ready.prompt_version == "medication_grounding_v3"
            assert ready.schema_version == "medication-guide-review/v3"
            assert "targetFieldCount" not in ready.structured_result
            assert stored_path.is_file()

    async def test_process_marks_recapture_as_failed_with_exact_stages_and_no_review(self) -> None:
        user = await create_user("ocr-recapture@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "recapture-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            await service.process(job.id, RecaptureAnalyzer(), job_try=1)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "RECAPTURE_REQUIRED"
            assert failed.structured_result is None
            assert failed.stage_results == [
                {
                    "name": "preprocess",
                    "status": "succeeded",
                    "elapsedMs": 4,
                    "callCount": 0,
                    "code": "RECAPTURE_REQUIRED",
                },
                {"name": "ocr", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "candidate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
            ]

    async def test_read_input_bytes_is_owner_scoped_and_preserves_uploaded_content(self) -> None:
        owner = await create_user("ocr-input-owner@example.com")
        other = await create_user("ocr-input-other@example.com")
        image = png_bytes("black")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(owner, "input-content-key", upload(image))

            content, media_type = await service.read_input_bytes(owner, int(accepted.ocr_job_id))

            assert content == image
            assert media_type == "image/png"
            with pytest.raises(OcrJobNotFoundError):
                await service.read_input_bytes(other, int(accepted.ocr_job_id))

    async def test_process_persists_an_owner_scoped_processed_image(self) -> None:
        owner = await create_user("ocr-processed-owner@example.com")
        other = await create_user("ocr-processed-other@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(owner, "processed-image-key", upload())
            job_id = int(accepted.ocr_job_id)

            await service.process(job_id, FixtureAnalyzer(), job_try=1)

            content, media_type = await service.read_processed_bytes(owner, job_id)
            ready = await OcrJob.get(id=job_id)
            assert content == b"processed-review-jpeg"
            assert media_type == "image/jpeg"
            assert ready.input_manifest["processedContentSha256"]
            assert Path(directory, str(ready.input_manifest["processedStorageKey"])).is_file()
            with pytest.raises(OcrJobNotFoundError):
                await service.read_processed_bytes(other, job_id)

    async def test_process_marks_the_second_transient_failure_as_failed(self) -> None:
        user = await create_user("ocr-final-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "final-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            stored_path = Path(directory, str(job.input_manifest["storageKey"]))

            with pytest.raises(Retry):
                await service.process(job.id, AlwaysTimeoutAnalyzer(), job_try=1)
            retrying = await OcrJob.get(id=job.id)
            assert retrying.stage_results is None
            await service.process(job.id, AlwaysTimeoutAnalyzer(), job_try=2)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "OCR_PROVIDER_TIMEOUT"
            assert failed.stage_results == provider_failure_stages()
            assert failed.completed_at is not None
            assert not stored_path.exists()

    async def test_process_does_not_retry_a_permanent_provider_error(self) -> None:
        user = await create_user("ocr-permanent-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "permanent-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            await service.process(job.id, PermanentFailureAnalyzer(), job_try=1)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "OCR_PROVIDER_ERROR"
            assert failed.stage_results == provider_failure_stages(code="OCR_PROVIDER_ERROR")

    async def test_process_logs_an_unexpected_extraction_failure_before_marking_the_job_failed(self) -> None:
        user = await create_user("ocr-unexpected-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "unexpected-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            with self.assertLogs("app.services.medication_guide_ocr_jobs", level="ERROR") as captured:
                await service.process(job.id, UnexpectedFailureAnalyzer(), job_try=1)

            assert "Unexpected OCR extraction failure for job" in "\n".join(captured.output)
            assert "RuntimeError: unexpected extraction failure" in "\n".join(captured.output)
            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "EXTRACTION_FAILED"
            assert failed.stage_results == fallback_failure_stages(code="EXTRACTION_FAILED")

    async def test_process_preserves_analyzers_stages_when_ready_projection_is_invalid(self) -> None:
        user = await create_user("ocr-invalid-projection@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(user, "invalid-projection-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            await service.process(job.id, InvalidProjectionAnalyzer(), job_try=1)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "VALIDATION_FAILED"
            assert failed.structured_result is None
            assert failed.stage_results == successful_stages()

    async def test_process_uses_exact_fallback_stages_when_analyzer_stages_are_invalid(self) -> None:
        user = await create_user("ocr-invalid-stages@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(user, "invalid-stages-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            await service.process(job.id, InvalidStageAnalyzer(), job_try=1)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "VALIDATION_FAILED"
            assert failed.structured_result is None
            assert failed.stage_results == fallback_failure_stages(code="VALIDATION_FAILED")

    async def test_status_is_owner_scoped_and_hides_result_before_review(self) -> None:
        owner = await create_user("ocr-owner@example.com")
        other = await create_user("ocr-other@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(owner, "request-key-789", upload())

            status_response = await service.get(owner, int(accepted.ocr_job_id))

            assert status_response.status is MedicationGuideOcrJobStatus.QUEUED
            assert status_response.result is None
            with pytest.raises(OcrJobNotFoundError):
                await service.get(other, int(accepted.ocr_job_id))

    async def test_status_deletes_an_expired_review_job(self) -> None:
        user = await create_user("ocr-expired-status@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="expired-status-key",
            input_manifest={
                "contentSha256": "abc",
                "storageKey": "expired.png",
                "processedStorageKey": "expired.processed.jpg",
                "processedContentSha256": "def",
                "processedMediaType": "image/jpeg",
            },
            structured_result={"medications": []},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(minutes=61),
            ready_at=now - timedelta(minutes=61),
            expires_at=now - timedelta(minutes=1),
        )
        with TemporaryDirectory() as directory:
            original_path = Path(directory, "expired.png")
            original_path.write_bytes(b"temporary OCR image")
            processed_path = Path(directory, "expired.processed.jpg")
            processed_path.write_bytes(b"temporary processed image")
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            with pytest.raises(OcrJobNotFoundError):
                await service.get(user, job.id)

            assert not original_path.exists()
            assert not processed_path.exists()
        assert not await OcrJob.filter(id=job.id).exists()

    async def test_status_preserves_a_cancelled_document_job(self) -> None:
        user = await create_user("ocr-legacy-cancelled@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.CANCELLED,
            idempotency_key="legacy-cancelled-key",
            input_manifest={"contentSha256": "abc", "storageKey": "gone.png"},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            error_code="USER_CANCELLED",
            completed_at=now,
        )
        service = MedicationGuideOcrJobService(redis_pool=FakeRedis())

        response = await service.get(user, job.id)

        assert response.status is MedicationGuideOcrJobStatus.CANCELLED

    async def test_confirm_creates_domain_rows_once_and_preserves_image_and_review_result(self) -> None:
        user = await create_user("ocr-confirm@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="confirm-key-123",
            input_manifest={"contentSha256": "abc", "storageKey": "gone.png"},
            structured_result={
                "fields": {"dispensedDate": {"value": "2026-08-25", "confidence": "high"}},
                "medications": [
                    {
                        "tempId": "med-1",
                        "name": "OCR 약품명",
                        "strength": "5mg",
                        "doseQuantity": "1.5정",
                        "timesPerDay": 3,
                        "days": 5,
                        "confidence": "low",
                    }
                ],
                "lowConfidenceCount": 1,
            },
            stage_results=[
                {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
                {"name": "ocr", "status": "succeeded", "elapsedMs": 20, "callCount": 1},
                {"name": "candidate", "status": "succeeded", "elapsedMs": 2, "callCount": 0},
                {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "validate", "status": "succeeded", "elapsedMs": 1, "callCount": 0},
            ],
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(seconds=1),
            ready_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        with TemporaryDirectory() as directory:
            stored_path = Path(directory, "gone.png")
            stored_path.write_bytes(b"confirmed OCR image")
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            request = confirm_request(alias="OCR 등록 별칭")

            first = await service.confirm(user, job.id, request)
            second = await service.confirm(user, job.id, request)
            renamed = await service.confirm(user, job.id, confirm_request(alias="OCR 변경 별칭"))
            clear_alias_payload = request.model_dump(mode="json", by_alias=True)
            clear_alias_payload["alias"] = None
            cleared = await service.confirm(
                user,
                job.id,
                MedicationGuideConfirmRequest.model_validate(clear_alias_payload),
            )

            assert first == second
            assert renamed.care_episode_id == first.care_episode_id
            assert cleared.care_episode_id == first.care_episode_id
            episode = await CareEpisode.get(id=int(first.care_episode_id))
            assert episode.user_id == user.id
            assert episode.title == "2026-08-25 조제약 복약안내"
            assert episode.alias is None
            assert await CareEpisode.filter(source_ocr_job_id=job.id).count() == 1
            assert episode.medication_start_date == date(2026, 8, 25)
            assert episode.medication_days == 5
            assert episode.source_ocr_job_id == job.id
            assert episode.confirmed_at is not None
            medications = await Medication.filter(care_episode=episode).order_by("id")
            assert [item.name for item in medications] == ["수정한 약품 10mg", "추가한 약품", "필요 시 약품"]
            assert medications[0].prescribed_at == date(2026, 8, 25)
            assert medications[0].strength == "10mg"
            assert medications[0].dose_quantity == "1.5정"
            assert all(item.efficacy is None for item in medications)
            assert all(item.administration is None for item in medications)
            assert all(item.precautions is None for item in medications)
            assert all(item.note is None for item in medications)
            assert all(item.source_ocr_job_id == job.id for item in medications)
            stored_job = await OcrJob.get(id=job.id)
            assert stored_job.status is OcrJobStatus.COMPLETE
            assert stored_job.care_episode_id == episode.id
            assert stored_job.structured_result["fields"]["dispensedDate"] == {
                "value": "2026-08-25",
                "confidence": "high",
            }
            assert [item["name"] for item in stored_job.structured_result["medications"]] == [
                "수정한 약품 10mg",
                "추가한 약품",
                "필요 시 약품",
            ]
            assert stored_job.structured_result["medications"][0]["confidence"] == "low"
            assert stored_job.structured_result["medications"][0]["strength"] == "10mg"
            assert stored_job.structured_result["medications"][0]["doseQuantity"] == "1.5정"
            assert "confidence" not in stored_job.structured_result["medications"][1]
            assert "confidence" not in stored_job.structured_result["medications"][2]
            assert "timesPerDay" not in stored_job.structured_result["medications"][2]
            assert stored_job.user_review_match_rate == Decimal("0.6667")
            assert stored_job.stage_results == [
                {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
                {"name": "ocr", "status": "succeeded", "elapsedMs": 20, "callCount": 1},
                {"name": "candidate", "status": "succeeded", "elapsedMs": 2, "callCount": 0},
                {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "validate", "status": "succeeded", "elapsedMs": 1, "callCount": 0},
            ]
            assert stored_job.ready_at is None
            assert stored_job.expires_at is None
            assert stored_path.is_file()
            complete_status = await service.get(user, job.id)
            assert complete_status.status is MedicationGuideOcrJobStatus.COMPLETE
            assert complete_status.result is not None

            with pytest.raises(OcrJobStateConflictError):
                await service.confirm(user, job.id, confirm_request(name="다르게 수정한 약품"))

            revised = await service.confirm(
                user,
                job.id,
                confirm_request(name="등록 중 다시 수정한 약품"),
                allow_registration_edit=True,
            )

            assert revised.care_episode_id == first.care_episode_id
            assert await CareEpisode.filter(source_ocr_job_id=job.id).count() == 1
            assert await Medication.filter(care_episode=episode).count() == 3
            assert (
                await Medication.filter(care_episode=episode).order_by("id").first()
            ).name == "등록 중 다시 수정한 약품"

            await MedicationDose.create(
                user=user,
                care_episode=episode,
                dose_date=date(2026, 8, 25),
                slot=MealSlot.MORNING,
            )
            with pytest.raises(OcrJobStateConflictError):
                await service.confirm(
                    user,
                    job.id,
                    confirm_request(name="복약 기록 뒤 수정 시도"),
                    allow_registration_edit=True,
                )
            await MedicationDose.filter(care_episode=episode).delete()

            medication = await Medication.filter(care_episode=episode).order_by("id").first()
            await MedicationNote.create(
                user=user,
                care_episode=episode,
                medication=medication,
                dosed_at=now,
                body="등록 중 메모",
            )
            with pytest.raises(OcrJobStateConflictError):
                await service.confirm(
                    user,
                    job.id,
                    confirm_request(name="복약 메모 뒤 수정 시도"),
                    allow_registration_edit=True,
                )
            await MedicationNote.filter(care_episode=episode).delete()

            episode.medication_start_slot = MealSlot.MORNING
            await episode.save(update_fields=["medication_start_slot"])
            with pytest.raises(OcrJobStateConflictError):
                await service.confirm(
                    user,
                    job.id,
                    confirm_request(name="복약시간 저장 뒤 수정 시도"),
                    allow_registration_edit=True,
                )

    def test_user_review_match_rate_counts_user_filled_missing_strength_as_mismatch(self) -> None:
        job = OcrJob(
            structured_result={
                "fields": {"dispensedDate": {"value": "2026-08-25", "confidence": "high"}},
                "medications": [
                    {
                        "tempId": "med-1",
                        "name": "테스트약",
                        "doseQuantity": "1정",
                        "timesPerDay": 3,
                        "days": 5,
                    }
                ],
            }
        )
        request = MedicationGuideConfirmRequest.model_validate(
            {
                "dispensingDate": "2026-08-25",
                "medications": [
                    {
                        "tempId": "med-1",
                        "name": "테스트약",
                        "strength": "500mg",
                        "doseQuantity": "1정",
                        "timesPerDay": 3,
                        "days": 5,
                    }
                ],
            }
        )

        assert MedicationGuideOcrJobService._user_review_match_rate(job, request) == Decimal("0.8333")

    async def test_confirmation_keeps_match_rate_null_without_comparable_baseline_fields(self) -> None:
        user = await create_user("ocr-confirm-no-baseline@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="confirm-no-baseline-key",
            input_manifest={"contentSha256": "abc", "storageKey": "no-baseline.png"},
            structured_result={"medications": []},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(seconds=1),
            ready_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        service = MedicationGuideOcrJobService(redis_pool=FakeRedis())
        request = MedicationGuideConfirmRequest.model_validate(
            {
                "dispensingDate": "2026-08-25",
                "medications": [
                    {
                        "tempId": "user-1",
                        "name": "사용자 추가 필요 시 약",
                        "timesPerDay": None,
                    }
                ],
            }
        )

        confirmation = await service.confirm(user, job.id, request)

        medication = await Medication.get(care_episode_id=int(confirmation.care_episode_id))
        assert medication.times_per_day is None
        assert medication.note is None
        stored_job = await OcrJob.get(id=job.id)
        assert "timesPerDay" not in stored_job.structured_result["medications"][0]
        assert stored_job.user_review_match_rate is None

    async def test_confirmation_is_owner_scoped(self) -> None:
        owner = await create_user("ocr-confirm-owner@example.com")
        other = await create_user("ocr-confirm-other@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=owner,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="owner-confirm-key",
            input_manifest={"contentSha256": "abc", "storageKey": "gone.png"},
            structured_result={"medications": []},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(seconds=1),
            ready_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            with pytest.raises(OcrJobNotFoundError):
                await service.confirm(other, job.id, confirm_request())

        assert not await CareEpisode.filter(source_ocr_job_id=job.id).exists()

    async def test_confirmation_rolls_back_every_domain_row_on_failure(self) -> None:
        user = await create_user("ocr-confirm-rollback@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="rollback-confirm-key",
            input_manifest={"contentSha256": "abc", "storageKey": "gone.png"},
            structured_result={"medications": []},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(seconds=1),
            ready_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            with patch.object(Medication, "create", AsyncMock(side_effect=RuntimeError("write failed"))):
                with pytest.raises(RuntimeError, match="write failed"):
                    await service.confirm(user, job.id, confirm_request())

        rolled_back = await OcrJob.get(id=job.id)
        assert rolled_back.status is OcrJobStatus.READY_FOR_REVIEW
        assert rolled_back.care_episode_id is None
        assert not await CareEpisode.filter(user=user).exists()
        assert not await Medication.all().exists()

    async def test_cleanup_deletes_only_expired_unconfirmed_jobs(self) -> None:
        user = await create_user("ocr-cleanup@example.com")
        now = datetime.now(config.TIMEZONE)
        common: dict[str, Any] = {
            "user": user,
            "input_manifest": {"contentSha256": "abc", "storageKey": "missing.png"},
            "ocr_model": "clova-template",
            "structuring_model": "application",
            "prompt_version": "none",
            "schema_version": "medication-guide-review/v1",
            "started_at": now - timedelta(minutes=2),
        }
        expired = await OcrJob.create(
            **common,
            idempotency_key="expired-key",
            status=OcrJobStatus.READY_FOR_REVIEW,
            structured_result={"medications": []},
            ready_at=now - timedelta(minutes=61),
            expires_at=now - timedelta(minutes=1),
        )
        active = await OcrJob.create(
            **common,
            idempotency_key="active-key",
            status=OcrJobStatus.READY_FOR_REVIEW,
            structured_result={"medications": []},
            ready_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        complete = await OcrJob.create(
            **common,
            idempotency_key="complete-key",
            status=OcrJobStatus.COMPLETE,
            structured_result={"medications": []},
            ready_at=None,
            expires_at=None,
            completed_at=now - timedelta(days=1),
        )
        with TemporaryDirectory() as directory:
            original_path = Path(directory, "missing.png")
            complete_path = Path(directory, "complete.png")
            await OcrJob.filter(id=complete.id).update(
                input_manifest={"contentSha256": "def", "storageKey": complete_path.name}
            )
            original_path.write_bytes(b"temporary OCR image")
            complete_path.write_bytes(b"confirmed OCR image")
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            deleted = await service.cleanup_expired(now=now)

            assert complete_path.exists()

        assert deleted == 1
        assert not await OcrJob.filter(id=expired.id).exists()
        assert await OcrJob.filter(id=active.id).exists()
        assert await OcrJob.filter(id=complete.id).exists()
        assert not original_path.exists()

    async def test_cleanup_uses_processing_start_time_and_sweeps_unreferenced_files(self) -> None:
        user = await create_user("ocr-processing-cleanup@example.com")
        now = datetime.now(config.TIMEZONE)
        recent_processing = await OcrJob.create(
            user=user,
            idempotency_key="recent-processing-key",
            status=OcrJobStatus.PROCESSING,
            input_manifest={"contentSha256": "abc", "storageKey": "active.png"},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now,
        )
        await OcrJob.filter(id=recent_processing.id).update(created_at=now - timedelta(minutes=61))
        stale_processing = await OcrJob.create(
            user=user,
            idempotency_key="stale-processing-key",
            status=OcrJobStatus.PROCESSING,
            input_manifest={"contentSha256": "def", "storageKey": "stale.png"},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            started_at=now - timedelta(minutes=61),
        )
        await OcrJob.filter(id=stale_processing.id).update(created_at=now - timedelta(minutes=62))

        with TemporaryDirectory() as directory:
            active_path = Path(directory, "active.png")
            stale_path = Path(directory, "stale.png")
            orphan_path = Path(directory, "orphan.png")
            for path in (active_path, stale_path, orphan_path):
                path.write_bytes(b"temporary OCR image")
            old_timestamp = (now - timedelta(minutes=61)).timestamp()
            os.utime(orphan_path, (old_timestamp, old_timestamp))
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            deleted = await service.cleanup_expired(now=now)

            assert deleted == 1
            assert active_path.exists()
            assert not stale_path.exists()
            assert not orphan_path.exists()
        assert await OcrJob.filter(id=recent_processing.id).exists()
        assert not await OcrJob.filter(id=stale_processing.id).exists()
