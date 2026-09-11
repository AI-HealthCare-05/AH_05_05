from datetime import date, time

import pytest
import pytest_asyncio
from tortoise import Tortoise

from ai_worker.providers.db_follow_up_schedule_provider import DbFollowUpScheduleProvider
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.care import FollowUpVisit
from app.models.users import User


@pytest_asyncio.fixture
async def initialized_db() -> None:
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": TORTOISE_APP_MODELS},
        timezone="Asia/Seoul",
        use_tz=False,
    )
    await Tortoise.generate_schemas()
    yield
    await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_list_upcoming_schedules_limits_to_future_visits_owned_by_user(
    initialized_db: None,
) -> None:
    owner = await User.create(
        email="owner@example.com",
        hashed_password="hashed-password",
        name="소유자",
    )
    other_user = await User.create(
        email="other@example.com",
        hashed_password="hashed-password",
        name="다른 사용자",
    )
    await FollowUpVisit.create(
        user=owner,
        visit_date=date(2026, 9, 9),
        hospital="지난 일정 병원",
    )
    await FollowUpVisit.create(
        user=owner,
        visit_date=date(2026, 9, 12),
        visit_time=time(14, 30),
        hospital="가까운 일정 병원",
    )
    await FollowUpVisit.create(
        user=owner,
        visit_date=date(2026, 9, 14),
        hospital="다음 일정 병원",
    )
    await FollowUpVisit.create(
        user=other_user,
        visit_date=date(2026, 9, 11),
        hospital="다른 사용자 병원",
    )

    schedules = await DbFollowUpScheduleProvider(
        today_provider=lambda: date(2026, 9, 10),
    ).list_upcoming_schedules(
        user_id=owner.id,
        limit=1,
    )

    assert len(schedules) == 1
    assert schedules[0].hospital == "가까운 일정 병원"
    assert schedules[0].visit_time == time(14, 30)
    assert schedules[0].visit_at is not None
    assert schedules[0].visit_at.strftime("%Y-%m-%d %H:%M") == "2026-09-12 14:30"
