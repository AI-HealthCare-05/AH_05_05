import copy
import json
import os
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
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
from app.models.care import CareEpisode, FollowUpVisit
from app.models.enums import AccountStatus, OcrJobStatus
from app.models.medications import Medication
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_normalizer import normalize_clova_response
from app.services.medication_guide_ocr_jobs import (
    MedicationGuideOcrJobService,
    TemporaryOcrStorage,
    build_review_result,
)

FIXTURE_PATH = Path(__file__).parents[3] / "tests" / "ocr" / "fixtures" / "template_ocr_exact_02_response.json"


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


def confirm_request(*, name: str = "수정한 약품 10mg") -> MedicationGuideConfirmRequest:
    return MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-08-25",
            "nextVisitDate": "2026-09-01",
            "medications": [
                {
                    "tempId": "med-1",
                    "name": name,
                    "dose": "1회 1정",
                    "efficacy": "효능",
                    "note": "식후 복용",
                    "precautions": "졸림 주의",
                    "timesPerDay": 3,
                    "days": 5,
                },
                {"tempId": "user-2", "name": "추가한 약품", "timesPerDay": 1, "days": 3},
                {"tempId": "user-3", "name": "필요 시 약품", "timesPerDay": None, "days": None},
            ],
        }
    )


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

    assert review.medications[0].times_per_day is None
    assert review.medications[0].days is None
    assert review.medications[0].needs_review is True
    assert {(issue.code, issue.path) for issue in review.review_issues} == {
        ("VALUE_OUT_OF_RANGE", "medications.med-1.timesPerDay"),
        ("VALUE_OUT_OF_RANGE", "medications.med-1.days"),
    }


class FakeRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        self.enqueued.append((args, kwargs))
        return object()


class FailingRedis(FakeRedis):
    async def enqueue_job(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("redis unavailable")


class FixtureExtractor:
    async def extract_validated(self, _image: object) -> object:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        return normalize_clova_response(copy.deepcopy(payload), expected_template_id=43199)


class TimeoutThenSuccessExtractor(FixtureExtractor):
    def __init__(self) -> None:
        self.calls = 0

    async def extract_validated(self, image: object) -> object:
        from app.core.exceptions import OcrProviderTimeoutError

        self.calls += 1
        if self.calls == 1:
            raise OcrProviderTimeoutError()
        return await super().extract_validated(image)


class AlwaysTimeoutExtractor:
    async def extract_validated(self, _image: object) -> object:
        from app.core.exceptions import OcrProviderTimeoutError

        raise OcrProviderTimeoutError()


class PermanentFailureExtractor:
    async def extract_validated(self, _image: object) -> object:
        from app.core.exceptions import OcrProviderError

        raise OcrProviderError()


class UnexpectedFailureExtractor:
    async def extract_validated(self, _image: object) -> object:
        raise RuntimeError("unexpected extraction failure")


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
        extractor = TimeoutThenSuccessExtractor()
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=redis)
            accepted = await service.submit(user, "request-key-456", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            stored_path = Path(directory, str(job.input_manifest["storageKey"]))

            with pytest.raises(Retry):
                await service.process(job.id, extractor, job_try=1)

            retrying = await OcrJob.get(id=job.id)
            assert retrying.status is OcrJobStatus.PROCESSING
            assert stored_path.is_file()

            await service.process(job.id, extractor, job_try=2)

            ready = await OcrJob.get(id=job.id)
            assert ready.status is OcrJobStatus.READY_FOR_REVIEW
            assert ready.ready_at is not None
            assert ready.expires_at == ready.ready_at + timedelta(minutes=60)
            assert ready.structured_result["medications"][0]["name"] == "에스오메프라졸캡슐"
            assert ready.structured_result["medications"][0]["dose"] == "20mg"
            assert ready.structured_result["dispensingDateConfidence"] == 1.0
            date_fields = {
                field["name"]: field
                for field in ready.structured_result["ocrFields"]
                if field["name"] in {"next_visit_date", "dispensing_date"}
            }
            assert date_fields == {
                "next_visit_date": {"name": "next_visit_date", "text": "2025-04-16(수))", "confidence": 0.9999},
                "dispensing_date": {"name": "dispensing_date", "text": "2025-04-02", "confidence": 1.0},
            }
            assert stored_path.is_file()

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

    async def test_process_marks_the_second_transient_failure_as_failed(self) -> None:
        user = await create_user("ocr-final-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "final-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            stored_path = Path(directory, str(job.input_manifest["storageKey"]))

            with pytest.raises(Retry):
                await service.process(job.id, AlwaysTimeoutExtractor(), job_try=1)
            await service.process(job.id, AlwaysTimeoutExtractor(), job_try=2)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "OCR_PROVIDER_TIMEOUT"
            assert failed.completed_at is not None
            assert not stored_path.exists()

    async def test_process_does_not_retry_a_permanent_provider_error(self) -> None:
        user = await create_user("ocr-permanent-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "permanent-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            await service.process(job.id, PermanentFailureExtractor(), job_try=1)

            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "OCR_PROVIDER_ERROR"

    async def test_process_logs_an_unexpected_extraction_failure_before_marking_the_job_failed(self) -> None:
        user = await create_user("ocr-unexpected-failure@example.com")
        with TemporaryDirectory() as directory:
            storage = TemporaryOcrStorage(Path(directory))
            service = MedicationGuideOcrJobService(storage=storage, redis_pool=FakeRedis())
            accepted = await service.submit(user, "unexpected-failure-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))

            with self.assertLogs("app.services.medication_guide_ocr_jobs", level="ERROR") as captured:
                await service.process(job.id, UnexpectedFailureExtractor(), job_try=1)

            assert "Unexpected OCR extraction failure for job" in "\n".join(captured.output)
            assert "RuntimeError: unexpected extraction failure" in "\n".join(captured.output)
            failed = await OcrJob.get(id=job.id)
            assert failed.status is OcrJobStatus.FAILED
            assert failed.error_code == "EXTRACTION_FAILED"

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
            input_manifest={"contentSha256": "abc", "storageKey": "expired.png"},
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
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )

            with pytest.raises(OcrJobNotFoundError):
                await service.get(user, job.id)

            assert not original_path.exists()
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
                "dispensingDate": "2026-08-25",
                "dispensingDateConfidence": 0.99,
                "medications": [
                    {
                        "rowId": "med-1",
                        "name": "OCR 약품명",
                        "timesPerDay": 3,
                        "days": 5,
                        "confidence": 0.88,
                        "needsReview": True,
                    }
                ],
            },
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
            request = confirm_request()

            first = await service.confirm(user, job.id, request)
            second = await service.confirm(user, job.id, request)

            assert first == second
            episode = await CareEpisode.get(id=int(first.care_episode_id))
            assert episode.user_id == user.id
            assert episode.title == "2026-08-25 조제약 복약안내"
            assert episode.medication_start_date == date(2026, 8, 25)
            assert episode.medication_days == 5
            assert episode.source_ocr_job_id == job.id
            assert episode.confirmed_at is not None
            medications = await Medication.filter(care_episode=episode).order_by("id")
            assert [item.name for item in medications] == ["수정한 약품 10mg", "추가한 약품", "필요 시 약품"]
            assert medications[0].prescribed_at == date(2026, 8, 25)
            assert medications[0].note == "식후 복용"
            assert medications[2].note == "필요 시 복용"
            assert all(item.source_ocr_job_id == job.id for item in medications)
            visit = await FollowUpVisit.get(user=user)
            assert visit.visit_date == date(2026, 9, 1)
            assert visit.user_id == user.id
            stored_job = await OcrJob.get(id=job.id)
            assert stored_job.status is OcrJobStatus.COMPLETE
            assert stored_job.care_episode_id == episode.id
            assert stored_job.structured_result["dispensingDate"] == "2026-08-25"
            assert [item["name"] for item in stored_job.structured_result["medications"]] == [
                "수정한 약품 10mg",
                "추가한 약품",
                "필요 시 약품",
            ]
            assert stored_job.structured_result["medications"][0]["confidence"] == 0.88
            assert "confidence" not in stored_job.structured_result["medications"][1]
            assert "confidence" not in stored_job.structured_result["medications"][2]
            assert stored_job.ready_at is None
            assert stored_job.expires_at is None
            assert stored_path.is_file()
            complete_status = await service.get(user, job.id)
            assert complete_status.status is MedicationGuideOcrJobStatus.COMPLETE
            assert complete_status.result is not None

            with pytest.raises(OcrJobStateConflictError):
                await service.confirm(user, job.id, confirm_request(name="다르게 수정한 약품"))

    async def test_confirmation_preserves_an_explicit_blank_note(self) -> None:
        user = await create_user("ocr-confirm-blank-note@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.READY_FOR_REVIEW,
            idempotency_key="confirm-blank-note-key",
            input_manifest={"contentSha256": "abc", "storageKey": "blank-note.png"},
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
                        "days": None,
                        "note": "",
                    }
                ],
            }
        )

        confirmation = await service.confirm(user, job.id, request)

        medication = await Medication.get(care_episode_id=int(confirmation.care_episode_id))
        assert medication.note == ""
        stored_job = await OcrJob.get(id=job.id)
        assert stored_job.structured_result["medications"][0]["administration"] == ""

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
            with patch.object(FollowUpVisit, "create", AsyncMock(side_effect=RuntimeError("write failed"))):
                with pytest.raises(RuntimeError, match="write failed"):
                    await service.confirm(user, job.id, confirm_request())

        rolled_back = await OcrJob.get(id=job.id)
        assert rolled_back.status is OcrJobStatus.READY_FOR_REVIEW
        assert rolled_back.care_episode_id is None
        assert not await CareEpisode.filter(user=user).exists()
        assert not await Medication.all().exists()
        assert not await FollowUpVisit.all().exists()

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
