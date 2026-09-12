from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.enums import MealSlot

KST = ZoneInfo("Asia/Seoul")
SLOT_ORDER = {slot: index for index, slot in enumerate(MealSlot)}


@dataclass(frozen=True)
class GoalWindow:
    source_id: int
    slot: MealSlot
    first_date: date
    last_date: date | None


@dataclass(frozen=True)
class PlannedGoal:
    source_id: int
    scheduled_date: date
    slot: MealSlot
    scheduled_at: datetime


GoalKey = tuple[int, date, MealSlot]


def seven_day_end(joined_at: datetime) -> datetime:
    joined_kst = _as_kst(joined_at, "joined_at")
    return datetime.combine(joined_kst.date() + timedelta(days=7), time.min, tzinfo=KST)


def plan_goals(
    *,
    windows: Sequence[GoalWindow],
    meal_times: Mapping[MealSlot, time],
    joined_at: datetime,
    end_at: datetime,
    not_before: datetime | None = None,
    preserved_keys: Collection[GoalKey] = (),
    existing_keys: Collection[GoalKey] = (),
    include_join_slot: bool = False,
    excluded_keys: Collection[GoalKey] = (),
) -> list[PlannedGoal]:
    joined_kst = _as_kst(joined_at, "joined_at")
    end_kst = _as_kst(end_at, "end_at")
    if end_kst <= joined_kst:
        raise ValueError("end_at must be after joined_at")

    lower_bound = joined_kst
    if include_join_slot:
        # Use all configured slots, not just this source's assigned slots. A
        # missing/already-taken current slot must not fall back to an older one.
        elapsed_times = [value for value in meal_times.values() if value <= joined_kst.time()]
        if elapsed_times:
            lower_bound = datetime.combine(joined_kst.date(), max(elapsed_times), tzinfo=KST)
    if not_before is not None:
        lower_bound = max(joined_kst, lower_bound, _as_kst(not_before, "not_before"))

    preserved = set(preserved_keys)
    existing = set(existing_keys)
    excluded = set(excluded_keys)
    planned_by_key: dict[GoalKey, PlannedGoal] = {}
    for window in windows:
        meal_time = meal_times.get(window.slot)
        if meal_time is None:
            continue

        scheduled_date = max(window.first_date, lower_bound.date())
        last_date = min(window.last_date or end_kst.date(), end_kst.date())
        while scheduled_date <= last_date:
            key = (window.source_id, scheduled_date, window.slot)
            scheduled_at = datetime.combine(scheduled_date, meal_time, tzinfo=KST)
            if (
                key not in preserved
                and key not in excluded
                and scheduled_at < end_kst
                and (lower_bound <= scheduled_at or key in existing)
            ):
                planned_by_key.setdefault(
                    key,
                    PlannedGoal(
                        source_id=window.source_id,
                        scheduled_date=scheduled_date,
                        slot=window.slot,
                        scheduled_at=scheduled_at,
                    ),
                )
            scheduled_date += timedelta(days=1)

    return sorted(
        planned_by_key.values(),
        key=lambda goal: (goal.scheduled_at, goal.source_id, SLOT_ORDER[goal.slot]),
    )


def _as_kst(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(KST)
