"""Isolated SQLite contract tests for medication-note filter episode options."""

import sqlite3
from datetime import date, datetime, time

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise import Tortoise

from app.apis.v1.medication_router import (
    get_medication_service,
    medication_resource_router,
    medication_router,
)
from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.core.exception_handlers import register_exception_handlers
from app.dependencies.security import get_request_user
from app.models.care import CareEpisode
from app.models.enums import AccountStatus, CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationNote
from app.models.users import User, UserSettings
from app.services.medications import MedicationService

OPTIONS_URL = "/api/v1/med/notes/episodes"


@pytest_asyncio.fixture
async def isolated_db() -> None:
    sqlite3.register_adapter(time, lambda value: value.isoformat())
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


def api_for(user: User | None = None, *, service: MedicationService | None = None) -> FastAPI:
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(medication_router, prefix="/api/v1")
    api.include_router(medication_resource_router, prefix="/api/v1")
    if user is not None:
        api.dependency_overrides[get_request_user] = lambda: user
    if service is not None:
        api.dependency_overrides[get_medication_service] = lambda: service
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


async def test_note_inventory_includes_current_candidates_and_historical_episodes_with_notes(
    isolated_db: None,
) -> None:
    owner = await create_user("note-inventory-owner@example.com")
    other = await create_user("note-inventory-other@example.com")
    active_without_note = await create_episode(
        owner,
        alias="현재 무메모 처방",
        start_date=date(2026, 9, 13),
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
    active_medication = await Medication.create(
        care_episode=active_without_note,
        name="현재 처방 약50mg",
        strength="50mg",
    )
    await Medication.create(
        care_episode=completed_without_note,
        name="종료 처방 약10mg",
        strength="10mg",
    )
    await Medication.create(care_episode=active_with_note, name="기록 처방 약")
    await create_note(owner, active_with_note, "기록 1")
    await create_note(owner, active_with_note, "기록 2")
    await create_note(owner, cancelled_with_note, "취소 전 기록")
    await create_note(other, active_without_note, "다른 사용자가 잘못 연결한 기록")
    await create_note(owner, other_episode, "다른 처방에 잘못 연결한 기록")

    async with AsyncClient(
        transport=ASGITransport(app=api_for(
            owner,
            service=MedicationService(
                mutation_time_provider=lambda: datetime(2026, 9, 13, 12, 0, tzinfo=config.TIMEZONE),
            ),
        )),
        base_url="http://test",
    ) as client:
        response = await client.get(OPTIONS_URL, params={"includeWithoutNotes": "true"})

    assert response.status_code == status.HTTP_200_OK
    items = response.json()
    assert [item["careEpisodeId"] for item in items] == [
        active_without_note.id,
        active_with_note.id,
        cancelled_with_note.id,
    ]
    assert [item["noteCount"] for item in items] == [0, 2, 1]
    assert [item["canCreateNote"] for item in items] == [True, False, False]
    assert items[0]["firstDoseAt"] == "2026-09-13T08:00:00"
    assert items[0]["representativeMedicationName"] == "현재 처방 약50mg"
    assert items[0]["medications"] == [{"id": active_medication.id, "name": "현재 처방 약50mg", "dose": "50mg"}]
    assert completed_without_note.id not in {item["careEpisodeId"] for item in items}
    assert cancelled_without_note.id not in {item["careEpisodeId"] for item in items}
    assert other_episode.id not in {item["careEpisodeId"] for item in items}
    assert empty_draft.id not in {item["careEpisodeId"] for item in items}


async def test_note_inventory_first_dose_uses_owned_schedule_and_excludes_unknown_date(
    isolated_db: None,
) -> None:
    owner = await create_user("first-dose-owner@example.com")
    await UserSettings.create(
        user=owner,
        morning_medication_time=time(9, 15),
        lunch_medication_time=time(16, 30),
        evening_medication_time=time(20, 45),
        bedtime_medication_time=time(23, 10),
    )
    expected: dict[int, str | None] = {}
    for slot, clock in [
        (MealSlot.MORNING, "09:15"),
        (MealSlot.LUNCH, "16:30"),
        (MealSlot.EVENING, "20:45"),
        (MealSlot.BEDTIME, "23:10"),
    ]:
        episode = await create_episode(
            owner, alias=slot.value, start_date=date(2026, 9, 13), episode_status=CareEpisodeStatus.ACTIVE
        )
        episode.medication_start_slot = slot
        await episode.save(update_fields=["medication_start_slot"])
        await Medication.create(care_episode=episode, name="현재 처방 약")
        expected[episode.id] = "2026-09-13T" + clock + ":00"
    unknown = await create_episode(owner, alias="시작일 미상", start_date=None, episode_status=CareEpisodeStatus.ACTIVE)
    await Medication.create(care_episode=unknown, name="시작일 미상 약")
    async with AsyncClient(
        transport=ASGITransport(app=api_for(
            owner,
            service=MedicationService(
                mutation_time_provider=lambda: datetime(2026, 9, 13, 12, 0, tzinfo=config.TIMEZONE),
            ),
        )),
        base_url="http://test",
    ) as client:
        response = await client.get(OPTIONS_URL, params={"includeWithoutNotes": "true"})
    assert response.status_code == 200
    assert {item["careEpisodeId"]: item["firstDoseAt"] for item in response.json()} == expected
    assert unknown.id not in {item["careEpisodeId"] for item in response.json()}


async def test_note_inventory_only_offers_active_episodes_inside_the_inclusive_intake_period(
    isolated_db: None,
) -> None:
    today = date(2026, 9, 13)
    owner = await create_user("note-current-period@example.com")
    current_first_day = await create_episode(
        owner, alias="오늘 시작", start_date=today, episode_status=CareEpisodeStatus.ACTIVE
    )
    current_last_day = await create_episode(
        owner, alias="오늘 종료", start_date=date(2026, 9, 11), episode_status=CareEpisodeStatus.ACTIVE
    )
    ended_with_note = await create_episode(
        owner, alias="종료 기록", start_date=date(2026, 9, 9), episode_status=CareEpisodeStatus.ACTIVE
    )
    ended_without_note = await create_episode(
        owner, alias="종료 무기록", start_date=date(2026, 9, 8), episode_status=CareEpisodeStatus.ACTIVE
    )
    future = await create_episode(
        owner, alias="미래 처방", start_date=date(2026, 9, 14), episode_status=CareEpisodeStatus.ACTIVE
    )
    cancelled_with_note = await create_episode(
        owner, alias="삭제된 기록", start_date=today, episode_status=CareEpisodeStatus.CANCELLED
    )
    completed_without_note = await create_episode(
        owner, alias="완료 무기록", start_date=today, episode_status=CareEpisodeStatus.COMPLETED
    )
    for episode, days in (
        (current_first_day, 1),
        (current_last_day, 3),
        (ended_with_note, 2),
        (ended_without_note, 2),
        (future, 2),
        (cancelled_with_note, 3),
        (completed_without_note, 3),
    ):
        await Medication.create(care_episode=episode, name=f"{episode.alias} 약", days=days, times_per_day=1)
    await create_note(owner, ended_with_note, "종료 전에 작성한 메모")
    await create_note(owner, cancelled_with_note, "삭제 전에 작성한 메모")

    fixed_service = MedicationService(
        mutation_time_provider=lambda: datetime(2026, 9, 13, 12, 0, tzinfo=config.TIMEZONE),
    )
    async with AsyncClient(
        transport=ASGITransport(app=api_for(owner, service=fixed_service)),
        base_url="http://test",
    ) as client:
        response = await client.get(OPTIONS_URL, params={"includeWithoutNotes": "true"})

    assert response.status_code == status.HTTP_200_OK
    can_create_by_id = {item["careEpisodeId"]: item["canCreateNote"] for item in response.json()}
    assert can_create_by_id == {
        current_first_day.id: True,
        current_last_day.id: True,
        ended_with_note.id: False,
        cancelled_with_note.id: False,
    }
    assert ended_without_note.id not in can_create_by_id
    assert future.id not in can_create_by_id
    assert completed_without_note.id not in can_create_by_id


async def test_create_note_rechecks_current_period_but_cancel_keeps_existing_history(
    isolated_db: None,
) -> None:
    today = date(2026, 9, 13)
    owner = await create_user("note-create-period@example.com")
    first_day = await create_episode(
        owner, alias="첫날", start_date=today, episode_status=CareEpisodeStatus.ACTIVE
    )
    last_day = await create_episode(
        owner, alias="마지막날", start_date=date(2026, 9, 11), episode_status=CareEpisodeStatus.ACTIVE
    )
    ended = await create_episode(
        owner, alias="종료됨", start_date=date(2026, 9, 10), episode_status=CareEpisodeStatus.ACTIVE
    )
    future = await create_episode(
        owner, alias="아직 시작 전", start_date=date(2026, 9, 14), episode_status=CareEpisodeStatus.ACTIVE
    )
    cancelled = await create_episode(
        owner, alias="삭제됨", start_date=today, episode_status=CareEpisodeStatus.CANCELLED
    )
    completed = await create_episode(
        owner, alias="완료 상태", start_date=today, episode_status=CareEpisodeStatus.COMPLETED
    )
    for episode, days in (
        (first_day, 1),
        (last_day, 3),
        (ended, 3),
        (future, 3),
        (cancelled, 3),
        (completed, 3),
    ):
        await Medication.create(care_episode=episode, name=f"{episode.alias} 약", days=days, times_per_day=1)
    historical_note = await create_note(owner, first_day, "삭제 전부터 있던 메모")
    fixed_service = MedicationService(
        mutation_time_provider=lambda: datetime(2026, 9, 13, 12, 0, tzinfo=config.TIMEZONE),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_for(owner, service=fixed_service)),
        base_url="http://test",
    ) as client:
        responses = {}
        for episode in (first_day, last_day, ended, future, cancelled, completed):
            responses[episode.id] = await client.post(
                "/api/v1/med/notes",
                json={
                    "careEpisodeId": episode.id,
                    "dosedAt": "2026-09-13T12:00:00",
                    "body": f"{episode.alias} 메모",
                },
            )
        cancelled_response = await client.delete(f"/api/v1/medications/{first_day.id}")
        retained = await client.get(f"/api/v1/med/notes/{historical_note.id}")

    assert responses[first_day.id].status_code == status.HTTP_201_CREATED
    assert responses[last_day.id].status_code == status.HTTP_201_CREATED
    for episode in (ended, future, cancelled, completed):
        assert responses[episode.id].status_code == status.HTTP_404_NOT_FOUND
        assert responses[episode.id].json()["code"] == "MEDICATION_RECORD_NOT_FOUND"
    assert cancelled_response.status_code == status.HTTP_204_NO_CONTENT
    assert retained.status_code == status.HTTP_200_OK
    assert retained.json()["body"] == "삭제 전부터 있던 메모"
    assert retained.json()["careEpisodeStatus"] == "CANCELLED"
    assert await MedicationNote.filter(id=historical_note.id).exists() is True
