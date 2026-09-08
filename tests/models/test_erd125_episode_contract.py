"""Exercise the ERD125 contract with real persistence in an isolated SQLite DB."""

from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dtos.medication_guide_ocr import DocumentOcrConfirmRequest, MedicationGuideConfirmRequest
from app.dtos.medications import CreateMedicationNoteRequest, UpdateCareEpisodeAliasRequest
from app.models.care import CareEpisode
from app.models.enums import OcrJobStatus
from app.models.medications import Medication
from app.models.ocr import OcrJob
from app.models.users import User
from app.services.medication_guide_ocr_jobs import MedicationGuideOcrJobService, TemporaryOcrStorage
from app.services.medications import MedicationService


@pytest_asyncio.fixture
async def isolated_db():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def confirmation(**changes):
    return MedicationGuideConfirmRequest.model_validate(
        {
            "dispensingDate": "2026-09-08",
            "medications": [{"tempId": "med-1", "name": "테스트 약", "timesPerDay": 1, "days": 3}],
            **changes,
        }
    )


async def ready_job(user):
    now = datetime.now(config.TIMEZONE)
    return await OcrJob.create(
        user=user,
        status=OcrJobStatus.READY_FOR_REVIEW,
        idempotency_key="erd125-isolated",
        input_manifest={},
        structured_result={"fields": {}, "medications": [], "lowConfidenceCount": 0},
        ocr_model="synthetic",
        schema_version="medication-guide-review/v1",
        ready_at=now,
        expires_at=now + timedelta(hours=1),
    )


@pytest.mark.parametrize(
    "fields,expected_alias",
    [
        ({}, None),
        ({"hospitalName": "가" * 253 + "병원"}, "가" * 253 + "병원"),
        ({"hospitalName": "병원 원문", "alias": "나의 처방"}, "나의 처방"),
        ({"hospitalName": "병원 원문", "alias": None}, None),
    ],
)
async def test_confirmation_persists_alias_without_title_or_care_completion(
    isolated_db, tmp_path, fields, expected_alias
):
    user = await User.create(email="erd125@example.test", hashed_password="test-only", name="테스트")
    job = await ready_job(user)
    service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(tmp_path))
    request = confirmation(**fields)

    first = await service.confirm(user, job.id, request)
    repeated = await service.confirm(user, job.id, request)
    episode = await CareEpisode.get(id=int(first.care_episode_id))
    assert first == repeated
    assert await CareEpisode.all().count() == 1
    assert await Medication.all().count() == 1
    assert episode.alias == expected_alias
    assert episode.hospital_name == fields.get("hospitalName")
    assert episode.medication_start_date == date(2026, 9, 8)
    assert episode.completed_at is None
    assert episode.created_at is not None

    note = await MedicationService().create_note(
        user,
        CreateMedicationNoteRequest(
            care_episode_id=episode.id, dosed_at=datetime.now(config.TIMEZONE), body="테스트 메모"
        ),
    )
    response = note.model_dump(mode="json", by_alias=True)
    assert response["careEpisodeAlias"] == expected_alias
    assert response["careEpisodeStartDate"] == "2026-09-08"
    assert "careEpisodeTitle" not in response


async def test_registration_edit_preserves_custom_alias_and_fills_missing_alias(isolated_db, tmp_path):
    user = await User.create(email="erd125-edit@example.test", hashed_password="test-only", name="테스트")
    job = await ready_job(user)
    service = MedicationGuideOcrJobService(storage=TemporaryOcrStorage(tmp_path))
    confirmed = await service.confirm(user, job.id, confirmation(alias="사용자 별칭", hospitalName="원본 병원"))
    episode_id = int(confirmed.care_episode_id)

    await service.confirm(user, job.id, confirmation(hospitalName="수정 병원"), allow_registration_edit=True)
    episode = await CareEpisode.get(id=episode_id)
    assert episode.alias == "사용자 별칭"
    assert episode.hospital_name == "수정 병원"

    await CareEpisode.filter(id=episode_id).update(alias=None)
    await service.confirm(user, job.id, confirmation(hospitalName="새 병원"), allow_registration_edit=True)
    episode = await CareEpisode.get(id=episode_id)
    assert episode.alias == "새 병원"
    assert episode.hospital_name == "새 병원"
    assert episode.completed_at is None
    assert await Medication.all().count() == 1


@pytest.mark.parametrize(
    "model", [UpdateCareEpisodeAliasRequest, MedicationGuideConfirmRequest, DocumentOcrConfirmRequest]
)
def test_alias_request_boundary_is_255_characters(model):
    payload = {"alias": "가" * 255}
    if model is not UpdateCareEpisodeAliasRequest:
        payload.update({"dispensingDate": "2026-09-08", "medications": []})
        if model is DocumentOcrConfirmRequest:
            payload.pop("dispensingDate")
            payload["dispensedDate"] = "2026-09-08"
    assert model.model_validate(payload).alias == "가" * 255
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "alias": "가" * 256})
