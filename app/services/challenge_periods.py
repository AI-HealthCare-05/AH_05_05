from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core import config

_PERIOD_DAYS = {"D7": 7, "D14": 14, "D30": 30}


@dataclass(frozen=True)
class ProgressPeriod:
    period_start: date
    period_end: date
    target_count: int


def build_progress_periods(
    started_at: datetime,
    period_code: str,
    frequency_code: str,
) -> list[ProgressPeriod]:
    try:
        duration_days = _PERIOD_DAYS[period_code]
    except KeyError as error:
        raise ValueError(f"Unsupported challenge period: {period_code}") from error

    start_date = started_at.astimezone(config.TIMEZONE).date()
    if frequency_code == "DAILY":
        return [
            ProgressPeriod(
                period_start=start_date + timedelta(days=offset),
                period_end=start_date + timedelta(days=offset),
                target_count=1,
            )
            for offset in range(duration_days)
        ]
    if frequency_code == "WEEKLY_3":
        return [
            ProgressPeriod(
                period_start=start_date + timedelta(days=week * 7),
                period_end=start_date + timedelta(days=week * 7 + 6),
                target_count=3,
            )
            for week in range(duration_days // 7)
        ]
    if frequency_code == "TOTAL_10":
        return [
            ProgressPeriod(
                period_start=start_date,
                period_end=start_date + timedelta(days=duration_days - 1),
                target_count=10,
            )
        ]
    raise ValueError(f"Unsupported challenge frequency: {frequency_code}")
