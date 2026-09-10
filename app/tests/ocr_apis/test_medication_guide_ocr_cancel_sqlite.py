import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.apis.v1.medication_guide_ocr_router import medication_guide_ocr_router
from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import OcrJobNotFoundError, OcrJobStateConflictError
from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import MedicationGuideConfirmRequest
from app.models.care import CareEpisode
from app.models.enums import AccountStatus, OcrJobStatus
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService


@pytest.fixture(scope="module", autouse=True)
async def isolated_sqlite_database() -> None:
    """Keep cancellation tests independent from the repository's MySQL-reset fixture."""
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def create_user(label: str) -> User:
    return await User.create(
        email=f"ocr-cancel-{label}-{uuid4().hex}@example.com",
        hashed_password="hashed-password",
        status=AccountStatus.ACTIVE,
        name="OCR 취소 테스트 사용자",
    )


async def create_job(user: User, status_value: OcrJobStatus) -> OcrJob:
    now = datetime.now(config.TIMEZONE)
    return await OcrJob.create(
        user=user,
        status=status_value,
        idempotency_key=f"cancel-{uuid4().hex}",
        input_manifest={"storageKey": "retained.png", "contentSha256": "abc"},
        structured_result={"fields": {}, "medications": [], "lowConfidenceCount": 0},
        ocr_model="clova-general-v2",
        schema_version="medication-guide-review/v3",
        started_at=now if status_value == OcrJobStatus.PROCESSING else None,
        ready_at=now if status_value == OcrJobStatus.READY_FOR_REVIEW else None,
        expires_at=(now + timedelta(minutes=30)) if status_value == OcrJobStatus.READY_FOR_REVIEW else None,
        completed_at=now if status_value in {OcrJobStatus.COMPLETE, OcrJobStatus.FAILED} else None,
    )


def confirm_request() -> MedicationGuideConfirmRequest:
    return MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-08-25",
            "medications": [
                {
                    "tempId": "med-1",
                    "name": "테스트 약품",
                    "strength": "10mg",
                    "doseQuantity": "1정",
                    "timesPerDay": 1,
                    "days": 3,
                }
            ],
        }
    )


@pytest.mark.asyncio
async def test_cancel_route_returns_204_with_no_body() -> None:
    calls: list[tuple[int, int]] = []

    class FakeService:
        async def cancel(self, user: SimpleNamespace, job_id: int) -> None:
            calls.append((int(user.id), job_id))

    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(medication_guide_ocr_router, prefix="/api/v1")
    api.dependency_overrides[get_request_user] = lambda: SimpleNamespace(id=41)
    api.dependency_overrides[get_medication_guide_ocr_job_service] = FakeService

    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        response = await client.post("/api/v1/ocr/jobs/73/cancel")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    assert calls == [(41, 73)]


@pytest.mark.asyncio
async def test_cancel_ready_job_mutates_only_lifecycle_metadata_and_retains_review_artifacts() -> None:
    user = await create_user("ready")
    job = await create_job(user, OcrJobStatus.READY_FOR_REVIEW)
    original_manifest = job.input_manifest
    original_result = job.structured_result
    before = datetime.now(config.TIMEZONE)

    await MedicationGuideOcrJobService().cancel(user, job.id)

    after = datetime.now(config.TIMEZONE)
    cancelled = await OcrJob.get(id=job.id)
    assert cancelled.status is OcrJobStatus.CANCELLED
    assert cancelled.completed_at is not None and before <= cancelled.completed_at <= after
    assert cancelled.updated_at is not None and before <= cancelled.updated_at <= after
    assert cancelled.expires_at is None
    assert cancelled.error_code == "USER_CANCELLED"
    assert cancelled.input_manifest == original_manifest
    assert cancelled.structured_result == original_result


@pytest.mark.asyncio
async def test_cancel_is_idempotent_without_rewriting_completion_metadata() -> None:
    user = await create_user("idempotent")
    job = await create_job(user, OcrJobStatus.READY_FOR_REVIEW)
    service = MedicationGuideOcrJobService()
    await service.cancel(user, job.id)
    first = await OcrJob.get(id=job.id)

    await service.cancel(user, job.id)

    second = await OcrJob.get(id=job.id)
    assert second.status is OcrJobStatus.CANCELLED
    assert second.completed_at == first.completed_at
    assert second.updated_at == first.updated_at


@pytest.mark.asyncio
async def test_cancel_is_owner_scoped_as_not_found() -> None:
    owner = await create_user("owner")
    other = await create_user("other")
    job = await create_job(owner, OcrJobStatus.READY_FOR_REVIEW)

    with pytest.raises(OcrJobNotFoundError):
        await MedicationGuideOcrJobService().cancel(other, job.id)

    retained = await OcrJob.get(id=job.id)
    assert retained.status is OcrJobStatus.READY_FOR_REVIEW


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_value",
    [OcrJobStatus.QUEUED, OcrJobStatus.PROCESSING, OcrJobStatus.FAILED, OcrJobStatus.COMPLETE],
)
async def test_cancel_rejects_every_non_ready_non_cancelled_status(status_value: OcrJobStatus) -> None:
    user = await create_user(status_value.value.lower())
    job = await create_job(user, status_value)

    with pytest.raises(OcrJobStateConflictError):
        await MedicationGuideOcrJobService().cancel(user, job.id)

    retained = await OcrJob.get(id=job.id)
    assert retained.status is status_value


@pytest.mark.asyncio
async def test_cancel_and_confirm_are_serialized_so_only_one_transition_wins() -> None:
    user = await create_user("race")
    job = await create_job(user, OcrJobStatus.READY_FOR_REVIEW)
    service = MedicationGuideOcrJobService()

    cancel_result, confirm_result = await asyncio.gather(
        service.cancel(user, job.id),
        service.confirm(user, job.id, confirm_request()),
        return_exceptions=True,
    )

    results = (cancel_result, confirm_result)
    assert (
        sum(result is None for result in results)
        + sum(not isinstance(result, BaseException) and result is not None for result in results)
        == 1
    )
    assert sum(isinstance(result, OcrJobStateConflictError) for result in results) == 1
    stored = await OcrJob.get(id=job.id)
    assert stored.status in {OcrJobStatus.CANCELLED, OcrJobStatus.COMPLETE}
    assert await CareEpisode.filter(source_ocr_job_id=job.id).count() == (
        1 if stored.status is OcrJobStatus.COMPLETE else 0
    )
