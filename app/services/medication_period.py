from collections.abc import Sequence
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.core.exceptions import InvalidMedicationOverviewDateRangeError
from app.models.care import CareEpisode
from app.models.medications import Medication

DEFAULT_OVERVIEW_MONTHS = 6
MAX_OVERVIEW_YEARS = 2
UNKNOWN_DAYS = 1


def resolve_medication_overview_range(
    from_date: date | None,
    to_date: date | None,
    today: date,
) -> tuple[date, date]:
    if from_date is None and to_date is None:
        resolved_from = today - relativedelta(months=DEFAULT_OVERVIEW_MONTHS)
        resolved_to = today
    elif from_date is not None and to_date is None:
        resolved_from = from_date
        resolved_to = from_date + relativedelta(months=DEFAULT_OVERVIEW_MONTHS)
    elif from_date is None and to_date is not None:
        resolved_from = today
        resolved_to = to_date
    else:
        resolved_from = from_date
        resolved_to = to_date

    earliest_date = today - relativedelta(years=MAX_OVERVIEW_YEARS)
    if (
        resolved_from is None
        or resolved_to is None
        or resolved_from > resolved_to
        or resolved_from < earliest_date
        or resolved_to > today
    ):
        raise InvalidMedicationOverviewDateRangeError()
    return resolved_from, resolved_to


def medication_end_date(episode: CareEpisode, medications: Sequence[Medication]) -> date:
    start_date = episode.medication_start_date
    if start_date is None:
        raise ValueError("Medication end date requires a start date")

    known_days = [medication.days for medication in medications if medication.days is not None]
    fallback_days = episode.medication_days or (max(known_days) if known_days else UNKNOWN_DAYS)
    all_days = [medication.days or fallback_days for medication in medications]
    scheduled_days = [
        medication.days or fallback_days for medication in medications if medication.times_per_day is not None
    ]
    longest_days = max(scheduled_days or all_days or [fallback_days])
    return start_date + timedelta(days=longest_days - 1)
