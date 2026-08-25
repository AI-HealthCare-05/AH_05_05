import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
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
    ReviewIssue,
)
from app.models.care import CareEpisode, FollowUpVisit
from app.models.enums import CareEpisodeStatus, OcrJobStatus
from app.models.medications import Medication
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr import MedicationGuideService
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


def build_review_result(result: MedicationGuideResult) -> MedicationGuideReviewResult:
    medications = []
    review_issues = list(result.review_issues)
    for medication in result.medications:
        times_per_day = medication.times_per_day
        days = medication.days
        needs_review = medication.needs_review
        if times_per_day is not None and times_per_day > 6:
            times_per_day = None
            needs_review = True
            review_issues.append(
                ReviewIssue(code="VALUE_OUT_OF_RANGE", path=f"medications.{medication.row_id}.timesPerDay")
            )
        if days is not None and days > 365:
            days = None
            needs_review = True
            review_issues.append(ReviewIssue(code="VALUE_OUT_OF_RANGE", path=f"medications.{medication.row_id}.days"))
        medications.append(
            MedicationReview(
                row_id=medication.row_id,
                name=medication.name,
                dose=medication.strength or medication.dose_quantity or medication.dose_line,
                efficacy=medication.efficacy,
                administration=medication.administration,
                precautions=medication.precautions,
                times_per_day=times_per_day,
                days=days,
                confidence=medication.confidence,
                needs_review=needs_review,
            )
        )
    return MedicationGuideReviewResult(
        dispensing_date=result.dispensing_date,
        dispensing_date_confidence=next(
            (field.confidence for field in result.ocr_fields if field.name in {"dispensing_date", "dispensed_date"}),
            None,
        ),
        next_visit_date=result.next_visit_date,
        medications=medications,
        review_issues=review_issues,
    )


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

    async def delete(self, manifest: dict[str, object]) -> None:
        storage_key = manifest.get("storageKey")
        if not isinstance(storage_key, str):
            return
        path = self._path(storage_key)
        await asyncio.to_thread(path.unlink, missing_ok=True)

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
                    structuring_model="application",
                    prompt_version="none",
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
        extractor: MedicationGuideService,
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
        try:
            image = await self.storage.load(manifest)
            extracted = await extractor.extract_validated(image)
            review = build_review_result(extracted)
        except (OcrProviderTimeoutError, OcrProviderTransientError) as error:
            if job_try < 2:
                raise Retry(defer=timedelta(seconds=config.OCR_RETRY_BASE_SECONDS)) from error
            await self._fail(job, error.code, manifest)
            return
        except OcrProviderError as error:
            await self._fail(job, error.code, manifest)
            return
        except AppError:
            await self._fail(job, "VALIDATION_FAILED", manifest)
            return
        except Exception:
            logger.exception("Unexpected OCR extraction failure for job %s", job_id)
            await self._fail(job, "EXTRACTION_FAILED", manifest)
            return

        ready_at = datetime.now(config.TIMEZONE)
        job.status = OcrJobStatus.READY_FOR_REVIEW
        review_payload = review.model_dump(mode="json", by_alias=True)
        review_payload["ocrFields"] = [field.model_dump(mode="json", by_alias=True) for field in extracted.ocr_fields]
        job.structured_result = review_payload
        job.ready_at = ready_at
        job.expires_at = ready_at + timedelta(minutes=config.OCR_REVIEW_TTL_MINUTES)
        job.updated_at = ready_at
        job.error_code = None
        await job.save(
            update_fields=[
                "status",
                "structured_result",
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
                return self._confirmed(job, episode)
            if job.status != OcrJobStatus.READY_FOR_REVIEW:
                raise OcrJobStateConflictError()
            if job.expires_at is None or job.expires_at <= now:
                raise OcrJobNotFoundError()

            dispensing_date = request.dispensing_date
            medication_days = max((item.days for item in request.medications if item.days is not None), default=None)
            episode = await CareEpisode.create(
                using_db=connection,
                user_id=user.id,
                title=f"{dispensing_date.isoformat()} 조제약 복약안내",
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
                update_fields=["source_ocr_job_id", "confirmation_hash", "confirmed_at", "updated_at"],
            )

            for item in request.medications:
                await Medication.create(
                    using_db=connection,
                    care_episode_id=episode.id,
                    name=item.name,
                    dose=item.dose,
                    efficacy=item.efficacy,
                    administration=item.administration,
                    precautions=item.precautions,
                    times_per_day=item.times_per_day,
                    days=item.days,
                    prescribed_at=dispensing_date,
                    source_ocr_job_id=job.id,
                    note=(
                        item.note if item.note is not None else ("필요 시 복용" if item.times_per_day is None else None)
                    ),
                )
            if request.next_visit_date is not None:
                await FollowUpVisit.create(
                    using_db=connection,
                    care_episode_id=episode.id,
                    source_ocr_job_id=job.id,
                    visit_date=request.next_visit_date,
                    purpose="다음 내방일",
                )

            job.status = OcrJobStatus.COMPLETE
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
            if isinstance(manifest, dict) and isinstance((storage_key := manifest.get("storageKey")), str)
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

    async def _fail(self, job: OcrJob, error_code: str, manifest: dict[str, object]) -> None:
        now = datetime.now(config.TIMEZONE)
        job.status = OcrJobStatus.FAILED
        job.error_code = error_code
        if job.started_at is None:
            job.started_at = now
        job.structured_result = None
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
    def _confirmation_hash(request: MedicationGuideConfirmRequest) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json", by_alias=True),
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
        existing_by_id = {medication.row_id: medication for medication in existing.medications}
        medications: list[MedicationReview] = []
        for index, item in enumerate(request.medications, start=1):
            row_id = item.temp_id or f"user-{index}"
            previous = existing_by_id.get(row_id)
            medications.append(
                MedicationReview(
                    row_id=row_id,
                    name=item.name,
                    dose=item.dose,
                    efficacy=item.efficacy,
                    administration=item.note if item.note is not None else item.administration,
                    precautions=item.precautions,
                    times_per_day=item.times_per_day,
                    days=item.days,
                    confidence=previous.confidence if previous is not None else None,
                    needs_review=False,
                )
            )
        confirmed = MedicationGuideReviewResult(
            dispensing_date=request.dispensing_date,
            dispensing_date_confidence=existing.dispensing_date_confidence,
            medications=medications,
        ).model_dump(mode="json", by_alias=True)
        if isinstance(existing_payload.get("ocrFields"), list):
            confirmed["ocrFields"] = existing_payload["ocrFields"]
        return confirmed

    @staticmethod
    def _confirmed(job: OcrJob, episode: CareEpisode) -> OcrConfirmationResponse:
        if episode.confirmed_at is None:
            raise OcrJobStateConflictError()
        return OcrConfirmationResponse(
            ocr_job_id=str(job.id),
            care_episode_id=str(episode.id),
            confirmed_at=episode.confirmed_at,
        )
