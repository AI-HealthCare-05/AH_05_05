from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.models.enums import MealSlot
from app.services.custom_challenge_goal_planner import GoalWindow, plan_goals, seven_day_end

KST = ZoneInfo("Asia/Seoul")


def test_seven_day_plan_starts_after_a_missed_join_day_slot() -> None:
    joined = datetime(2026, 9, 10, 9, tzinfo=KST)

    goals = plan_goals(
        windows=[GoalWindow(7, MealSlot.MORNING, date(2026, 9, 10), None)],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=joined,
        end_at=seven_day_end(joined),
    )

    assert [goal.scheduled_date for goal in goals] == [date(2026, 9, day) for day in range(11, 17)]
    assert seven_day_end(joined) == datetime(2026, 9, 17, tzinfo=KST)


def test_goal_exactly_at_join_is_included() -> None:
    joined = datetime(2026, 9, 10, 8, tzinfo=KST)

    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10))],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=joined,
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert [goal.scheduled_at for goal in goals] == [joined]


def test_goal_before_join_is_excluded() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 11))],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=datetime(2026, 9, 10, 8, 1, tzinfo=KST),
        end_at=datetime(2026, 9, 12, tzinfo=KST),
    )

    assert [goal.scheduled_at for goal in goals] == [datetime(2026, 9, 11, 8, tzinfo=KST)]


def test_goal_exactly_at_end_is_excluded() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 11))],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, 8, tzinfo=KST),
    )

    assert [goal.scheduled_at for goal in goals] == [datetime(2026, 9, 10, 8, tzinfo=KST)]


def test_utc_join_is_compared_by_its_kst_local_date_and_time() -> None:
    joined_utc = datetime(2026, 9, 10, 15, 30, tzinfo=UTC)

    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), None)],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=joined_utc,
        end_at=seven_day_end(joined_utc),
    )

    assert [goal.scheduled_date for goal in goals] == [date(2026, 9, day) for day in range(11, 18)]
    assert seven_day_end(joined_utc) == datetime(2026, 9, 18, tzinfo=KST)


def test_source_last_date_stops_goals_early() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.LUNCH, date(2026, 9, 10), date(2026, 9, 12))],
        meal_times={MealSlot.LUNCH: time(13)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 17, tzinfo=KST),
    )

    assert [goal.scheduled_date for goal in goals] == [date(2026, 9, day) for day in range(10, 13)]


def test_source_first_date_can_start_after_participation_begins() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.EVENING, date(2026, 9, 13), None)],
        meal_times={MealSlot.EVENING: time(19)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 17, tzinfo=KST),
    )

    assert [goal.scheduled_date for goal in goals] == [date(2026, 9, day) for day in range(13, 17)]


def test_unbounded_source_is_bounded_by_seven_day_participation_end() -> None:
    joined = datetime(2026, 9, 10, tzinfo=KST)

    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.BEDTIME, date(2026, 9, 1), None)],
        meal_times={MealSlot.BEDTIME: time(22)},
        joined_at=joined,
        end_at=seven_day_end(joined),
    )

    assert len(goals) == 7
    assert goals[-1].scheduled_at == datetime(2026, 9, 16, 22, tzinfo=KST)


def test_duplicate_windows_collapse_by_source_date_and_slot() -> None:
    window = GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10))

    goals = plan_goals(
        windows=[window, window],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert [(goal.source_id, goal.scheduled_date, goal.slot) for goal in goals] == [
        (1, date(2026, 9, 10), MealSlot.MORNING)
    ]


def test_different_sources_at_the_same_slot_do_not_collapse() -> None:
    goals = plan_goals(
        windows=[
            GoalWindow(2, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10)),
            GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10)),
        ],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert [goal.source_id for goal in goals] == [1, 2]


def test_results_are_ordered_by_timestamp_source_and_meal_slot_order() -> None:
    goals = plan_goals(
        windows=[
            GoalWindow(2, MealSlot.EVENING, date(2026, 9, 10), date(2026, 9, 10)),
            GoalWindow(2, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10)),
            GoalWindow(1, MealSlot.LUNCH, date(2026, 9, 10), date(2026, 9, 10)),
        ],
        meal_times={MealSlot.MORNING: time(8), MealSlot.LUNCH: time(8), MealSlot.EVENING: time(8)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert [(goal.source_id, goal.slot) for goal in goals] == [
        (1, MealSlot.LUNCH),
        (2, MealSlot.MORNING),
        (2, MealSlot.EVENING),
    ]


def test_missing_slot_time_is_skipped() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), None)],
        meal_times={},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert goals == []


def test_empty_windows_produce_no_goals() -> None:
    goals = plan_goals(
        windows=[],
        meal_times={MealSlot.MORNING: time(8)},
        joined_at=datetime(2026, 9, 10, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
    )

    assert goals == []


@pytest.mark.parametrize("timestamp_name", ["joined_at", "end_at", "not_before"])
def test_naive_timestamps_are_rejected(timestamp_name: str) -> None:
    timestamps = {
        "joined_at": datetime(2026, 9, 10, tzinfo=KST),
        "end_at": datetime(2026, 9, 11, tzinfo=KST),
        "not_before": datetime(2026, 9, 10, tzinfo=KST),
    }
    timestamps[timestamp_name] = timestamps[timestamp_name].replace(tzinfo=None)

    with pytest.raises(ValueError, match=timestamp_name):
        plan_goals(
            windows=[],
            meal_times={},
            joined_at=timestamps["joined_at"],
            end_at=timestamps["end_at"],
            not_before=timestamps["not_before"],
        )


def test_seven_day_end_rejects_a_naive_join_timestamp() -> None:
    with pytest.raises(ValueError, match="joined_at"):
        seven_day_end(datetime(2026, 9, 10, 9))


@pytest.mark.parametrize(
    "end_at",
    [datetime(2026, 9, 10, 9, tzinfo=KST), datetime(2026, 9, 10, 8, 59, tzinfo=KST)],
)
def test_end_must_be_after_join(end_at: datetime) -> None:
    with pytest.raises(ValueError, match="end_at"):
        plan_goals(
            windows=[],
            meal_times={},
            joined_at=datetime(2026, 9, 10, 9, tzinfo=KST),
            end_at=end_at,
        )


def test_schedule_change_uses_change_time_not_a_later_read_time() -> None:
    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 10))],
        meal_times={MealSlot.MORNING: time(9)},
        joined_at=datetime(2026, 9, 10, 6, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
        not_before=datetime(2026, 9, 10, 7, tzinfo=KST),
    )

    assert [goal.scheduled_at for goal in goals] == [datetime(2026, 9, 10, 9, tzinfo=KST)]


def test_preserved_past_key_wins_over_a_rescheduled_future_time() -> None:
    preserved_key = (1, date(2026, 9, 10), MealSlot.MORNING)

    goals = plan_goals(
        windows=[GoalWindow(1, MealSlot.MORNING, date(2026, 9, 10), date(2026, 9, 11))],
        meal_times={MealSlot.MORNING: time(10)},
        joined_at=datetime(2026, 9, 10, 6, tzinfo=KST),
        end_at=datetime(2026, 9, 12, tzinfo=KST),
        not_before=datetime(2026, 9, 10, 9, tzinfo=KST),
        preserved_keys={preserved_key},
    )

    assert [(goal.scheduled_date, goal.scheduled_at) for goal in goals] == [
        (date(2026, 9, 11), datetime(2026, 9, 11, 10, tzinfo=KST))
    ]


def test_only_existing_key_can_move_before_change_and_join_boundaries() -> None:
    existing_evening = (1, date(2026, 9, 10), MealSlot.EVENING)

    goals = plan_goals(
        windows=[
            GoalWindow(1, MealSlot.LUNCH, date(2026, 9, 10), date(2026, 9, 10)),
            GoalWindow(1, MealSlot.EVENING, date(2026, 9, 10), date(2026, 9, 10)),
        ],
        meal_times={MealSlot.LUNCH: time(13), MealSlot.EVENING: time(16)},
        joined_at=datetime(2026, 9, 10, 16, 48, tzinfo=KST),
        end_at=datetime(2026, 9, 11, tzinfo=KST),
        not_before=datetime(2026, 9, 10, 17, tzinfo=KST),
        existing_keys={existing_evening},
    )

    assert [(goal.scheduled_date, goal.slot, goal.scheduled_at) for goal in goals] == [
        (date(2026, 9, 10), MealSlot.EVENING, datetime(2026, 9, 10, 16, tzinfo=KST))
    ]
