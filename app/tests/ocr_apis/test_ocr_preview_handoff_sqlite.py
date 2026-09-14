import hashlib
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.apis.v1.medication_guide_ocr_router import medication_guide_ocr_router
from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exception_handlers import register_exception_handlers
from app.core.exceptions import OcrJobNotFoundError
from app.dependencies.medication_guide_ocr import get_medication_guide_ocr_job_service
from app.dependencies.security import get_request_user
from app.dtos.medication_guide_ocr import MedicationGuideConfirmRequest
from app.models.enums import AccountStatus, OcrJobStatus
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService
from app.services.ocr_image_input import ValidatedImage
from app.services.ocr_volatile_storage import STORAGE_BACKEND, VolatileOcrStorage
from app.tests.ocr_apis.test_ocr_volatile_storage import FakeRedis


@pytest.fixture(scope="module", autouse=True)
async def isolated_database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


async def setup_job(state=OcrJobStatus.READY_FOR_REVIEW):
    user = await User.create(
        email=f"handoff-{uuid4().hex}@example.com",
        name="합성 테스트",
        hashed_password="test",
        status=AccountStatus.ACTIVE,
    )
    redis = FakeRedis()
    storage = VolatileOcrStorage("redis://test", ttl_seconds=3600, client=redis)
    image = ValidatedImage("test.jpg", "image/jpeg", "jpg", b"original")
    key = await storage.save(image)
    manifest = await storage.save_processed(
        {
            "storageBackend": STORAGE_BACKEND,
            "storageKey": key,
            "contentSha256": hashlib.sha256(image.content).hexdigest(),
            "filename": image.filename,
            "mediaType": image.media_type,
            "providerFormat": image.provider_format,
        },
        b"processed",
    )
    now = datetime.now(config.TIMEZONE)
    job = await OcrJob.create(
        user=user,
        status=state,
        idempotency_key=uuid4().hex,
        input_manifest=manifest,
        structured_result={"fields": {}, "medications": [], "lowConfidenceCount": 0},
        ocr_model="test",
        schema_version="medication-guide-review/v3",
        ready_at=now,
        expires_at=now + timedelta(minutes=60),
    )
    return user, job, MedicationGuideOcrJobService(storage=storage), redis


async def release_request(user, job_id, service):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(medication_guide_ocr_router, prefix="/api/v1")
    api.dependency_overrides[get_request_user] = lambda: user
    api.dependency_overrides[get_medication_guide_ocr_job_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://test") as client:
        return await client.post(f"/api/v1/ocr/jobs/{job_id}/release-images")


@pytest.mark.asyncio
async def test_handoff_deletes_both_photos_but_keeps_review_confirmable():
    user, job, service, redis = await setup_job()
    assert (await service.read_input_bytes(user, job.id))[0] == b"original"
    assert (await service.read_processed_bytes(user, job.id))[0] == b"processed"
    response = await release_request(user, job.id, service)
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"
    assert redis.values == {}
    stored = await OcrJob.get(id=job.id)
    assert stored.status == OcrJobStatus.READY_FOR_REVIEW
    assert stored.structured_result == job.structured_result
    assert stored.expires_at == job.expires_at
    assert stored.input_manifest["imagesPurgedAt"]
    with pytest.raises(OcrJobNotFoundError):
        await service.read_input_bytes(user, job.id)
    with pytest.raises(OcrJobNotFoundError):
        await service.read_processed_bytes(user, job.id)
    assert (await service.get(user, job.id)).result is not None
    confirmation = await service.confirm(
        user,
        job.id,
        MedicationGuideConfirmRequest.model_validate(
            {
                "dispensingDate": "2026-09-14",
                "medications": [{"tempId": "m1", "name": "테스트 약", "timesPerDay": 1, "days": 3}],
            }
        ),
    )
    assert confirmation.care_episode_id
    assert (await OcrJob.get(id=job.id)).status == OcrJobStatus.COMPLETE


@pytest.mark.asyncio
async def test_handoff_is_idempotent_and_owner_scoped():
    user, job, service, redis = await setup_job()
    other, _, _, _ = await setup_job()
    response = await release_request(other, job.id, service)
    assert response.status_code == 404
    assert len(redis.values) == 2
    assert (await release_request(user, job.id, service)).status_code == 204
    first = (await OcrJob.get(id=job.id)).input_manifest
    assert (await release_request(user, job.id, service)).status_code == 204
    assert (await OcrJob.get(id=job.id)).input_manifest == first


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [OcrJobStatus.QUEUED, OcrJobStatus.PROCESSING])
async def test_handoff_cannot_remove_worker_input_while_ocr_is_active(state):
    user, job, service, redis = await setup_job(state)
    assert (await release_request(user, job.id, service)).status_code == 409
    assert len(redis.values) == 2


@pytest.mark.asyncio
async def test_failed_deletion_is_retryable_and_not_falsely_acknowledged(monkeypatch):
    user, job, service, redis = await setup_job()
    original_delete = redis.delete

    async def fail_delete(*keys):
        raise OSError("temporary test outage")

    monkeypatch.setattr(redis, "delete", fail_delete)
    assert (await release_request(user, job.id, service)).status_code == 503
    assert len(redis.values) == 2
    assert "imagesPurgedAt" not in (await OcrJob.get(id=job.id)).input_manifest
    monkeypatch.setattr(redis, "delete", original_delete)
    assert (await release_request(user, job.id, service)).status_code == 204
    assert redis.values == {}


@pytest.mark.asyncio
async def test_ready_images_have_short_handoff_ttl_not_full_review_ttl():
    _, job, service, redis = await setup_job()
    await service._refresh_preview_ttl(job.input_manifest)
    assert set(redis.expirations.values()) == {300}
    assert (await OcrJob.get(id=job.id)).expires_at == job.expires_at


@pytest.mark.asyncio
async def test_handoff_ttl_never_outlasts_shorter_review_window(monkeypatch):
    _, job, service, redis = await setup_job()
    monkeypatch.setattr(config, "OCR_REVIEW_TTL_MINUTES", 1)
    await service._refresh_preview_ttl(job.input_manifest)
    assert set(redis.expirations.values()) == {60}
