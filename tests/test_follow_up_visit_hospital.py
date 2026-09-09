"""Hospital contract tests; run with --noconftest to use only in-memory SQLite."""

import sqlite3
from collections.abc import AsyncIterator
from datetime import date, time

import pytest
import pytest_asyncio
from fastapi import HTTPException
from tortoise import Tortoise

from app.dtos.follow_up_visits import FollowUpVisitUpdateRequest
from app.models.care import FollowUpVisit
from app.models.users import User
from app.services.follow_up_visits import FollowUpVisitService


@pytest_asyncio.fixture(loop_scope="function")
async def owner(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[User]:
    # MySQL accepts native time values; SQLite needs an explicit bind adapter.
    monkeypatch.setitem(sqlite3.adapters, (time, sqlite3.PrepareProtocol), lambda value: value.isoformat())
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["app.models.users", "app.models.care", "app.models.alarms"]},
        timezone="Asia/Seoul",
    )
    await Tortoise.generate_schemas()
    try:
        yield await User.create(email="hospital-owner@example.com", hashed_password="unused", name="사용자")
    finally:
        await Tortoise.close_connections()


@pytest.mark.parametrize("hospital", [None, "", " \t "])
@pytest.mark.parametrize("updates", [{}, {"visit_time": "13:30:00"}, {"visit_date": "2026-09-12"}])
async def test_legacy_visit_cannot_be_updated_without_valid_hospital(owner: User, hospital, updates) -> None:
    visit = await FollowUpVisit.create(user=owner, visit_date=date(2026, 9, 10), hospital=hospital)

    with pytest.raises(HTTPException) as error:
        await FollowUpVisitService().update(owner, visit.id, FollowUpVisitUpdateRequest(**updates))

    assert error.value.status_code == 422
    await visit.refresh_from_db()
    assert visit.hospital == hospital
    assert visit.visit_time is None
    assert visit.visit_date == date(2026, 9, 10)
    assert visit.updated_at is None


@pytest.mark.parametrize("hospital", [None, "", " \t "])
async def test_legacy_visit_can_be_repaired_with_valid_hospital(owner: User, hospital) -> None:
    visit = await FollowUpVisit.create(user=owner, visit_date=date(2026, 9, 10), hospital=hospital)

    response = await FollowUpVisitService().update(
        owner, visit.id, FollowUpVisitUpdateRequest(hospital="  내과  ", visit_time=time(13, 30))
    )

    await visit.refresh_from_db()
    assert response.hospital == visit.hospital == "내과"
    assert response.visit_time == time(13, 30)


async def test_patch_without_hospital_preserves_existing_name(owner: User) -> None:
    visit = await FollowUpVisit.create(
        user=owner, visit_date=date(2026, 9, 10), visit_time=time(13, 30), hospital="○○이비인후과"
    )

    response = await FollowUpVisitService().update(owner, visit.id, FollowUpVisitUpdateRequest(visit_time=None))

    await visit.refresh_from_db()
    assert response.hospital == visit.hospital == "○○이비인후과"
    assert response.visit_time is None


@pytest.mark.parametrize("hospital", [None, "", " \t "])
async def test_legacy_visit_remains_readable_and_deletable(owner: User, hospital) -> None:
    visit = await FollowUpVisit.create(user=owner, visit_date=date(2026, 9, 10), hospital=hospital)
    service = FollowUpVisitService()

    assert (await service.get(owner, visit.id)).hospital == hospital
    listed = await service.list(owner, start_date=None, end_date=None, offset=0, limit=20)
    assert listed.total == 1
    assert listed.items[0].hospital == hospital
    await service.delete(owner, visit.id)
    assert not await FollowUpVisit.filter(id=visit.id).exists()


async def test_legacy_hospital_validation_does_not_expose_another_users_visit(owner: User) -> None:
    other = await User.create(email="other@example.com", hashed_password="unused", name="다른 사용자")
    visit = await FollowUpVisit.create(user=other, visit_date=date(2026, 9, 10))

    with pytest.raises(HTTPException) as error:
        await FollowUpVisitService().update(owner, visit.id, FollowUpVisitUpdateRequest(visit_time=time(13, 30)))

    assert error.value.status_code == 404
