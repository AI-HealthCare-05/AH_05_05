from datetime import datetime, time

import pytest

from app.core import config
from app.core.exceptions import InvalidMedicationScheduleError
from app.dtos.medication_schedule import SaveMedicationScheduleRequest
from app.services.medication_schedule import MedicationScheduleService


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("08:01", time(8, 1)),
        ("13:17", time(13, 17)),
        ("22:59", time(22, 59)),
    ],
)
def test_parse_time_allows_each_minute_of_a_valid_day(value: str, expected: time) -> None:
    assert MedicationScheduleService._parse_time(value) == expected


@pytest.mark.parametrize("value", ["24:00", "08:60", "invalid"])
def test_parse_time_rejects_invalid_clock_values(value: str) -> None:
    with pytest.raises(InvalidMedicationScheduleError):
        MedicationScheduleService._parse_time(value)


def test_validate_request_rejects_meal_times_out_of_order() -> None:
    request = SaveMedicationScheduleRequest.model_validate(
        {
            "start": {"date": datetime.now(config.TIMEZONE).date().isoformat(), "slot": "morning"},
            "mealTimes": {
                "morning": "08:01",
                "lunch": "08:00",
                "evening": "18:17",
                "bedtime": "22:59",
            },
            "medications": [],
        }
    )

    with pytest.raises(InvalidMedicationScheduleError):
        MedicationScheduleService._validate_request(request)
