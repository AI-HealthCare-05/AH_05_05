"""Fixed schedule policy with in-memory SQLite only; run with --noconftest."""

import sqlite3
from collections.abc import AsyncIterator
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS
from app.dtos.follow_up_visits import FollowUpVisitCreateRequest, FollowUpVisitUpdateRequest
from app.dtos.settings import NotifySettingsUpdateRequest
from app.models.alarms import Alarm
from app.models.care import FollowUpVisit
from app.models.enums import AlarmStatus, AlarmType
from app.models.users import User, UserSettings
from app.services import follow_up_visit_alarms
from app.services.follow_up_visits import FollowUpVisitService
from app.services.settings import NotifySettingsService

KST = ZoneInfo("Asia/Seoul")


def freeze_clock(monkeypatch: pytest.MonkeyPatch, instant: str) -> None:
    class FrozenDatetime(datetime):
        combine = staticmethod(datetime.combine)

        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant).astimezone(tz)

    monkeypatch.setattr(follow_up_visit_alarms, "datetime", FrozenDatetime)


@pytest_asyncio.fixture(loop_scope="function")
async def owner(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[User]:
    monkeypatch.setitem(sqlite3.adapters, (time, sqlite3.PrepareProtocol), lambda value: value.isoformat())
    freeze_clock(monkeypatch, "2026-09-10T10:00:00+09:00")
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    try:
        yield await User.create(email="reminder@example.com", hashed_password="unused", name="사용자")
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize("evening", [time(18), time(19), time(20, 30)])
async def test_create_reserves_previous_day_2100_independent_of_medication(owner: User, evening: time) -> None:
    await UserSettings.create(user=owner, evening_medication_time=evening)
    visit = await FollowUpVisitService().create(
        owner, FollowUpVisitCreateRequest(visit_date=date(2026, 9, 12), hospital="내과")
    )

    alarm = await Alarm.get(follow_up_visit_id=visit.id)
    assert alarm.scheduled_at == datetime(2026, 9, 11, 21, tzinfo=KST)
    assert alarm.next_trigger_at == datetime(2026, 9, 11, 21, tzinfo=KST)
    assert alarm.timezone == "Asia/Seoul"


async def test_date_change_moves_existing_pending_reservation_to_previous_day_2100(owner: User) -> None:
    service = FollowUpVisitService()
    visit = await service.create(owner, FollowUpVisitCreateRequest(visit_date=date(2026, 9, 12), hospital="내과"))
    original_alarm = await Alarm.get(follow_up_visit_id=visit.id)

    await service.update(owner, visit.id, FollowUpVisitUpdateRequest(visit_date=date(2026, 9, 15)))

    alarm = await Alarm.get(follow_up_visit_id=visit.id)
    assert alarm.id == original_alarm.id
    assert alarm.scheduled_at == alarm.next_trigger_at == datetime(2026, 9, 14, 21, tzinfo=KST)
    assert alarm.status == AlarmStatus.ACTIVE


@pytest.mark.parametrize(
    ("instant", "expected_count"),
    [
        ("2026-09-11T11:59:59+00:00", 1),
        ("2026-09-11T12:00:00+00:00", 0),
        ("2026-09-11T12:00:01+00:00", 0),
        ("2026-09-11T15:00:00+00:00", 0),
    ],
)
async def test_no_replay_at_or_after_previous_day_2100_kst(
    owner: User, monkeypatch: pytest.MonkeyPatch, instant: str, expected_count: int
) -> None:
    freeze_clock(monkeypatch, instant)
    visit = await FollowUpVisitService().create(
        owner, FollowUpVisitCreateRequest(visit_date=date(2026, 9, 12), hospital="내과")
    )

    assert await Alarm.filter(follow_up_visit_id=visit.id).count() == expected_count


async def test_evening_setting_change_does_not_touch_schedule_reservation(owner: User) -> None:
    visit = await FollowUpVisit.create(user=owner, visit_date=date(2026, 9, 12), hospital="내과")
    alarm = await Alarm.create(
        user=owner,
        follow_up_visit=visit,
        alarm_type=AlarmType.FOLLOW_UP_VISIT,
        title="진료 일정 알림",
        scheduled_at=datetime(2026, 9, 11, 21, tzinfo=KST),
        next_trigger_at=datetime(2026, 9, 11, 21, tzinfo=KST),
    )
    before = await Alarm.filter(id=alarm.id).values()

    settings = await NotifySettingsService().update(
        owner, NotifySettingsUpdateRequest(evening_medication_time=time(20))
    )

    assert settings.evening_medication_time == time(20)
    assert await Alarm.filter(id=alarm.id).values() == before


@pytest.mark.parametrize("alarm_status", [AlarmStatus.PAUSED, AlarmStatus.COMPLETED, AlarmStatus.CANCELLED])
@pytest.mark.parametrize("new_date", [date(2026, 9, 10), date(2026, 9, 15)])
async def test_date_change_preserves_inactive_reservations(owner: User, alarm_status, new_date: date) -> None:
    await assert_existing_alarm_unchanged(owner, new_date, status=alarm_status)


async def test_date_change_preserves_already_triggered_reservation(owner: User) -> None:
    await assert_existing_alarm_unchanged(
        owner, date(2026, 9, 15), last_triggered_at=datetime(2026, 9, 11, 19, tzinfo=KST)
    )


@pytest.mark.parametrize("field", ["scheduled_at", "next_trigger_at"])
async def test_date_change_does_not_replay_overdue_reservation(owner: User, field: str) -> None:
    await assert_existing_alarm_unchanged(owner, date(2026, 9, 15), **{field: datetime(2026, 9, 9, 19, tzinfo=KST)})


async def assert_existing_alarm_unchanged(owner: User, new_date: date, **alarm_fields) -> None:
    visit = await FollowUpVisit.create(user=owner, visit_date=date(2026, 9, 12), hospital="내과")
    values = {
        "scheduled_at": datetime(2026, 9, 11, 19, tzinfo=KST),
        "next_trigger_at": datetime(2026, 9, 11, 19, tzinfo=KST),
        **alarm_fields,
    }
    alarm = await Alarm.create(
        user=owner,
        follow_up_visit=visit,
        alarm_type=AlarmType.FOLLOW_UP_VISIT,
        title="진료 일정 알림",
        **values,
    )
    before = await Alarm.filter(id=alarm.id).values()

    await FollowUpVisitService().update(owner, visit.id, FollowUpVisitUpdateRequest(visit_date=new_date))

    assert await Alarm.filter(id=alarm.id).values() == before


async def test_date_change_to_elapsed_reminder_cancels_pending_reservation(owner: User) -> None:
    service = FollowUpVisitService()
    visit = await service.create(owner, FollowUpVisitCreateRequest(visit_date=date(2026, 9, 12), hospital="내과"))

    await service.update(owner, visit.id, FollowUpVisitUpdateRequest(visit_date=date(2026, 9, 10)))

    alarm = await Alarm.get(follow_up_visit_id=visit.id)
    assert alarm.status == AlarmStatus.CANCELLED
    assert alarm.cancelled_at == datetime(2026, 9, 10, 10, tzinfo=KST)
