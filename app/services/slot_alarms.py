from datetime import date, datetime, time, timedelta

from tortoise.backends.base.client import BaseDBAsyncClient

from app.core import config
from app.models.alarms import Alarm
from app.models.enums import AlarmStatus, AlarmType, MealSlot

SLOT_ORDER = (MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME)
SlotWindow = tuple[date, date | None]


async def sync_slot_alarms(
    *,
    user_id: int,
    alarm_type: AlarmType,
    meal_times: dict[MealSlot, time],
    windows: dict[MealSlot, list[SlotWindow]],
    title: str,
    message: str,
    connection: BaseDBAsyncClient,
) -> None:
    now = datetime.now(config.TIMEZONE)
    existing = {
        alarm.meal_slot: alarm
        for alarm in await Alarm.filter(user_id=user_id, alarm_type=alarm_type).using_db(connection).select_for_update()
    }

    for slot in SLOT_ORDER:
        await _sync_slot_alarm(
            user_id=user_id,
            alarm_type=alarm_type,
            slot=slot,
            alarm_time=meal_times[slot],
            windows=windows[slot],
            title=title,
            message=message,
            alarm=existing.get(slot),
            now=now,
            connection=connection,
        )


async def _sync_slot_alarm(
    *,
    user_id: int,
    alarm_type: AlarmType,
    slot: MealSlot,
    alarm_time: time,
    windows: list[SlotWindow],
    title: str,
    message: str,
    alarm: Alarm | None,
    now: datetime,
    connection: BaseDBAsyncClient,
) -> None:
    schedule = _next_alarm_schedule(windows, alarm_time, now)
    if schedule is None:
        if alarm is not None and alarm.status != AlarmStatus.CANCELLED:
            alarm.status = AlarmStatus.CANCELLED
            alarm.cancelled_at = now
            alarm.updated_at = now
            await alarm.save(
                using_db=connection,
                update_fields=["status", "cancelled_at", "updated_at"],
            )
        return

    next_trigger_at, last_date = schedule
    recurrence_rule = "FREQ=DAILY"
    if last_date is not None:
        occurrence_count = (last_date - next_trigger_at.date()).days + 1
        recurrence_rule = f"FREQ=DAILY;COUNT={occurrence_count}"
    values = {
        "care_episode_id": None,
        "title": title,
        "message": message,
        "scheduled_at": next_trigger_at,
        "recurrence_rule": recurrence_rule,
        "timezone": str(config.TIMEZONE),
        "next_trigger_at": next_trigger_at,
        "status": AlarmStatus.ACTIVE,
        "last_triggered_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "updated_at": now,
    }
    if alarm is None:
        await Alarm.create(
            using_db=connection,
            user_id=user_id,
            alarm_type=alarm_type,
            meal_slot=slot,
            **values,
        )
        return

    for field_name, value in values.items():
        setattr(alarm, field_name, value)
    await alarm.save(using_db=connection, update_fields=list(values))


def _next_alarm_schedule(
    windows: list[SlotWindow],
    alarm_time: time,
    now: datetime,
) -> tuple[datetime, date | None] | None:
    candidates: list[tuple[datetime, date | None]] = []
    for first_date, last_date in windows:
        candidate_date = max(first_date, now.date())
        candidate = datetime.combine(candidate_date, alarm_time, tzinfo=config.TIMEZONE)
        if candidate <= now:
            candidate += timedelta(days=1)
        if last_date is None or candidate.date() <= last_date:
            candidates.append((candidate, last_date))
    if not candidates:
        return None

    next_trigger_at = min(candidate for candidate, _ in candidates)
    candidate_end_dates = [last_date for _, last_date in candidates]
    if any(last_date is None for last_date in candidate_end_dates):
        return next_trigger_at, None
    return next_trigger_at, max(last_date for last_date in candidate_end_dates if last_date is not None)
