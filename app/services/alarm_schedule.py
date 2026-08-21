from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

from app.models.enums import AlarmType, MealSlot


def parse_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Invalid timezone.") from exc


def validate_alarm_shape(alarm_type: AlarmType, meal_slot: MealSlot | None) -> None:
    if alarm_type == AlarmType.MEDICATION and meal_slot is None:
        raise ValueError("meal_slot is required for medication alarms.")
    if alarm_type != AlarmType.MEDICATION and meal_slot is not None:
        raise ValueError("meal_slot is only allowed for medication alarms.")


def next_occurrence(rule: str, dtstart: datetime, after: datetime) -> datetime | None:
    try:
        return rrulestr(rule, dtstart=dtstart).after(after, inc=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid recurrence rule.") from exc
