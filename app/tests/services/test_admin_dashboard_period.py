"""app/services/admin_dashboard.py 의 기간 경계 계산 테스트.

대시보드의 가입자 수·알람 발송 수·탈퇴 비율이 전부 day_range 를 지난다.
하루가 어긋나도 화면에는 그럴듯한 숫자가 뜨므로 경계를 명시적으로 고정한다.

날짜는 date(...) 로 박는다. date.today() 를 쓰면 실행일에 따라 결과가 달라진다.
시간대는 config.TIMEZONE 을 가져다 비교한다 — 설정이 바뀌면 같이 따라가야 한다.
"""

from datetime import date, datetime, time, timedelta

import pytest

from app.core import config
from app.services.admin_dashboard import day_range, day_start

# ──────────────────────────────── day_start ────────────────────────────────


def test_day_start_is_midnight() -> None:
    result = day_start(date(2026, 9, 5))

    assert result.date() == date(2026, 9, 5)
    assert result.timetz().replace(tzinfo=None) == time(0, 0, 0)
    assert (result.hour, result.minute, result.second, result.microsecond) == (0, 0, 0, 0)


def test_day_start_is_timezone_aware() -> None:
    """naive datetime 이 나오면 DB 비교에서 UTC 로 해석돼 9시간이 밀린다."""
    result = day_start(date(2026, 9, 5))

    assert result.tzinfo is not None


def test_day_start_uses_the_configured_timezone() -> None:
    result = day_start(date(2026, 9, 5))

    assert result.tzinfo == config.TIMEZONE


# ──────────────────────────────── day_range ────────────────────────────────


def test_day_range_starts_at_the_first_day_midnight() -> None:
    start, _ = day_range(date(2026, 9, 1), date(2026, 9, 5))

    assert start == day_start(date(2026, 9, 1))


def test_day_range_ends_at_the_day_after_the_last_day() -> None:
    """끝은 last 의 자정이 **아니라** last + 1일의 자정이다.

    `<= last` 로 잡으면 종료일 당일이 통째로 누락된다(함수 docstring 참고).
    """
    _, end = day_range(date(2026, 9, 1), date(2026, 9, 5))

    assert end == day_start(date(2026, 9, 6))
    assert end != day_start(date(2026, 9, 5))


def test_day_range_includes_every_moment_of_the_last_day() -> None:
    """종료일 당일 23:59 가 구간에 들어간다. 끝은 포함되지 않는 경계다."""
    last = date(2026, 9, 5)
    start, end = day_range(date(2026, 9, 1), last)

    last_evening = day_start(last) + timedelta(hours=23, minutes=59)

    assert start <= last_evening < end


def test_day_range_includes_the_very_last_microsecond_of_the_last_day() -> None:
    """마지막 순간까지 들어가되, 그 다음 마이크로초(= end)는 빠진다."""
    last = date(2026, 9, 5)
    start, end = day_range(date(2026, 9, 1), last)

    last_moment = end - timedelta(microseconds=1)

    assert start <= last_moment < end
    assert last_moment.date() == last


def test_day_range_of_a_single_day_spans_exactly_24_hours() -> None:
    day = date(2026, 9, 5)
    start, end = day_range(day, day)

    assert start == day_start(day)
    assert end - start == timedelta(days=1)


@pytest.mark.parametrize(
    ("last", "expected_end_day"),
    [
        (date(2026, 1, 31), date(2026, 2, 1)),  # 월 경계
        (date(2026, 12, 31), date(2027, 1, 1)),  # 연 경계
        (date(2024, 2, 28), date(2024, 2, 29)),  # 윤년 — 2월 29일이 존재한다
        (date(2026, 2, 28), date(2026, 3, 1)),  # 평년 — 곧바로 3월
        (date(2024, 2, 29), date(2024, 3, 1)),  # 윤일 자체
    ],
)
def test_day_range_crosses_month_year_and_leap_boundaries(last: date, expected_end_day: date) -> None:
    _, end = day_range(last, last)

    assert end == day_start(expected_end_day)


def test_day_range_does_not_validate_reversed_input() -> None:
    """first > last 를 막지 않는다. 시작이 끝보다 뒤인 빈 구간이 나온다.

    고쳐야 한다는 뜻이 아니라, 호출부가 뒤집힌 값을 넣지 않는다는 전제를 남기는 것이다.
    현재 호출부(DashboardSummaryQuery)는 period 로 기간을 만들어 뒤집히지 않는다.
    """
    start, end = day_range(date(2026, 9, 10), date(2026, 9, 1))

    assert start == day_start(date(2026, 9, 10))
    assert end == day_start(date(2026, 9, 2))
    assert start > end  # 어떤 시각도 이 구간에 들어가지 않는다


def test_day_range_length_matches_the_inclusive_day_count() -> None:
    """[first, last] 를 사람이 세는 방식(양끝 포함)과 구간 길이가 맞는다."""
    first, last = date(2026, 9, 1), date(2026, 9, 14)
    start, end = day_range(first, last)

    inclusive_days = (last - first).days + 1

    assert end - start == timedelta(days=inclusive_days)
    assert inclusive_days == 14


def test_day_range_boundaries_are_timezone_aware() -> None:
    start, end = day_range(date(2026, 9, 1), date(2026, 9, 5))

    assert start.tzinfo == config.TIMEZONE
    assert end.tzinfo == config.TIMEZONE


def test_day_range_end_is_exclusive_for_the_next_day_start() -> None:
    """다음 날 00:00 은 구간에 들어가지 않는다 — 반열린 구간의 정의."""
    last = date(2026, 9, 5)
    _, end = day_range(date(2026, 9, 1), last)

    next_day_midnight = day_start(last + timedelta(days=1))

    assert next_day_midnight == end
    assert not (next_day_midnight < end)


def test_day_start_and_day_range_agree_on_the_same_day() -> None:
    day = date(2026, 9, 5)
    start, _ = day_range(day, day)

    assert start == day_start(day)
    assert isinstance(start, datetime)
