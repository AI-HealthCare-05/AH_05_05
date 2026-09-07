from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.challenge_periods import build_progress_periods

STARTED_AT = datetime(2026, 9, 7, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))


@pytest.mark.parametrize(
    ("period_code", "expected_count"),
    (("D7", 7), ("D14", 14), ("D30", 30)),
)
def test_daily_creates_one_target_for_each_challenge_day(
    period_code: str,
    expected_count: int,
) -> None:
    periods = build_progress_periods(STARTED_AT, period_code, "DAILY")

    assert len(periods) == expected_count
    assert sum(period.target_count for period in periods) == expected_count
    assert periods[0].period_start.isoformat() == "2026-09-07"


def test_d30_weekly_3_excludes_trailing_two_days() -> None:
    periods = build_progress_periods(STARTED_AT, "D30", "WEEKLY_3")

    assert len(periods) == 4
    assert sum(period.target_count for period in periods) == 12
    assert periods[-1].period_end.isoformat() == "2026-10-04"


def test_total_10_uses_one_full_period() -> None:
    periods = build_progress_periods(STARTED_AT, "D14", "TOTAL_10")

    assert len(periods) == 1
    assert periods[0].target_count == 10
    assert periods[0].period_start.isoformat() == "2026-09-07"
    assert periods[0].period_end.isoformat() == "2026-09-20"


@pytest.mark.parametrize(
    ("period_code", "frequency_code"),
    (("D10", "DAILY"), ("D7", "WEEKLY_5")),
)
def test_unknown_challenge_codes_are_rejected(period_code: str, frequency_code: str) -> None:
    with pytest.raises(ValueError):
        build_progress_periods(STARTED_AT, period_code, frequency_code)
