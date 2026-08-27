from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core import config
from app.dtos.alarms import AlarmCreateRequest
from app.models.enums import AlarmType, MealSlot
from app.services.alarm_schedule import next_occurrence, parse_timezone


def test_medication_requires_meal_slot():
    with pytest.raises(ValidationError):
        AlarmCreateRequest(
            alarm_type=AlarmType.MEDICATION,
            title="아침약",
            scheduled_at="2026-08-20T08:00:00+09:00",
            timezone="Asia/Seoul",
        )


def test_nutrient_requires_meal_slot():
    with pytest.raises(ValidationError):
        AlarmCreateRequest(
            alarm_type=AlarmType.NUTRIENT,
            title="아침 영양제",
            scheduled_at="2026-08-20T08:00:00+09:00",
            timezone="Asia/Seoul",
        )


def test_nutrient_accepts_meal_slot():
    request = AlarmCreateRequest(
        alarm_type=AlarmType.NUTRIENT,
        meal_slot=MealSlot.MORNING,
        title="아침 영양제",
        scheduled_at="2026-08-20T08:00:00+09:00",
        timezone="Asia/Seoul",
    )

    assert request.meal_slot == MealSlot.MORNING


def test_non_medication_rejects_meal_slot():
    with pytest.raises(ValidationError):
        AlarmCreateRequest(
            alarm_type=AlarmType.FOLLOW_UP_VISIT,
            meal_slot=MealSlot.MORNING,
            title="외래 일정",
            scheduled_at="2026-08-20T08:00:00+09:00",
            timezone="Asia/Seoul",
        )


def test_alarm_create_request_uses_config_timezone_by_default(monkeypatch):
    monkeypatch.setattr(config, "TIMEZONE", parse_timezone("UTC"))

    request = AlarmCreateRequest(
        alarm_type=AlarmType.FOLLOW_UP_VISIT,
        title="외래 일정",
        scheduled_at="2026-08-20T08:00:00+00:00",
    )

    assert request.timezone == "UTC"


def test_rrule_returns_next_occurrence():
    start = datetime.fromisoformat("2026-08-20T08:00:00+09:00")

    result = next_occurrence("FREQ=DAILY", start, start)

    assert result == datetime.fromisoformat("2026-08-21T08:00:00+09:00")


def test_invalid_timezone_is_rejected():
    with pytest.raises(ValueError, match="Invalid timezone"):
        parse_timezone("Not/AZone")
