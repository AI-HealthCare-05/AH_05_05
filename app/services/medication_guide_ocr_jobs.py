import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from arq import Retry
from arq.connections import RedisSettings, create_pool
from fastapi import UploadFile
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import (
    AppError,
    OcrIdempotencyConflictError,
    OcrJobNotFoundError,
    OcrJobStateConflictError,
    OcrProviderError,
    OcrProviderTimeoutError,
    OcrProviderTransientError,
    OcrQueueUnavailableError,
)
from app.dtos.medication_guide_ocr import (
    MedicationGuideConfirmRequest,
    MedicationGuideOcrJobStatus,
    MedicationGuideResult,
    MedicationGuideReviewResult,
    MedicationReview,
    OcrConfirmationResponse,
    OcrJobAcceptedResponse,
    OcrJobStatusResponse,
)
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, OcrJobStatus
from app.models.medications import Medication
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.ocr_image_input import ValidatedImage, validate_image

logger = logging.getLogger(__name__)


class QueueClient(Protocol):
    async def enqueue_job(
        self,
        function: str,
        *args: Any,
        _job_id: str | None = None,
        _queue_name: str | None = None,
        **kwargs: Any,
    ) -> object: ...

    async def aclose(self) -> None: ...


class MedicationOcrV3AnalysisContract(Protocol):
    project_review: object
    stages: list[dict[str, object]]
    confidence_values: list[float]
    ocr_model: str
    structuring_model: str | None
    prompt_version: str | None
    schema_version: str
    processed_image_bytes: bytes
    requires_recapture: bool


class MedicationOcrV3Analyzer(Protocol):
    async def analyze(self, image: ValidatedImage) -> MedicationOcrV3AnalysisContract: ...


def build_review_result(result: MedicationGuideResult) -> MedicationGuideReviewResult:
    medications: list[MedicationReview] = []
    low_confidence_count = int(result.dispensing_date is None)
    for medication in result.medications:
        times_per_day = medication.times_per_day
        days = medication.days
        needs_review = medication.needs_review
        if times_per_day is not None and times_per_day > 6:
            times_per_day = None
            needs_review = True
        if days is not None and days > 365:
            days = None
            needs_review = True
        confidence = "low" if needs_review else _confidence_tier(medication.confidence)
        low_confidence_count += int(confidence == "low")
        medication_payload: dict[str, object] = {
            "tempId": medication.row_id,
            "name": medication.name,
            "confidence": confidence,
        }
        if medication.strength:
            medication_payload["strength"] = medication.strength
        dose_quantity = _parse_dose_quantity(medication.dose_quantity, medication.dose_unit)
        if dose_quantity is not None:
            medication_payload["doseQuantity"] = dose_quantity
        if times_per_day is not None:
            medication_payload["timesPerDay"] = times_per_day
        if days is not None:
            medication_payload["days"] = days
        medications.append(MedicationReview.model_validate(medication_payload))

    fields: dict[str, object] = {}
    if result.dispensing_date is not None:
        date_confidence = next(
            (field.confidence for field in result.ocr_fields if field.name in {"dispensing_date", "dispensed_date"}),
            0.0,
        )
        date_confidence_tier = _confidence_tier(date_confidence)
        low_confidence_count += int(date_confidence_tier == "low")
        fields["dispensedDate"] = {
            "value": result.dispensing_date.isoformat(),
            "confidence": date_confidence_tier,
        }
    return MedicationGuideReviewResult(
        fields=fields,
        medications=medications,
        low_confidence_count=low_confidence_count,
    )


def _confidence_tier(confidence: float) -> str:
    if confidence >= 0.90:
        return "high"
    if confidence >= 0.70:
        return "medium"
    return "low"


def _parse_dose_quantity(quantity: str | None, unit: str | None) -> str | None:
    if not quantity:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(.*?)\s*", quantity)
    if match is None:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    parsed_unit = (unit or match.group(2)).strip()
    return f"{match.group(1)}{parsed_unit}"


class TemporaryOcrStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, storage_key: str) -> Path:
        if not storage_key or Path(storage_key).name != storage_key:
            raise ValueError("invalid OCR storage key")
        return self.root / storage_key

    async def save(self, image: ValidatedImage) -> str:
        storage_key = f"{uuid4().hex}.{image.provider_format}"
        path = self._path(storage_key)

        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(image.content)
            os.replace(temporary, path)

        await asyncio.to_thread(write)
        return storage_key

    async def save_processed(self, manifest: dict[str, object], content: bytes) -> dict[str, object]:
        if not isinstance(content, bytes) or not content:
            raise ValueError("processed OCR image is missing")
        storage_key = f"{uuid4().hex}.processed.jpg"
        path = self._path(storage_key)

        def write() -> None:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)

        await asyncio.to_thread(write)
        return {
            **manifest,
            "processedStorageKey": storage_key,
            "processedContentSha256": hashlib.sha256(content).hexdigest(),
            "processedMediaType": "image/jpeg",
        }

    async def load(self, manifest: dict[str, object]) -> ValidatedImage:
        storage_key = manifest.get("storageKey")
        if not isinstance(storage_key, str):
            raise ValueError("OCR storage key is missing")
        content = await asyncio.to_thread(self._path(storage_key).read_bytes)
        expected_hash = manifest.get("contentSha256")
        if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("OCR temporary image hash mismatch")
        filename = manifest.get("filename")
        media_type = manifest.get("mediaType")
        provider_format = manifest.get("providerFormat")
        if not all(isinstance(value, str) and value for value in (filename, media_type, provider_format)):
            raise ValueError("OCR image metadata is incomplete")
        return ValidatedImage(
            filename=str(filename),
            media_type=str(media_type),
            provider_format=str(provider_format),
            content=content,
        )

    async def load_processed(self, manifest: dict[str, object]) -> tuple[bytes, str]:
        storage_key = manifest.get("processedStorageKey")
        if not isinstance(storage_key, str):
            raise ValueError("processed OCR storage key is missing")
        content = await asyncio.to_thread(self._path(storage_key).read_bytes)
        expected_hash = manifest.get("processedContentSha256")
        if not isinstance(expected_hash, str) or hashlib.sha256(content).hexdigest() != expected_hash:
            raise ValueError("processed OCR image hash mismatch")
        media_type = manifest.get("processedMediaType")
        if media_type != "image/jpeg":
            raise ValueError("processed OCR image media type is invalid")
        return content, media_type

    async def delete(self, manifest: dict[str, object]) -> None:
        for field in ("storageKey", "processedStorageKey"):
            storage_key = manifest.get(field)
            if isinstance(storage_key, str):
                await asyncio.to_thread(self._path(storage_key).unlink, missing_ok=True)

    async def delete_orphans(self, active_storage_keys: set[str], *, older_than: datetime) -> int:
        """Remove stale files that no database row can discover after a partial submit failure."""

        def delete() -> int:
            if not self.root.exists():
                return 0
            deleted = 0
            cutoff = older_than.timestamp()
            for path in self.root.iterdir():
                if not path.is_file() or path.name in active_storage_keys or path.stat().st_mtime > cutoff:
                    continue
                path.unlink(missing_ok=True)
                deleted += 1
            return deleted

        return await asyncio.to_thread(delete)


class MedicationGuideOcrJobService:
    def __init__(
        self,
        *,
        storage: TemporaryOcrStorage | None = None,
        redis_pool: QueueClient | None = None,
    ) -> None:
        self.storage = storage or TemporaryOcrStorage(config.OCR_TEMP_DIR)
        self.redis_pool = redis_pool

    async def submit(self, user: User, idempotency_key: str, upload: UploadFile) -> OcrJobAcceptedResponse:
        image = await validate_image(upload)
        content_hash = hashlib.sha256(image.content).hexdigest()
        key = idempotency_key.strip()
        existing = await OcrJob.get_or_none(user_id=user.id, idempotency_key=key)
        if existing is not None:
            return self._reuse_or_conflict(existing, content_hash)

        try:
            storage_key = await self.storage.save(image)
        except OSError as error:
            raise OcrQueueUnavailableError() from error
        manifest: dict[str, object] = {
            "storageKey": storage_key,
            "contentSha256": content_hash,
            "filename": image.filename,
            "mediaType": image.media_type,
            "providerFormat": image.provider_format,
            "size": len(image.content),
        }
        keep_image_for_worker = False
        try:
            try:
                job = await OcrJob.create(
                    user=user,
                    status=OcrJobStatus.QUEUED,
                    idempotency_key=key,
                    input_manifest=manifest,
                    ocr_model="clova-template",
                    schema_version="medication-guide-review/v1",
                )
            except IntegrityError:
                existing = await OcrJob.get_or_none(user_id=user.id, idempotency_key=key)
                if existing is None:
                    raise
                return self._reuse_or_conflict(existing, content_hash)

            try:
                await self._enqueue(job)
            except Exception as error:
                try:
                    await self._fail(job, "WORKER_INTERRUPTED", manifest)
                except Exception:
                    # The finally block still removes the image; the orphan sweeper is
                    # a second line of defence if local storage itself is unavailable.
                    pass
                raise OcrQueueUnavailableError() from error
            keep_image_for_worker = True
            return self._accepted(job)
        finally:
            if not keep_image_for_worker:
                try:
                    await self.storage.delete(manifest)
                except OSError:
                    pass

    async def get(self, user: User, job_id: int) -> OcrJobStatusResponse:
        job = await OcrJob.get_or_none(id=job_id, user_id=user.id)
        if job is None:
            raise OcrJobNotFoundError()
        now = datetime.now(config.TIMEZONE)
        if job.status == OcrJobStatus.READY_FOR_REVIEW and job.expires_at is not None and job.expires_at <= now:
            if await self._delete_if_expired(job.id, now=now, user_id=user.id):
                raise OcrJobNotFoundError()
            # confirm() may have won the row lock while this request was checking expiry.
            # In that case return the committed COMPLETE state instead of deleting it.
            job = await OcrJob.get_or_none(id=job_id, user_id=user.id)
            if job is None:
                raise OcrJobNotFoundError()
        result = None
        if job.status in {OcrJobStatus.READY_FOR_REVIEW, OcrJobStatus.COMPLETE} and isinstance(
            job.structured_result, dict
        ):
            result = MedicationGuideReviewResult.model_validate(job.structured_result)
        public_status = self._public_status(job.status)
        return OcrJobStatusResponse(
            ocr_job_id=str(job.id),
            status=public_status,
            expires_at=job.expires_at if job.status == OcrJobStatus.READY_FOR_REVIEW else None,
            result=result,
            error_code=(job.error_code or "WORKER_INTERRUPTED")
            if public_status == MedicationGuideOcrJobStatus.FAILED
            else None,
        )

    async def process(
        self,
        job_id: int,
        analyzer: MedicationOcrV3Analyzer,
        *,
        job_try: int,
    ) -> None:
        now = datetime.now(config.TIMEZONE)
        if job_try <= 1:
            claimed = await OcrJob.filter(id=job_id, status=OcrJobStatus.QUEUED).update(
                status=OcrJobStatus.PROCESSING,
                started_at=now,
                updated_at=now,
            )
            if claimed != 1:
                return
        job = await OcrJob.get_or_none(id=job_id)
        if job is None or job.status != OcrJobStatus.PROCESSING:
            return
        manifest = self._manifest(job)
        analysis: MedicationOcrV3AnalysisContract | None = None
        try:
            image = await self.storage.load(manifest)
            analysis = await analyzer.analyze(image)
            stage_results, review_payload, confidence_values = self._prepared_analysis(analysis)
            if review_payload is None:
                await self._fail(
                    job,
                    "RECAPTURE_REQUIRED",
                    manifest,
                    stage_results=stage_results,
                )
                return
            manifest = await self.storage.save_processed(manifest, analysis.processed_image_bytes)
        except (OcrProviderTimeoutError, OcrProviderTransientError) as error:
            if job_try < 2:
                raise Retry(defer=timedelta(seconds=config.OCR_RETRY_BASE_SECONDS)) from error
            await self._fail(
                job,
                error.code,
                manifest,
                stage_results=self._failure_stage_results(error, error.code, analysis),
            )
            return
        except OcrProviderError as error:
            await self._fail(
                job,
                error.code,
                manifest,
                stage_results=self._failure_stage_results(error, error.code, analysis),
            )
            return
        except (AppError, TypeError, ValueError) as error:
            await self._fail(
                job,
                "VALIDATION_FAILED",
                manifest,
                stage_results=self._failure_stage_results(error, "VALIDATION_FAILED", analysis),
            )
            return
        except Exception as error:
            logger.exception("Unexpected OCR extraction failure for job %s", job_id)
            await self._fail(
                job,
                "EXTRACTION_FAILED",
                manifest,
                stage_results=self._failure_stage_results(error, "EXTRACTION_FAILED", analysis),
            )
            return

        ready_at = datetime.now(config.TIMEZONE)
        job.status = OcrJobStatus.READY_FOR_REVIEW
        job.input_manifest = manifest
        job.structured_result = review_payload
        job.stage_results = stage_results
        job.avg_field_confidence = (
            (sum(confidence_values, start=Decimal("0")) / len(confidence_values)).quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
            if confidence_values
            else None
        )
        job.confidence_field_count = len(confidence_values)
        job.ocr_model = analysis.ocr_model
        job.structuring_model = analysis.structuring_model
        job.prompt_version = analysis.prompt_version
        job.schema_version = analysis.schema_version
        job.ready_at = ready_at
        job.expires_at = ready_at + timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES)
        job.updated_at = ready_at
        job.error_code = None
        await job.save(
            update_fields=[
                "status",
                "input_manifest",
                "structured_result",
                "stage_results",
                "avg_field_confidence",
                "confidence_field_count",
                "ocr_model",
                "structuring_model",
                "prompt_version",
                "schema_version",
                "ready_at",
                "expires_at",
                "updated_at",
                "error_code",
            ]
        )

    async def read_input_bytes(self, user: User, job_id: int) -> tuple[bytes, str]:
        """Return a verified original image only when the requesting user owns the job."""
        job = await OcrJob.get_or_none(id=job_id, user_id=user.id)
        if job is None or job.status in {OcrJobStatus.FAILED, OcrJobStatus.CANCELLED}:
            raise OcrJobNotFoundError()
        try:
            image = await self.storage.load(self._manifest(job))
        except (OSError, ValueError) as error:
            raise OcrJobNotFoundError() from error
        return image.content, image.media_type

    async def read_processed_bytes(self, user: User, job_id: int) -> tuple[bytes, str]:
        """Return the verified processed JPEG only when the requesting user owns the job."""
        job = await OcrJob.get_or_none(id=job_id, user_id=user.id)
        if job is None or job.status not in {OcrJobStatus.READY_FOR_REVIEW, OcrJobStatus.COMPLETE}:
            raise OcrJobNotFoundError()
        try:
            return await self.storage.load_processed(self._manifest(job))
        except (OSError, ValueError) as error:
            raise OcrJobNotFoundError() from error

    async def confirm(
        self,
        user: User,
        job_id: int,
        request: MedicationGuideConfirmRequest,
    ) -> OcrConfirmationResponse:
        confirmation_hash = self._confirmation_hash(request)
        now = datetime.now(config.TIMEZONE)
        async with in_transaction() as connection:
            job = await OcrJob.filter(id=job_id, user_id=user.id).using_db(connection).select_for_update().first()
            if job is None:
                raise OcrJobNotFoundError()
            if job.status == OcrJobStatus.COMPLETE:
                episode = (
                    await CareEpisode.filter(id=getattr(job, "care_episode_id", None), user_id=user.id)
                    .using_db(connection)
                    .first()
                )
                if episode is None or episode.confirmation_hash != confirmation_hash or episode.confirmed_at is None:
                    raise OcrJobStateConflictError()
                if "alias" in request.model_fields_set:
                    episode.alias = request.alias
                    episode.updated_at = now
                    await episode.save(using_db=connection, update_fields=["alias", "updated_at"])
                return self._confirmed(job, episode)
            if job.status != OcrJobStatus.READY_FOR_REVIEW:
                raise OcrJobStateConflictError()
            if job.expires_at is None or job.expires_at <= now:
                raise OcrJobNotFoundError()

            dispensing_date = request.dispensing_date
            medication_days = max(
                (item.days for item in request.medications if "days" in item.model_fields_set),
                default=None,
            )
            episode = await CareEpisode.create(
                using_db=connection,
                user_id=user.id,
                title=f"{dispensing_date.isoformat()} 조제약 복약안내",
                alias=request.alias,
                status=CareEpisodeStatus.ACTIVE,
                medication_start_date=dispensing_date,
                medication_days=medication_days,
            )

            job.care_episode_id = episode.id  # type: ignore[attr-defined]
            await job.save(using_db=connection, update_fields=["care_episode_id"])

            episode.source_ocr_job_id = job.id
            episode.confirmation_hash = confirmation_hash
            episode.confirmed_at = now
            episode.updated_at = now
            await episode.save(
                using_db=connection,
                update_fields=["alias", "source_ocr_job_id", "confirmation_hash", "confirmed_at", "updated_at"],
            )

            for item in request.medications:
                dose_quantity = item.dose_quantity if "dose_quantity" in item.model_fields_set else None
                await Medication.create(
                    using_db=connection,
                    care_episode_id=episode.id,
                    name=item.name,
                    strength=item.strength if "strength" in item.model_fields_set else None,
                    dose_quantity=dose_quantity,
                    times_per_day=item.times_per_day if "times_per_day" in item.model_fields_set else None,
                    days=item.days if "days" in item.model_fields_set else None,
                    prescribed_at=dispensing_date,
                    source_ocr_job_id=job.id,
                )

            job.status = OcrJobStatus.COMPLETE
            job.user_review_match_rate = self._user_review_match_rate(job, request)
            job.structured_result = self._confirmed_review_payload(job, request)
            job.ready_at = None
            job.expires_at = None
            job.completed_at = now
            job.updated_at = now
            await job.save(
                using_db=connection,
                update_fields=[
                    "status",
                    "structured_result",
                    "user_review_match_rate",
                    "ready_at",
                    "expires_at",
                    "completed_at",
                    "updated_at",
                ],
            )
        return self._confirmed(job, episode)

    async def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(config.TIMEZONE)
        stale_cutoff = current - timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES)
        candidate_ids = await (
            OcrJob.filter(care_episode_id=None)
            .filter(
                Q(status=OcrJobStatus.READY_FOR_REVIEW, expires_at__lte=current)
                | Q(status=OcrJobStatus.FAILED, completed_at__lte=stale_cutoff)
                | Q(status=OcrJobStatus.CANCELLED, completed_at__lte=stale_cutoff)
                | Q(status=OcrJobStatus.QUEUED, created_at__lte=stale_cutoff)
                | Q(status=OcrJobStatus.PROCESSING, started_at__lte=stale_cutoff)
            )
            .values_list("id", flat=True)
        )
        deleted = 0
        for job_id in candidate_ids:
            deleted += int(await self._delete_if_expired(job_id, now=current))
        manifests = await OcrJob.all().values_list("input_manifest", flat=True)
        active_storage_keys = {
            storage_key
            for manifest in manifests
            if isinstance(manifest, dict)
            for field in ("storageKey", "processedStorageKey")
            if isinstance((storage_key := manifest.get(field)), str)
        }
        await self.storage.delete_orphans(active_storage_keys, older_than=stale_cutoff)
        return deleted

    async def _delete_if_expired(self, job_id: int, *, now: datetime, user_id: int | None = None) -> bool:
        """Delete one still-unconfirmed stale job while serializing against confirm()."""
        stale_cutoff = now - timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES)
        async with in_transaction() as connection:
            query = OcrJob.filter(id=job_id, care_episode_id=None)
            if user_id is not None:
                query = query.filter(user_id=user_id)
            job = await query.using_db(connection).select_for_update().first()
            if job is None or not self._is_expired(job, now=now, stale_cutoff=stale_cutoff):
                return False
            await self.storage.delete(self._manifest(job))
            await job.delete(using_db=connection)
        return True

    @staticmethod
    def _is_expired(job: OcrJob, *, now: datetime, stale_cutoff: datetime) -> bool:
        if job.status == OcrJobStatus.READY_FOR_REVIEW:
            return job.expires_at is not None and job.expires_at <= now
        if job.status in {OcrJobStatus.FAILED, OcrJobStatus.CANCELLED}:
            return job.completed_at is not None and job.completed_at <= stale_cutoff
        if job.status == OcrJobStatus.QUEUED:
            return job.created_at <= stale_cutoff
        return job.status == OcrJobStatus.PROCESSING and job.started_at is not None and job.started_at <= stale_cutoff

    async def _enqueue(self, job: OcrJob) -> None:
        pool = self.redis_pool
        owns_pool = pool is None
        if pool is None:
            pool = await create_pool(
                RedisSettings(host=config.REDIS_HOST, port=config.REDIS_PORT, database=config.REDIS_DB)
            )
        assert pool is not None
        try:
            await pool.enqueue_job(
                "process_medication_guide_ocr",
                job.id,
                _job_id=f"ocr:{job.id}",
                _queue_name=config.OCR_QUEUE_NAME,
            )
        finally:
            if owns_pool:
                await pool.aclose()

    async def _fail(
        self,
        job: OcrJob,
        error_code: str,
        manifest: dict[str, object],
        *,
        stage_results: list[dict[str, object]] | None = None,
    ) -> None:
        now = datetime.now(config.TIMEZONE)
        job.status = OcrJobStatus.FAILED
        job.error_code = error_code
        if job.started_at is None:
            job.started_at = now
        job.structured_result = None
        job.stage_results = stage_results
        job.ready_at = None
        job.expires_at = None
        job.completed_at = now
        job.updated_at = now
        await job.save(
            update_fields=[
                "status",
                "error_code",
                "started_at",
                "structured_result",
                "stage_results",
                "ready_at",
                "expires_at",
                "completed_at",
                "updated_at",
            ]
        )
        await self.storage.delete(manifest)

    @staticmethod
    def _manifest(job: OcrJob) -> dict[str, object]:
        if not isinstance(job.input_manifest, dict):
            return {}
        return job.input_manifest

    @staticmethod
    def _accepted(job: OcrJob) -> OcrJobAcceptedResponse:
        return OcrJobAcceptedResponse(
            ocr_job_id=str(job.id),
            status=MedicationGuideOcrJobService._public_status(job.status),
            status_url=f"/api/v1/ocr/jobs/{job.id}",
        )

    @staticmethod
    def _public_status(status: OcrJobStatus) -> MedicationGuideOcrJobStatus:
        return MedicationGuideOcrJobStatus(status)

    def _reuse_or_conflict(self, job: OcrJob, content_hash: str) -> OcrJobAcceptedResponse:
        manifest = self._manifest(job)
        if manifest.get("contentSha256") != content_hash:
            raise OcrIdempotencyConflictError()
        return self._accepted(job)

    @staticmethod
    def _project_review_payload(project_review: object) -> dict[str, object]:
        if hasattr(project_review, "model_dump"):
            payload = project_review.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
        elif isinstance(project_review, dict):
            payload = project_review
        else:
            raise TypeError("OCR project_review must be a mapping or Pydantic model")
        payload = MedicationGuideOcrJobService._without_incomplete_dose_quantities(payload)
        review = MedicationGuideReviewResult.model_validate(payload)
        if any(medication.confidence is None for medication in review.medications):
            raise ValueError("OCR project_review medications must include confidence")
        return review.model_dump(mode="json", by_alias=True)

    @classmethod
    def _prepared_analysis(
        cls,
        analysis: MedicationOcrV3AnalysisContract,
    ) -> tuple[list[dict[str, object]], dict[str, object] | None, list[Decimal]]:
        stage_results = cls._validated_stage_results(analysis.stages)
        if type(analysis.requires_recapture) is not bool:
            raise ValueError("OCR requires_recapture must be a boolean")
        if analysis.requires_recapture:
            return stage_results, None, []
        review_payload = cls._project_review_payload(analysis.project_review)
        confidence_values = [Decimal(str(value)) for value in analysis.confidence_values]
        if any(value < 0 or value > 1 for value in confidence_values):
            raise ValueError("OCR confidence values must be between 0 and 1")
        return stage_results, review_payload, confidence_values

    @staticmethod
    def _without_incomplete_dose_quantities(payload: dict[str, object]) -> dict[str, object]:
        canonical = dict(payload)
        medications = payload.get("medications")
        if not isinstance(medications, list):
            return canonical
        canonical_medications: list[object] = []
        for medication in medications:
            if not isinstance(medication, dict):
                canonical_medications.append(medication)
                continue
            canonical_medication = dict(medication)
            dose_quantity = canonical_medication.get("doseQuantity")
            if "doseQuantity" in canonical_medication and (
                not isinstance(dose_quantity, str) or not dose_quantity.strip() or len(dose_quantity) > 50
            ):
                canonical_medication.pop("doseQuantity", None)
            if canonical_medication.get("timesPerDay") is None:
                canonical_medication.pop("timesPerDay", None)
            canonical_medications.append(canonical_medication)
        canonical["medications"] = canonical_medications
        return canonical

    @staticmethod
    def _validated_stage_results(stages: list[dict[str, object]]) -> list[dict[str, object]]:
        expected_names = ["preprocess", "ocr", "candidate", "llm", "validate"]
        normalized: list[dict[str, object]] = []
        for stage in stages:
            if hasattr(stage, "model_dump"):
                stage_payload = stage.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
            elif isinstance(stage, dict):
                stage_payload = dict(stage)
            else:
                raise TypeError("OCR stage must be a mapping or Pydantic model")
            if set(stage_payload) - {"name", "status", "elapsedMs", "callCount", "code"}:
                raise ValueError("OCR stage contains unsupported fields")
            normalized.append(stage_payload)
        if [stage.get("name") for stage in normalized] != expected_names:
            raise ValueError("OCR stages must contain the five ordered v3 stages")
        if any(
            type(stage.get("status")) is not str or stage.get("status") not in {"succeeded", "failed", "skipped"}
            for stage in normalized
        ):
            raise ValueError("OCR stage status is invalid")
        if any(type(stage.get("elapsedMs")) is not int or int(stage["elapsedMs"]) < 0 for stage in normalized):
            raise ValueError("OCR stage elapsedMs must be a non-negative integer")
        if any(type(stage.get("callCount")) is not int or int(stage["callCount"]) < 0 for stage in normalized):
            raise ValueError("OCR stage callCount must be a non-negative integer")
        if any(
            "code" in stage and (type(stage["code"]) is not str or not str(stage["code"]).strip())
            for stage in normalized
        ):
            raise ValueError("OCR stage code must be a non-blank string")
        return normalized

    @classmethod
    def _failure_stage_results(
        cls,
        error: Exception,
        error_code: str,
        analysis: MedicationOcrV3AnalysisContract | None = None,
    ) -> list[dict[str, object]]:
        for stages in (getattr(error, "stages", None), getattr(analysis, "stages", None)):
            if not isinstance(stages, list):
                continue
            try:
                return cls._validated_stage_results(stages)
            except (TypeError, ValueError):
                continue
        return cls._fallback_stage_results(error_code)

    @staticmethod
    def _fallback_stage_results(error_code: str) -> list[dict[str, object]]:
        return [
            {
                "name": "preprocess",
                "status": "failed",
                "elapsedMs": 0,
                "callCount": 0,
                "code": error_code,
            },
            *(
                {"name": name, "status": "skipped", "elapsedMs": 0, "callCount": 0}
                for name in ("ocr", "candidate", "llm", "validate")
            ),
        ]

    @staticmethod
    def _confirmation_hash(request: MedicationGuideConfirmRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True, exclude={"alias"}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _confirmed_review_payload(
        job: OcrJob,
        request: MedicationGuideConfirmRequest,
    ) -> dict[str, object]:
        existing_payload = job.structured_result if isinstance(job.structured_result, dict) else {}
        try:
            existing = MedicationGuideReviewResult.model_validate(existing_payload)
        except ValueError:
            existing = MedicationGuideReviewResult()
        existing_by_id = {medication.temp_id: medication for medication in existing.medications}
        medications: list[MedicationReview] = []
        for item in request.medications:
            previous = existing_by_id.get(item.temp_id)
            medication_payload = item.model_dump(mode="json", by_alias=True)
            if medication_payload.get("timesPerDay") is None:
                medication_payload.pop("timesPerDay", None)
            if previous is not None and previous.confidence is not None:
                medication_payload["confidence"] = previous.confidence
            medications.append(MedicationReview.model_validate(medication_payload))

        has_previous_date = "dispensed_date" in existing.fields.model_fields_set
        date_confidence = existing.fields.dispensed_date.confidence if has_previous_date else "low"
        low_confidence_count = int(date_confidence == "low") + sum(
            medication.confidence == "low" for medication in medications
        )
        confirmed = MedicationGuideReviewResult(
            fields={
                "dispensedDate": {
                    "value": request.dispensing_date.isoformat(),
                    "confidence": date_confidence,
                }
            },
            medications=medications,
            low_confidence_count=low_confidence_count,
        ).model_dump(mode="json", by_alias=True)
        return confirmed

    @staticmethod
    def _user_review_match_rate(
        job: OcrJob,
        request: MedicationGuideConfirmRequest,
    ) -> Decimal | None:
        existing_payload = job.structured_result if isinstance(job.structured_result, dict) else {}
        try:
            existing = MedicationGuideReviewResult.model_validate(existing_payload)
        except ValueError:
            return None

        comparable = 0
        matches = 0
        if "dispensed_date" in existing.fields.model_fields_set:
            previous_date = existing.fields.dispensed_date
            comparable += 1
            matches += int(previous_date.value == request.dispensing_date)

        existing_by_id = {medication.temp_id: medication for medication in existing.medications}
        missing = object()
        for item in request.medications:
            previous = existing_by_id.get(item.temp_id)
            if previous is None:
                continue
            previous_payload = previous.model_dump(mode="json", by_alias=True)
            confirmed_payload = item.model_dump(mode="json", by_alias=True)
            for field in ("name", "strength", "doseQuantity", "timesPerDay", "days"):
                if field not in previous_payload and field not in confirmed_payload:
                    continue
                comparable += 1
                matches += int(previous_payload.get(field, missing) == confirmed_payload.get(field, missing))

        if comparable == 0:
            return None
        return (Decimal(matches) / Decimal(comparable)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _confirmed(job: OcrJob, episode: CareEpisode) -> OcrConfirmationResponse:
        if episode.confirmed_at is None:
            raise OcrJobStateConflictError()
        return OcrConfirmationResponse(
            ocr_job_id=str(job.id),
            care_episode_id=str(episode.id),
            confirmed_at=episode.confirmed_at,
        )
