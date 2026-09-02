from datetime import time
from types import SimpleNamespace

import pytest

from app.services.follow_up_visit_alarms import follow_up_message


@pytest.mark.parametrize(
    ("visit_time", "hospital", "expected"),
    [
        (time(14, 30), "서울성모병원", "내일 14:30 서울성모병원 진료가 있어요"),
        (None, "서울성모병원", "내일 서울성모병원 진료가 있어요"),
        (None, None, "내일 진료 일정이 있어요"),
    ],
)
def test_follow_up_message_uses_only_current_visit_details(
    visit_time: time | None,
    hospital: str | None,
    expected: str,
) -> None:
    visit = SimpleNamespace(visit_time=visit_time, hospital=hospital)

    assert follow_up_message(visit) == expected
