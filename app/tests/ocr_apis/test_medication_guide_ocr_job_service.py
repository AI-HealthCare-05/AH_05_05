import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from arq import Retry
from arq.constants import result_key_prefix
from arq.jobs import serialize_result
from fastapi import UploadFile
from PIL import Image
from starlette.datastructures import Headers
from tortoise.contrib.test import TestCase
from tortoise.exceptions import DBConnectionError, OperationalError
from tortoise.queryset import QuerySet

from app.core import config
from app.core.exceptions import (
    OcrIdempotencyConflictError,
    OcrJobNotFoundError,
    OcrJobStateConflictError,
    OcrQueueUnavailableError,
)
from app.dtos.medication_guide_ocr import (
    MedicationGuideConfirmRequest,
    MedicationGuideOcrJobStatus,
)
from app.models.care import CareEpisode
from app.models.enums import AccountStatus, MealSlot, OcrJobStatus
from app.models.medications import Medication, MedicationDose, MedicationNote
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr_jobs import (
    MedicationGuideOcrJobService,
    TemporaryOcrStorage,
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


def confirm_request(
    *, name: str = "수정한 약품 10mg", alias: str | None = None, hospital_name: str | None = None
) -> MedicationGuideConfirmRequest:
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
    if hospital_name is not None:
        payload["hospitalName"] = hospital_name
    return MedicationGuideConfirmRequest.model_validate(payload)


class FakeRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.results: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.results.get(key)

    def finish(self, job_id: int, *, success: bool = False, function: str = "process_medication_guide_ocr") -> None:
        now_ms = int(datetime.now(config.TIMEZONE).timestamp() * 1000) + 1
        result = serialize_result(
            function,
            (job_id,),
            {},
            1,
            now_ms,
            success,
            None,
            now_ms,
            now_ms,
            f"ocr:{job_id}",
            config.OCR_QUEUE_NAME,
            f"ocr:{job_id}",
        )
        assert result is not None
        self.results[f"{result_key_prefix}ocr:{job_id}"] = result

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
    # No execution evidence: the job retains its error code, stages must not guess an origin.
    return []


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
            preprocess_version="v3.1.8",
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
                "status": "failed",
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


class EmptyMedicationAnalyzer(FixtureAnalyzer):
    def __init__(self, fields: dict[str, object]) -> None:
        self.fields = fields

    async def analyze(self, image: object) -> object:
        analysis = await super().analyze(image)
        analysis.project_review = {"fields": self.fields, "medications": [], "lowConfidenceCount": 0}
        analysis.confidence_values = []
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


def test_stage_validation_accepts_resolve_without_fabricating_legacy_measurements() -> None:
    legacy = successful_stages()
    current = [*legacy[:3], {"name": "resolve", "status": "succeeded", "elapsedMs": 3, "callCount": 0}, *legacy[3:]]
    assert MedicationGuideOcrJobService._validated_stage_results(current) == current
    assert MedicationGuideOcrJobService._validated_stage_results(legacy) == legacy
    with pytest.raises(ValueError):
        MedicationGuideOcrJobService._validated_stage_results([*current, current[3]])


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
    async def test_worker_failure_preserves_empty_legacy_stages(self) -> None:
        user = await create_user("ocr-empty-legacy-stages@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "empty-legacy-stages", upload())
            job_id = int(accepted.ocr_job_id)
            await OcrJob.filter(id=job_id).update(status=OcrJobStatus.PROCESSING, stage_results=[])
            job = await OcrJob.get(id=job_id)
            await service._mark_worker_interrupted(job, job.input_manifest, now=datetime.now(config.TIMEZONE))
            failed = await OcrJob.get(id=job_id)
            assert failed.stage_results == {"timings": None, "stages": []}

    async def test_stage_envelope_migration_leaves_unknown_and_conflicting_data_untouched(self) -> None:
        migration = import_module("app.core.db.migrations.models.33_20260907223001_stage_results_envelope")
        user = await create_user("ocr-envelope-conflicts@example.com")
        cases = [
            ({"unknown": []}, {"timings": {"totalMs": 100}}),
            ({"timings": {"totalMs": 200}, "stages": []}, {"timings": {"totalMs": 100}}),
            ({"timings": None, "stages": [], "futureMetadata": "keep"}, {"source": "keep"}),
            ([{"elapsedMs": 4}], ["legacy-manifest"]),
        ]
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            ids = []
            for index, (stages, manifest) in enumerate(cases):
                accepted = await service.submit(user, f"envelope-conflict-{index}", upload())
                job_id = int(accepted.ocr_job_id)
                ids.append(job_id)
                await OcrJob.filter(id=job_id).update(stage_results=stages, input_manifest=manifest)
            for migrate in (migration.upgrade, migration.upgrade, migration.downgrade, migration.downgrade):
                await OcrJob._meta.db.execute_script(await migrate(OcrJob._meta.db))
                for job_id, (stages, manifest) in zip(ids, cases, strict=True):
                    job = await OcrJob.get(id=job_id)
                    assert job.stage_results == stages
                    assert job.input_manifest == manifest

    async def test_stage_envelope_migration_preserves_history_and_is_repeatable(self) -> None:
        migration = import_module("app.core.db.migrations.models.33_20260907223001_stage_results_envelope")
        user = await create_user("ocr-envelope-migration@example.com")
        stages = [
            {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
            {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0, "code": "DETERMINISTIC_SUFFICIENT"},
        ]
        timings = {"queueWaitMs": 100, "persistMs": 200, "totalMs": 1500}
        cases = [
            (
                stages,
                {"source": "keep", "timings": timings},
                {"timings": timings, "stages": stages},
                {"source": "keep"},
            ),
            (stages, {"source": "keep"}, {"timings": None, "stages": stages}, {"source": "keep"}),
            ([], {"source": "keep"}, {"timings": None, "stages": []}, {"source": "keep"}),
            (None, {"source": "keep", "timings": timings}, {"timings": timings, "stages": None}, {"source": "keep"}),
            (None, {"source": "keep"}, None, {"source": "keep"}),
            (
                {"timings": timings, "stages": stages},
                {"source": "keep"},
                {"timings": timings, "stages": stages},
                {"source": "keep"},
            ),
        ]
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            ids = []
            for index, (old_stages, manifest, _, _) in enumerate(cases):
                accepted = await service.submit(user, f"envelope-migration-{index}", upload())
                job_id = int(accepted.ocr_job_id)
                ids.append(job_id)
                await OcrJob.filter(id=job_id).update(stage_results=old_stages, input_manifest=manifest)
            for _ in range(2):
                await OcrJob._meta.db.execute_script(await migration.upgrade(OcrJob._meta.db))
                for job_id, (_, _, expected, manifest) in zip(ids, cases, strict=True):
                    job = await OcrJob.get(id=job_id)
                    assert job.stage_results == expected
                    assert job.input_manifest == manifest
                    if expected is not None:
                        assert list(job.stage_results) == ["timings", "stages"]
            for _ in range(2):
                await OcrJob._meta.db.execute_script(await migration.downgrade(OcrJob._meta.db))
                for job_id, (_, _, expected, manifest) in zip(ids, cases, strict=True):
                    job = await OcrJob.get(id=job_id)
                    assert job.stage_results == (expected["stages"] if expected is not None else None)
                    expected_manifest = dict(manifest)
                    if expected is not None and expected["timings"] is not None:
                        expected_manifest["timings"] = expected["timings"]
                    assert job.input_manifest == expected_manifest
            await OcrJob._meta.db.execute_script(await migration.upgrade(OcrJob._meta.db))
            for job_id, (_, _, expected, manifest) in zip(ids, cases, strict=True):
                job = await OcrJob.get(id=job_id)
                assert job.stage_results == expected
                assert job.input_manifest == manifest

    async def test_final_publication_retries_database_only_and_preserves_analysis(self) -> None:
        user = await create_user("ocr-publication-retry@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "publication-retry", upload())
            db = OcrJob._meta.db
            execute = db.execute_query
            attempts = 0

            async def fail_first_two_publications(sql, values=None):
                nonlocal attempts
                if sql.startswith("UPDATE") and "structured_result" in sql and "READY_FOR_REVIEW" in (values or ()):
                    attempts += 1
                    if attempts == 1:
                        raise OperationalError("synthetic publication outage")
                    if attempts == 2:
                        raise DBConnectionError("synthetic database reconnect failure")
                return await execute(sql, values)

            analyzer = FixtureAnalyzer()
            with (
                patch.object(db, "execute_query", fail_first_two_publications),
                patch.object(analyzer, "analyze", wraps=analyzer.analyze) as analyze,
                patch.object(service.storage, "save_processed", wraps=service.storage.save_processed) as save_processed,
            ):
                await service.process(int(accepted.ocr_job_id), analyzer, job_try=1)

            ready = await OcrJob.get(id=int(accepted.ocr_job_id))
            assert ready.status == OcrJobStatus.READY_FOR_REVIEW
            assert ready.structured_result["medications"][0]["strength"] == "20mg"
            assert ready.stage_results["stages"] == successful_stages()
            assert ready.stage_results["timings"]["persistMs"] >= 0
            assert await service.storage.load_processed(ready.input_manifest) == (
                b"processed-review-jpeg",
                "image/jpeg",
            )
            assert attempts == 3
            analyze.assert_awaited_once()
            save_processed.assert_awaited_once()

    async def test_publication_ack_loss_never_overwrites_a_committed_or_confirmed_result(self) -> None:
        user = await create_user("ocr-publication-ack@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            db = OcrJob._meta.db
            execute = db.execute_query
            for confirm_immediately, continuing_outage in ((False, False), (True, False), (True, True)):
                accepted = await service.submit(
                    user, f"publication-ack-{confirm_immediately}-{continuing_outage}", upload()
                )
                job_id = int(accepted.ocr_job_id)
                lost_ack = False

                async def commit_then_lose_ack(
                    sql, values=None, *, _confirm=confirm_immediately, _outage=continuing_outage, _job_id=job_id
                ):
                    nonlocal lost_ack
                    if (
                        _outage
                        and lost_ack
                        and sql.startswith("UPDATE")
                        and "structured_result" in sql
                        and "READY_FOR_REVIEW" in (values or ())
                    ):
                        raise OperationalError("synthetic continuing publication outage")
                    result = await execute(sql, values)
                    if (
                        not lost_ack
                        and sql.startswith("UPDATE")
                        and "structured_result" in sql
                        and "READY_FOR_REVIEW" in (values or ())
                    ):
                        lost_ack = True
                        if _confirm:
                            await service.confirm(user, _job_id, confirm_request(name="사용자 확정 약"))
                        raise OperationalError("synthetic lost commit acknowledgement")
                    return result

                with patch.object(db, "execute_query", commit_then_lose_ack):
                    await service.process(job_id, FixtureAnalyzer(), job_try=1)

                saved = await OcrJob.get(id=job_id)
                assert saved.status == (OcrJobStatus.COMPLETE if confirm_immediately else OcrJobStatus.READY_FOR_REVIEW)
                assert saved.error_code is None
                if confirm_immediately:
                    assert saved.structured_result["medications"][0]["name"] == "사용자 확정 약"
                assert Path(directory, saved.input_manifest["storageKey"]).exists()
                assert Path(directory, saved.input_manifest["processedStorageKey"]).exists()

    async def test_exhausted_publication_marks_failed_without_recalling_providers(self) -> None:
        user = await create_user("ocr-publication-exhausted@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "publication-exhausted", upload())
            db = OcrJob._meta.db
            execute = db.execute_query

            async def reject_ready_publication(sql, values=None):
                if sql.startswith("UPDATE") and "structured_result" in sql and "READY_FOR_REVIEW" in (values or ()):
                    raise OperationalError("synthetic invalid publication write")
                return await execute(sql, values)

            analyzer = FixtureAnalyzer()
            with (
                patch.object(db, "execute_query", reject_ready_publication),
                patch.object(analyzer, "analyze", wraps=analyzer.analyze) as analyze,
            ):
                await service.process(int(accepted.ocr_job_id), analyzer, job_try=1)

            failed = await OcrJob.get(id=int(accepted.ocr_job_id))
            assert failed.status == OcrJobStatus.FAILED
            assert failed.error_code == "WORKER_INTERRUPTED"
            assert failed.completed_at is not None
            assert failed.ready_at is None and failed.expires_at is None and failed.structured_result is None
            assert failed.stage_results["stages"] == successful_stages()
            assert list(Path(directory).iterdir()) == []
            analyze.assert_awaited_once()

    async def test_cleanup_reconciles_publication_failure_after_database_recovers(self) -> None:
        user = await create_user("ocr-publication-recover@example.com")
        with TemporaryDirectory() as directory:
            redis = FakeRedis()
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=redis)
            accepted = await service.submit(user, "publication-recover", upload())
            job_id = int(accepted.ocr_job_id)
            db = OcrJob._meta.db
            execute = db.execute_query

            async def reject_terminal_writes(sql, values=None):
                if sql.startswith("UPDATE") and "structured_result" in sql:
                    raise OperationalError("synthetic database outage")
                return await execute(sql, values)

            with patch.object(db, "execute_query", reject_terminal_writes):
                with pytest.raises(OperationalError):
                    await service.process(job_id, FixtureAnalyzer(), job_try=1)
            assert (await OcrJob.get(id=job_id)).status == OcrJobStatus.PROCESSING
            assert len(list(Path(directory).iterdir())) == 2

            # ARQ records the unhandled error even when the database is unavailable.
            redis.finish(job_id)
            assert await service.cleanup_expired() == 0
            failed = await OcrJob.get(id=job_id)
            assert failed.status == OcrJobStatus.FAILED
            assert failed.error_code == "WORKER_INTERRUPTED"
            assert failed.completed_at is not None
            assert (await service.get(user, job_id)).status == MedicationGuideOcrJobStatus.FAILED

    async def test_reconciliation_requires_matching_unsuccessful_worker_evidence(self) -> None:
        user = await create_user("ocr-reconcile-evidence@example.com")
        with TemporaryDirectory() as directory:
            redis = FakeRedis()
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=redis)
            for evidence in ("missing", "success", "wrong-function", "wrong-job", "corrupt", "unavailable", "failed"):
                accepted = await service.submit(user, f"reconcile-{evidence}", upload())
                job_id = int(accepted.ocr_job_id)
                await OcrJob.filter(id=job_id).update(
                    status=OcrJobStatus.PROCESSING, started_at=datetime.now(config.TIMEZONE)
                )
                if evidence != "missing":
                    redis.finish(
                        job_id,
                        success=evidence == "success",
                        function="other_worker" if evidence == "wrong-function" else "process_medication_guide_ocr",
                    )
                if evidence == "wrong-job":
                    redis.finish(job_id + 1000)
                    redis.results[f"{result_key_prefix}ocr:{job_id}"] = redis.results[
                        f"{result_key_prefix}ocr:{job_id + 1000}"
                    ]
                if evidence == "corrupt":
                    redis.results[f"{result_key_prefix}ocr:{job_id}"] = b"invalid-result"
                if evidence == "unavailable":
                    with patch.object(redis, "get", AsyncMock(side_effect=ConnectionError("synthetic redis outage"))):
                        response = await service.get(user, job_id)
                else:
                    response = await service.get(user, job_id)
                expected = (
                    MedicationGuideOcrJobStatus.FAILED
                    if evidence == "failed"
                    else MedicationGuideOcrJobStatus.PROCESSING
                )
                assert response.status == expected

    async def test_immediate_confirmation_does_not_drop_timing_metadata(self) -> None:
        user = await create_user("ocr-timing-confirm@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            original_process = service._process
            original_update = QuerySet.update
            for index, confirm_before_read in enumerate((True, False)):
                accepted = await service.submit(user, f"timing-confirm-{index}", upload())
                job_id = int(accepted.ocr_job_id)

                async def process_then_confirm(*args, _before=confirm_before_read, _job_id=job_id, **kwargs):
                    await original_process(*args, **kwargs)
                    if _before:
                        await OcrJob.filter(id=_job_id).update(status=OcrJobStatus.COMPLETE)

                async def confirm_before_metadata_write(query, _before=confirm_before_read, _job_id=job_id, **kwargs):
                    if not _before and set(kwargs) == {"stage_results"}:
                        await original_update(OcrJob.filter(id=_job_id), status=OcrJobStatus.COMPLETE)
                    return await original_update(query, **kwargs)

                with (
                    patch.object(service, "_process", side_effect=process_then_confirm),
                    patch.object(QuerySet, "update", confirm_before_metadata_write),
                ):
                    await service.process(job_id, FixtureAnalyzer(), job_try=1)
                job = await OcrJob.get(id=job_id)
                assert job.status == OcrJobStatus.COMPLETE
                assert job.stage_results["timings"]["totalMs"] >= 0

    async def test_timing_metadata_failure_does_not_fail_a_successful_ocr_job(self) -> None:
        user = await create_user("ocr-timing-write-failure@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "timing-write-failure-key", upload())
            original_update = QuerySet.update

            def fail_only_timing_write(query, **kwargs):
                if set(kwargs) == {"stage_results"} and kwargs["stage_results"].get("timings") is not None:
                    raise OperationalError("timing write unavailable")
                return original_update(query, **kwargs)

            with patch.object(QuerySet, "update", fail_only_timing_write):
                await service.process(int(accepted.ocr_job_id), FixtureAnalyzer(), job_try=1)
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            assert job.status == OcrJobStatus.READY_FOR_REVIEW
            assert job.error_code is None
            assert job.structured_result["medications"]
            assert "timings" not in job.input_manifest
            assert job.stage_results["timings"] is None
            assert job.stage_results["stages"] == successful_stages()

    async def test_timing_totals_include_storage_and_database_without_summing_stages(self) -> None:
        user = await create_user("ocr-timings@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "timing-success-key", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            await OcrJob.filter(id=job.id).update(created_at=datetime.now(config.TIMEZONE) - timedelta(seconds=5))
            clock = [100.0]
            original_storage_save = service.storage.save_processed
            db = OcrJob._meta.db
            original_execute = db.execute_query

            async def slow_storage(*args, **kwargs):
                result = await original_storage_save(*args, **kwargs)
                clock[0] += 0.2
                return result

            async def slow_database(sql, values=None):
                result = await original_execute(sql, values)
                if sql.startswith("UPDATE") and "structured_result" in sql and "READY_FOR_REVIEW" in (values or ()):
                    clock[0] += 0.3
                return result

            class CurrentAnalyzer(FixtureAnalyzer):
                async def analyze(self, image):
                    result = await super().analyze(image)
                    result.stages.insert(3, {"name": "resolve", "status": "succeeded", "elapsedMs": 1, "callCount": 0})
                    return result

            with (
                patch("app.services.medication_guide_ocr_jobs.time.perf_counter", side_effect=lambda: clock[0]),
                patch.object(service.storage, "save_processed", side_effect=slow_storage),
                patch.object(db, "execute_query", slow_database),
            ):
                await service.process(job.id, CurrentAnalyzer(), job_try=1)
            ready = await OcrJob.get(id=job.id)
            assert list(ready.stage_results) == ["timings", "stages"]
            assert "timings" not in ready.input_manifest
            metrics = ready.stage_results["timings"]
            assert metrics["persistMs"] == 500
            assert 4900 <= metrics["queueWaitMs"] <= 5500
            assert 5400 <= metrics["totalMs"] <= 6000
            response = await service.get(user, job.id)
            assert response.model_dump(mode="json", by_alias=True)["timings"] == metrics
            assert [stage["name"] for stage in ready.stage_results["stages"]] == [
                "preprocess",
                "ocr",
                "candidate",
                "resolve",
                "llm",
                "validate",
            ]
            await service.process(job.id, CurrentAnalyzer(), job_try=1)
            unchanged = await OcrJob.get(id=job.id)
            assert unchanged.stage_results["timings"] == metrics

    async def test_status_reads_enveloped_and_legacy_stage_timings_without_changing_records(self) -> None:
        user = await create_user("ocr-stage-envelope@example.com")
        metrics = {"queueWaitMs": 10, "persistMs": 20, "totalMs": 80}
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "stage-envelope-key", upload())
            job_id = int(accepted.ocr_job_id)
            job = await OcrJob.get(id=job_id)
            for legacy in (True, False):
                stages = [{"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0}]
                payload = stages if legacy else {"timings": metrics, "stages": stages}
                manifest = {**job.input_manifest, "timings": metrics} if legacy else job.input_manifest
                await OcrJob.filter(id=job_id).update(
                    status=OcrJobStatus.FAILED, stage_results=payload, input_manifest=manifest
                )
                response = await service.get(user, job_id)
                assert response.preprocess_elapsed_ms == 4
                assert response.model_dump(mode="json", by_alias=True)["timings"] == metrics
                stored = await OcrJob.get(id=job_id)
                assert stored.stage_results == payload
                assert stored.input_manifest == manifest

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
            assert job.ocr_model == "clova-general-v2"
            assert job.schema_version == "medication-guide-review/v3"
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
            assert "timings" not in retrying.input_manifest
            assert stored_path.is_file()

            await service.process(job.id, analyzer, job_try=2)

            ready = await OcrJob.get(id=job.id)
            assert ready.status is OcrJobStatus.READY_FOR_REVIEW
            assert ready.stage_results["timings"]["totalMs"] >= ready.stage_results["timings"]["queueWaitMs"]
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
            assert ready.stage_results["stages"] == [
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
            assert ready.input_manifest["preprocessVersion"] == "v3.1.8"
            status_response = await service.get(user, job.id)
            assert status_response.preprocess_version == "v3.1.8"
            assert status_response.preprocess_elapsed_ms == 4
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
            assert failed.stage_results["stages"] == [
                {
                    "name": "preprocess",
                    "status": "failed",
                    "elapsedMs": 4,
                    "callCount": 0,
                    "code": "RECAPTURE_REQUIRED",
                },
                {"name": "ocr", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "candidate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
                {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
            ]

    async def test_process_marks_an_empty_medication_analysis_as_extraction_failed(self) -> None:
        user = await create_user("ocr-empty-medications@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            for suffix, fields in (
                ("no-document-fields", {}),
                ("hospital-only", {"hospitalName": {"value": "병원만 인식됨", "confidence": "high"}}),
            ):
                accepted = await service.submit(user, f"empty-medications-{suffix}", upload())
                job = await OcrJob.get(id=int(accepted.ocr_job_id))

                await service.process(job.id, EmptyMedicationAnalyzer(fields), job_try=1)

                failed = await OcrJob.get(id=job.id)
                status_response = await service.get(user, job.id)

                assert failed.status is OcrJobStatus.FAILED
                assert failed.error_code == "EXTRACTION_FAILED"
                assert failed.structured_result is None
                assert status_response.status is MedicationGuideOcrJobStatus.FAILED
                assert status_response.error_code == "EXTRACTION_FAILED"
                assert failed.stage_results["stages"][-1]["status"] == "failed"
                assert failed.stage_results["stages"][-1]["code"] == "NO_VALID_MEDICATION_ROWS"
                assert status_response.result is None

    async def test_confirmation_registers_a_recent_failed_ocr_job(self) -> None:
        user = await create_user("ocr-failed-manual-confirm@example.com")
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(
                storage=TemporaryOcrStorage(Path(directory)),
                redis_pool=FakeRedis(),
            )
            accepted = await service.submit(user, "failed-manual-confirm", upload())
            job = await OcrJob.get(id=int(accepted.ocr_job_id))
            await service.process(job.id, RecaptureAnalyzer(), job_try=1)

            confirmation = await service.confirm(user, job.id, confirm_request())

            confirmed = await OcrJob.get(id=job.id)
            status_response = await service.get(user, job.id)
            assert confirmation.ocr_job_id == str(job.id)
            assert confirmed.status is OcrJobStatus.COMPLETE
            assert confirmed.error_code is None
            assert confirmed.structured_result["medications"][0]["name"] == "수정한 약품 10mg"
            assert status_response.status is MedicationGuideOcrJobStatus.COMPLETE
            assert status_response.result is not None

    async def test_confirmation_rejects_an_expired_failed_ocr_job(self) -> None:
        user = await create_user("ocr-expired-failed-manual-confirm@example.com")
        now = datetime.now(config.TIMEZONE)
        job = await OcrJob.create(
            user=user,
            status=OcrJobStatus.FAILED,
            idempotency_key="expired-failed-manual-confirm",
            input_manifest={"contentSha256": "abc", "storageKey": "gone.png"},
            ocr_model="clova-template",
            structuring_model="application",
            prompt_version="none",
            schema_version="medication-guide-review/v1",
            error_code="RECAPTURE_REQUIRED",
            started_at=now - timedelta(minutes=62),
            completed_at=now - timedelta(minutes=61),
        )
        service = MedicationGuideOcrJobService(redis_pool=FakeRedis())

        with pytest.raises(OcrJobNotFoundError):
            await service.confirm(user, job.id, confirm_request())

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
            assert failed.stage_results["stages"] == provider_failure_stages()
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
            assert failed.stage_results["stages"] == provider_failure_stages(code="OCR_PROVIDER_ERROR")

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
            assert failed.stage_results["stages"] == fallback_failure_stages(code="EXTRACTION_FAILED")
            assert failed.stage_results["timings"]["totalMs"] >= 0

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
            assert failed.stage_results["stages"] == successful_stages()[:-1] + [
                {**successful_stages()[-1], "status": "failed", "code": "VALIDATION_FAILED"}
            ]

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
            assert failed.stage_results["stages"] == fallback_failure_stages(code="VALIDATION_FAILED")

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

    async def test_status_preserves_expired_review_history_and_purges_images(self) -> None:
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
        retained = await OcrJob.get(id=job.id)
        assert retained.status is OcrJobStatus.READY_FOR_REVIEW
        assert retained.structured_result == job.structured_result
        assert retained.created_at == job.created_at
        assert retained.input_manifest["contentSha256"] == "abc"
        with pytest.raises(OcrJobNotFoundError):
            await service.get(user, job.id)
        with pytest.raises(OcrJobNotFoundError):
            await service.confirm(user, job.id, confirm_request())
        assert not await CareEpisode.filter(user=user).exists()

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
                "fields": {
                    "hospitalName": {"value": "송도센트럴이비인후과의원", "confidence": "high"},
                    "dispensedDate": {"value": "2026-08-25", "confidence": "high"},
                },
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
            request = confirm_request(hospital_name="송도센트럴이비인후과의원")

            first = await service.confirm(user, job.id, request)
            assert (await CareEpisode.get(id=int(first.care_episode_id))).alias == "송도센트럴이비인후과의원"
            second = await service.confirm(user, job.id, request)
            renamed = await service.confirm(
                user, job.id, confirm_request(alias="OCR 변경 별칭", hospital_name="송도센트럴이비인후과의원")
            )
            assert (await CareEpisode.get(id=int(first.care_episode_id))).alias == "OCR 변경 별칭"
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
            assert episode.completed_at is None
            assert episode.alias is None
            assert await CareEpisode.filter(source_ocr_job_id=job.id).count() == 1
            assert episode.hospital_name == "송도센트럴이비인후과의원"
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
            assert stored_job.structured_result["fields"]["hospitalName"] == {
                "value": "송도센트럴이비인후과의원",
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
            assert stored_job.user_review_match_rate == Decimal("0.7143")
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
                confirm_request(name="등록 중 다시 수정한 약품", hospital_name="수정한의원"),
                allow_registration_edit=True,
            )

            assert revised.care_episode_id == first.care_episode_id
            await episode.refresh_from_db()
            assert episode.hospital_name == "수정한의원"
            revised_job = await OcrJob.get(id=job.id)
            assert revised_job.structured_result["fields"]["hospitalName"]["value"] == "수정한의원"
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

    async def test_cleanup_retains_expired_unconfirmed_history(self) -> None:
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
            assert await service.cleanup_expired(now=now) == 0

            assert complete_path.exists()

        assert deleted == 1
        retained = await OcrJob.get(id=expired.id)
        assert retained.structured_result == expired.structured_result
        assert retained.status is OcrJobStatus.READY_FOR_REVIEW
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
        retained = await OcrJob.get(id=stale_processing.id)
        assert retained.status is OcrJobStatus.FAILED
        assert retained.error_code == "WORKER_INTERRUPTED"
        assert retained.started_at == stale_processing.started_at

    async def test_cleanup_preserves_stale_job_history_and_failure_evidence(self) -> None:
        for status in (OcrJobStatus.QUEUED, OcrJobStatus.FAILED, OcrJobStatus.CANCELLED):
            with self.subTest(status=status):
                await self._assert_stale_history_retained(status)

    async def _assert_stale_history_retained(self, status: OcrJobStatus) -> None:
        user = await create_user(f"ocr-history-{status.value.lower()}@example.com")
        now = datetime.now(config.TIMEZONE)
        old = now - timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES + 1)
        error_code = {OcrJobStatus.FAILED: "RECAPTURE_REQUIRED", OcrJobStatus.CANCELLED: "USER_CANCELLED"}.get(status)
        evidence = {"timings": None, "stages": successful_stages()}
        job = await OcrJob.create(
            user=user,
            status=status,
            idempotency_key=f"history-{status.value}",
            input_manifest={"contentSha256": "abc", "storageKey": "history.png"},
            ocr_model="clova-template",
            schema_version="medication-guide-review/v1",
            error_code=error_code,
            stage_results=evidence,
            started_at=old if status != OcrJobStatus.QUEUED else None,
            completed_at=old if status != OcrJobStatus.QUEUED else None,
        )
        await OcrJob.filter(id=job.id).update(created_at=old)
        with TemporaryDirectory() as directory:
            path = Path(directory, "history.png")
            path.write_bytes(b"temporary image")
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            assert await service.cleanup_expired(now=now) == 1
            assert not path.exists()
            assert await service.cleanup_expired(now=now + timedelta(days=7)) == 0
            retained = await OcrJob.get(id=job.id)
            assert retained.created_at == old
            assert retained.stage_results == evidence
            assert retained.status == (OcrJobStatus.FAILED if status == OcrJobStatus.QUEUED else status)
            assert retained.error_code == ("WORKER_INTERRUPTED" if status == OcrJobStatus.QUEUED else error_code)
            if status != OcrJobStatus.QUEUED:
                assert retained.completed_at == old
            response = await service.get(user, job.id)
            assert response.status.value == retained.status.value

    async def test_retained_failed_history_preserves_upload_idempotency(self) -> None:
        user = await create_user("ocr-retained-idempotency@example.com")
        now = datetime.now(config.TIMEZONE)
        with TemporaryDirectory() as directory:
            service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(Path(directory)), redis_pool=FakeRedis())
            accepted = await service.submit(user, "retained-upload", upload())
            job_id = int(accepted.ocr_job_id)
            await service.process(job_id, RecaptureAnalyzer(), job_try=1)
            await OcrJob.filter(id=job_id).update(
                completed_at=now - timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES + 1)
            )
            assert await service.cleanup_expired(now=now) == 1
            with patch.object(service, "_enqueue", new_callable=AsyncMock) as enqueue:
                reused = await service.submit(user, "retained-upload", upload())
                assert reused.ocr_job_id == accepted.ocr_job_id
                assert reused.status is MedicationGuideOcrJobStatus.FAILED
                enqueue.assert_not_awaited()
                with pytest.raises(OcrIdempotencyConflictError):
                    await service.submit(user, "retained-upload", upload(png_bytes("black")))
            assert await OcrJob.filter(user=user).count() == 1
