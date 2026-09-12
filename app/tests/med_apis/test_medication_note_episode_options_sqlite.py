"""Isolated SQLite contract tests for medication-note filter episode options."""

from datetime import date, datetime

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise import Tortoise

from app.apis.v1.medication_router import medication_resource_router
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exception_handlers import register_exception_handlers
from app.dependencies.security import get_request_user
from app.models.care import CareEpisode
from app.models.enums import AccountStatus, CareEpisodeStatus
from app.models.medications import Medication, MedicationNote
from app.models.users import User

OPTIONS_URL = "/api/v1/med/notes/episodes"


@pytest_asyncio.fixture
async def isolated_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    try:
        yield
    finally:
        await Tortoise.close_connections()


def api_for(user: User | None = None) -> FastAPI:
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(medication_resource_router, prefix="/api/v1")
    if user is not None:
        api.dependency_overrides[get_request_user] = lambda: user
    return api


async def create_user(email: str) -> User:
    return await User.create(
        email=email,
        hashed_password="test-only",
        status=AccountStatus.ACTIVE,
        name="테스트 사용자",
    )


async def create_episode(
    user: User,
    *,
    alias: str | None,
    start_date: date | None,
    episode_status: CareEpisodeStatus,
) -> CareEpisode:
    return await CareEpisode.create(
        user=user,
        alias=alias,
        status=episode_status,
        medication_start_date=start_date,
    )


async def create_note(user: User, episode: CareEpisode, body: str) -> MedicationNote:
    return await MedicationNote.create(
        user=user,
        care_episode=episode,
        dosed_at=datetime(2026, 9, 1, 8, 0),
        body=body,
    )


async def test_note_episode_options_require_authentication(isolated_db: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=api_for()), base_url="http://test") as client:
        response = await client.get(OPTIONS_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_note_episode_options_return_distinct_owned_historical_summaries(
    isolated_db: None,
) -> None:
    owner = await create_user("note-options-owner@example.com")
    other = await create_user("note-options-other@example.com")
    recent = await create_episode(
        owner,
        alias="같은 별칭",
        start_date=date(2026, 9, 1),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    older = await create_episode(
        owner,
        alias="같은 별칭",
        start_date=date(2024, 1, 2),
        episode_status=CareEpisodeStatus.COMPLETED,
    )
    cancelled = await create_episode(
        owner,
        alias=None,
        start_date=None,
        episode_status=CareEpisodeStatus.CANCELLED,
    )
    no_notes = await create_episode(
        owner,
        alias="메모 없는 처방",
        start_date=date(2026, 9, 2),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    other_episode = await create_episode(
        other,
        alias="다른 사용자 처방",
        start_date=date(2026, 9, 3),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    foreign_note_only = await create_episode(
        owner,
        alias="다른 사용자 메모만 있는 처방",
        start_date=date(2026, 9, 4),
        episode_status=CareEpisodeStatus.ACTIVE,
    )

    await create_note(owner, recent, "최근 메모 1")
    await create_note(owner, recent, "최근 메모 2")
    await create_note(owner, older, "오래된 완료 처방 메모")
    await create_note(owner, cancelled, "취소 처방 메모")
    await create_note(other, other_episode, "다른 사용자 메모")
    await create_note(other, foreign_note_only, "소유자가 다른 메모")
    await create_note(owner, other_episode, "소유자가 다른 처방의 비정상 메모")
    await Medication.create(care_episode=recent, name="먼저 등록한 약")
    await Medication.create(care_episode=recent, name="가나다 약")
    await Medication.create(care_episode=older, name="완료 처방 약")
    await Medication.create(care_episode=other_episode, name="다른 사용자 약")

    async with AsyncClient(
        transport=ASGITransport(app=api_for(owner)),
        base_url="http://test",
    ) as client:
        response = await client.get(OPTIONS_URL)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == [
        {
            "careEpisodeId": recent.id,
            "alias": "같은 별칭",
            "startDate": "2026-09-01",
            "status": "ACTIVE",
            "representativeMedicationName": "먼저 등록한 약",
            "medicationCount": 2,
        },
        {
            "careEpisodeId": older.id,
            "alias": "같은 별칭",
            "startDate": "2024-01-02",
            "status": "COMPLETED",
            "representativeMedicationName": "완료 처방 약",
            "medicationCount": 1,
        },
        {
            "careEpisodeId": cancelled.id,
            "alias": None,
            "startDate": None,
            "status": "CANCELLED",
            "representativeMedicationName": None,
            "medicationCount": 0,
        },
    ]
    assert no_notes.id not in {item["careEpisodeId"] for item in response.json()}
    assert other_episode.id not in {item["careEpisodeId"] for item in response.json()}
    assert foreign_note_only.id not in {item["careEpisodeId"] for item in response.json()}


async def test_note_episode_options_can_include_owned_active_and_completed_episodes_without_notes(
    isolated_db: None,
) -> None:
    owner = await create_user("note-inventory-owner@example.com")
    other = await create_user("note-inventory-other@example.com")
    active_without_note = await create_episode(
        owner,
        alias="현재 무메모 처방",
        start_date=date(2026, 9, 5),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    completed_without_note = await create_episode(
        owner,
        alias="종료 무메모 처방",
        start_date=date(2026, 9, 4),
        episode_status=CareEpisodeStatus.COMPLETED,
    )
    active_with_note = await create_episode(
        owner,
        alias="메모 있는 처방",
        start_date=date(2026, 9, 3),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    cancelled_with_note = await create_episode(
        owner,
        alias="취소됐지만 기록 있음",
        start_date=date(2026, 9, 2),
        episode_status=CareEpisodeStatus.CANCELLED,
    )
    cancelled_without_note = await create_episode(
        owner,
        alias="취소 무메모 처방",
        start_date=date(2026, 9, 1),
        episode_status=CareEpisodeStatus.CANCELLED,
    )
    other_episode = await create_episode(
        other,
        alias="다른 사용자 처방",
        start_date=date(2026, 9, 6),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    empty_draft = await create_episode(
        owner,
        alias="약이 없는 미완성 처방",
        start_date=date(2026, 9, 7),
        episode_status=CareEpisodeStatus.ACTIVE,
    )
    await Medication.create(care_episode=active_without_note, name="현재 처방 약")
    await Medication.create(care_episode=completed_without_note, name="종료 처방 약")
    await Medication.create(care_episode=active_with_note, name="기록 처방 약")
    await create_note(owner, active_with_note, "기록 1")
    await create_note(owner, active_with_note, "기록 2")
    await create_note(owner, cancelled_with_note, "취소 전 기록")
    await create_note(other, active_without_note, "다른 사용자가 잘못 연결한 기록")
    await create_note(owner, other_episode, "다른 처방에 잘못 연결한 기록")

    async with AsyncClient(
        transport=ASGITransport(app=api_for(owner)),
        base_url="http://test",
    ) as client:
        response = await client.get(OPTIONS_URL, params={"includeWithoutNotes": "true"})

    assert response.status_code == status.HTTP_200_OK
    items = response.json()
    assert [item["careEpisodeId"] for item in items] == [
        active_without_note.id,
        completed_without_note.id,
        active_with_note.id,
        cancelled_with_note.id,
    ]
    assert [item["noteCount"] for item in items] == [0, 0, 2, 1]
    assert items[0]["representativeMedicationName"] == "현재 처방 약"
    assert items[1]["representativeMedicationName"] == "종료 처방 약"
    assert cancelled_without_note.id not in {item["careEpisodeId"] for item in items}
    assert other_episode.id not in {item["careEpisodeId"] for item in items}
    assert empty_draft.id not in {item["careEpisodeId"] for item in items}
