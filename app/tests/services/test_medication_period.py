"""날짜·기간 계산 5개 테스트 — 박준영님·신동훈님 코드 대상. 동작 변경은 없다.

    app/services/medication_period.py
      resolve_medication_overview_range · medication_end_date
    app/dtos/medication_guide_ocr.py
      MedicationGuideConfirmRequest.validate_dispensing_date
      DocumentOcrConfirmRequest.reject_future_dispensing_date
    app/services/supplement_doses.py
      SupplementDoseService.validate_date
    app/services/medication_ocr_v3/pipeline/grounding.py
      seoul_today

접수 가능한 기간을 따지는 창구 규정이다. 정규화와 달리 틀리면 **경계에 딱 걸린
날짜만** 어긋난다. 하루 차이라 눈에 안 띄고 월말·윤년에만 터진다.

⚠️ 5개 중 4개가 오늘 날짜를 본다. 기대값을 하드코딩하면 작성한 날만 통과하므로
두 갈래로 나눠 쓴다.

  (가) 오늘을 인자로 받는 것(resolve_medication_overview_range)
       → date(2026, 3, 15) 같은 고정값을 넘긴다. 몇 년 뒤에도 같은 결과가 나온다.
  (나) 함수 안에서 오늘을 읽는 것(나머지)
       → config.TIMEZONE 기준으로 테스트 안에서 계산한다. date.today() 는 쓰지
         않는다 — 서버 로컬 시간대라 자정 근처에서 하루 어긋난다.

resolve_medication_overview_range 의 「종료일만 넘긴 경우」는 결함으로 판단해
여기서 고정하지 않았다. to 에 무엇을 넣어도 오늘 하루짜리이거나 거부다 → #278

DB·픽스처를 쓰지 않는다. ORM 객체는 SimpleNamespace 스텁으로 대체한다.
"""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
from pydantic import ValidationError

from app.core import config
from app.core.exceptions import InvalidMedicationOverviewDateRangeError
from app.dtos.medication_guide_ocr import DocumentOcrConfirmRequest, MedicationGuideConfirmRequest
from app.services.medication_ocr_v3.pipeline.grounding import seoul_today
from app.services.medication_period import (
    DEFAULT_OVERVIEW_MONTHS,
    MAX_OVERVIEW_YEARS,
    UNKNOWN_DAYS,
    medication_end_date,
    resolve_medication_overview_range,
)
from app.services.supplement_doses import SupplementDoseService

# (가) 오늘을 인자로 받는 함수용 고정 기준일. 실행 날짜와 무관하다.
TODAY = date(2026, 3, 15)


def seoul_now_date() -> date:
    """(나) 함수들이 보는 것과 같은 기준으로 오늘을 구한다."""
    return datetime.now(config.TIMEZONE).date()


def episode_stub(*, start: date | None = date(2026, 3, 1), days: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(medication_start_date=start, medication_days=days)


def medication_stub(*, days: int | None = None, times_per_day: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(days=days, times_per_day=times_per_day)


# ─────────────────── resolve_medication_overview_range — 4갈래 분기 ───────────────────


def test_range_defaults_to_the_last_six_months_when_nothing_is_given() -> None:
    assert resolve_medication_overview_range(None, None, TODAY) == (
        TODAY - relativedelta(months=DEFAULT_OVERVIEW_MONTHS),
        TODAY,
    )


def test_range_from_only_adds_six_months_to_the_start() -> None:
    start = TODAY - relativedelta(months=DEFAULT_OVERVIEW_MONTHS)

    assert resolve_medication_overview_range(start, None, TODAY) == (start, TODAY)


@pytest.mark.parametrize("months_ago", [0, 1, 3, 5])
def test_range_from_only_is_rejected_when_the_start_is_too_recent(months_ago: int) -> None:
    """현재 동작 — from 단독 조회는 6개월 이상 지난 날짜에만 쓸 수 있다.

    from + 6개월이 미래가 되면 `resolved_to > today` 로 걸린다. 최근 처방을
    시작일만으로 조회하려는 요청은 거부된다. #278 에 함께 적었다.
    """
    start = TODAY - relativedelta(months=months_ago)

    with pytest.raises(InvalidMedicationOverviewDateRangeError):
        resolve_medication_overview_range(start, None, TODAY)


def test_range_with_both_dates_uses_them_as_given() -> None:
    start, end = TODAY - timedelta(days=10), TODAY

    assert resolve_medication_overview_range(start, end, TODAY) == (start, end)


# ─────────────────── resolve_medication_overview_range — 거부 조건 ───────────────────


def test_range_rejects_a_reversed_pair() -> None:
    with pytest.raises(InvalidMedicationOverviewDateRangeError):
        resolve_medication_overview_range(TODAY, TODAY - timedelta(days=1), TODAY)


def test_range_accepts_the_two_year_boundary_itself() -> None:
    """2년 전 당일은 포함된다 — `<` 비교라 같은 날은 걸리지 않는다."""
    earliest = TODAY - relativedelta(years=MAX_OVERVIEW_YEARS)

    assert resolve_medication_overview_range(earliest, TODAY, TODAY) == (earliest, TODAY)


def test_range_rejects_one_day_before_the_two_year_boundary() -> None:
    earliest = TODAY - relativedelta(years=MAX_OVERVIEW_YEARS)

    with pytest.raises(InvalidMedicationOverviewDateRangeError):
        resolve_medication_overview_range(earliest - timedelta(days=1), TODAY, TODAY)


def test_range_accepts_today_as_the_end() -> None:
    start = TODAY - timedelta(days=5)

    assert resolve_medication_overview_range(start, TODAY, TODAY) == (start, TODAY)


def test_range_rejects_an_end_one_day_in_the_future() -> None:
    with pytest.raises(InvalidMedicationOverviewDateRangeError):
        resolve_medication_overview_range(TODAY - timedelta(days=5), TODAY + timedelta(days=1), TODAY)


def test_range_accepts_a_single_day_window() -> None:
    assert resolve_medication_overview_range(TODAY, TODAY, TODAY) == (TODAY, TODAY)


def test_range_none_guard_is_unreachable() -> None:
    """`resolved_from is None or resolved_to is None` 은 도달할 수 없다.

    네 갈래가 (None, None) · (값, None) · (None, 값) · (값, 값) 을 모두 덮고,
    각 갈래에서 두 변수가 반드시 채워진다. 타입 검사기를 위한 방어선으로 읽힌다
    (else 갈래에서 from_date 가 `date | None` 이라 좁혀지지 않는다).

    도달 불가라 별도 케이스를 두지 않고, 네 갈래가 모두 값을 채운다는 사실로 대신한다.
    """
    for from_date, to_date in [
        (None, None),
        (TODAY - relativedelta(months=DEFAULT_OVERVIEW_MONTHS), None),
        (TODAY, TODAY),
    ]:
        resolved_from, resolved_to = resolve_medication_overview_range(from_date, to_date, TODAY)
        assert resolved_from is not None
        assert resolved_to is not None


# ──────────── resolve_medication_overview_range — relativedelta 월말·윤년 ────────────


@pytest.mark.parametrize(
    ("today", "expected_start"),
    [
        (date(2026, 8, 31), date(2026, 2, 28)),  # 2월에 31일이 없어 말일로 맞춰진다
        (date(2026, 3, 31), date(2025, 9, 30)),
        (date(2024, 8, 31), date(2024, 2, 29)),  # 윤년이면 29일
        (date(2026, 3, 15), date(2025, 9, 15)),
    ],
)
def test_range_clamps_the_six_month_default_to_a_valid_month_end(today: date, expected_start: date) -> None:
    """relativedelta 는 timedelta 와 달리 「6개월 전 같은 날」을 찾고, 없으면 말일로 줄인다."""
    assert resolve_medication_overview_range(None, None, today) == (expected_start, today)


def test_range_two_year_boundary_on_a_leap_day() -> None:
    """2028-02-29 의 2년 전은 2026-02-28 이다 — 2026 은 윤년이 아니다."""
    today = date(2028, 2, 29)
    earliest = today - relativedelta(years=MAX_OVERVIEW_YEARS)

    assert earliest == date(2026, 2, 28)
    assert resolve_medication_overview_range(earliest, today, today) == (earliest, today)


# ──────────────────────────────── medication_end_date ────────────────────────────────


def test_medication_end_date_requires_a_start_date() -> None:
    with pytest.raises(ValueError, match="requires a start date"):
        medication_end_date(episode_stub(start=None), [])


def test_medication_end_date_counts_the_start_day_as_day_one() -> None:
    """5일치면 시작일 + 4일이다. 시작일이 이미 1일차다."""
    assert medication_end_date(episode_stub(days=5), []) == date(2026, 3, 5)
    assert medication_end_date(episode_stub(days=1), []) == date(2026, 3, 1)


def test_medication_end_date_prefers_the_episode_day_count() -> None:
    """fallback 1단계 — episode.medication_days 가 있으면 그것을 쓴다."""
    episode = episode_stub(days=5)
    medications = [medication_stub(days=None, times_per_day=1)]

    assert medication_end_date(episode, medications) == date(2026, 3, 5)


def test_medication_end_date_falls_back_to_the_longest_medication() -> None:
    """fallback 2단계 — episode 에 값이 없으면 약들의 days 최댓값을 쓴다."""
    medications = [medication_stub(days=3, times_per_day=1), medication_stub(days=7, times_per_day=1)]

    assert medication_end_date(episode_stub(), medications) == date(2026, 3, 7)


def test_medication_end_date_falls_back_to_a_single_unknown_day() -> None:
    """fallback 3단계 — episode 도 약도 모르면 UNKNOWN_DAYS(1일)로 본다."""
    assert UNKNOWN_DAYS == 1
    assert medication_end_date(episode_stub(), [medication_stub(times_per_day=1)]) == date(2026, 3, 1)


def test_medication_end_date_handles_an_empty_medication_list() -> None:
    """약 목록이 비어도 max() 가 빈 시퀀스로 터지지 않는다."""
    assert medication_end_date(episode_stub(), []) == date(2026, 3, 1)
    assert medication_end_date(episode_stub(days=4), []) == date(2026, 3, 4)


def test_medication_end_date_lets_scheduled_medications_win() -> None:
    """times_per_day 가 있는 약만 추린다. 스케줄 없는 긴 약이 기간을 늘리지 않는다."""
    medications = [medication_stub(days=3, times_per_day=1), medication_stub(days=30, times_per_day=None)]

    assert medication_end_date(episode_stub(), medications) == date(2026, 3, 3)


def test_medication_end_date_uses_unscheduled_medications_when_none_are_scheduled() -> None:
    """스케줄 있는 약이 하나도 없으면 전체 약 목록으로 돌아간다."""
    medications = [medication_stub(days=3, times_per_day=None), medication_stub(days=30, times_per_day=None)]

    assert medication_end_date(episode_stub(), medications) == date(2026, 3, 30)


@pytest.mark.parametrize(
    ("episode_days", "medication_days", "expected"),
    [
        (0, 7, date(2026, 3, 7)),  # episode 0 → 약의 7일이 쓰인다
        (10, 0, date(2026, 3, 10)),  # 약 0 → episode 의 10일이 쓰인다
    ],
)
def test_medication_end_date_treats_zero_days_as_unknown(
    episode_days: int, medication_days: int, expected: date
) -> None:
    """현재 동작 — `days or fallback` 이라 0 을 「모름」으로 본다.

    `or` 는 0 을 거짓으로 보므로 0일치가 fallback 으로 흐른다. 모델에
    MinValueValidator(1) 이 걸려 있어 DB 에는 0 이 들어갈 수 없고, 0 을 그대로
    쓰면 종료일이 시작일보다 앞서게 되므로(0 - 1 = -1일) 해롭지 않은 처리로 판단했다.
    """
    episode = episode_stub(days=episode_days)
    medications = [medication_stub(days=medication_days, times_per_day=1)]

    assert medication_end_date(episode, medications) == expected


# ──────────────── 조제일 검증기 2개 — _validate_confirmation_date 공용 ────────────────

CONFIRM_LIMIT_DAYS = 31


def guide_payload(dispensing_date: date) -> dict:
    return {
        "dispensingDate": dispensing_date,
        "medications": [{"tempId": "t1", "name": "타이레놀정"}],
    }


def document_payload(dispensed_date: date) -> dict:
    return {
        "dispensedDate": dispensed_date,
        "medications": [{"tempId": "t1", "name": "타이레놀정"}],
    }


def test_guide_confirm_accepts_today() -> None:
    today = seoul_now_date()

    assert MedicationGuideConfirmRequest(**guide_payload(today)).dispensing_date == today


def test_guide_confirm_accepts_the_upper_boundary_itself() -> None:
    """오늘 + 31일 당일은 통과한다 — `>` 비교라 같은 날은 걸리지 않는다."""
    limit = seoul_now_date() + timedelta(days=CONFIRM_LIMIT_DAYS)

    assert MedicationGuideConfirmRequest(**guide_payload(limit)).dispensing_date == limit


def test_guide_confirm_rejects_one_day_past_the_boundary() -> None:
    too_far = seoul_now_date() + timedelta(days=CONFIRM_LIMIT_DAYS + 1)

    with pytest.raises(ValidationError, match="조제일은 오늘로부터 31일 이후일 수 없습니다."):
        MedicationGuideConfirmRequest(**guide_payload(too_far))


def test_document_confirm_accepts_the_upper_boundary_itself() -> None:
    limit = seoul_now_date() + timedelta(days=CONFIRM_LIMIT_DAYS)

    assert DocumentOcrConfirmRequest(**document_payload(limit)).dispensed_date == limit


def test_document_confirm_rejects_one_day_past_the_boundary() -> None:
    too_far = seoul_now_date() + timedelta(days=CONFIRM_LIMIT_DAYS + 1)

    with pytest.raises(ValidationError, match="조제일은 오늘로부터 31일 이후일 수 없습니다."):
        DocumentOcrConfirmRequest(**document_payload(too_far))


@pytest.mark.parametrize("days_ago", [1, 365, 3650])
def test_confirm_requests_have_no_lower_bound(days_ago: int) -> None:
    """현재 동작 — 상한만 있고 하한이 없다. 10년 전 조제일도 통과한다.

    과거 처방전을 나중에 등록하는 경우를 막지 않으려는 것으로 읽힌다. 조제일이
    지나치게 오래된 경우를 걸러야 한다면 별도 판단이 필요하다.
    """
    old = seoul_now_date() - timedelta(days=days_ago)

    assert MedicationGuideConfirmRequest(**guide_payload(old)).dispensing_date == old
    assert DocumentOcrConfirmRequest(**document_payload(old)).dispensed_date == old


@pytest.mark.parametrize("offset_days", [0, CONFIRM_LIMIT_DAYS, CONFIRM_LIMIT_DAYS + 1, -1, -400])
def test_the_two_confirm_validators_agree(offset_days: int) -> None:
    """두 검증기는 이름만 다르고 같은 _validate_confirmation_date 를 부른다.

    한쪽만 고치면 이 테스트가 알려준다.
    """
    value = seoul_now_date() + timedelta(days=offset_days)

    def accepts(model, payload) -> bool:
        try:
            model(**payload)
        except ValidationError:
            return False
        return True

    assert accepts(MedicationGuideConfirmRequest, guide_payload(value)) == accepts(
        DocumentOcrConfirmRequest, document_payload(value)
    )


# ───────────────────────── SupplementDoseService.validate_date ─────────────────────────


def test_supplement_dose_date_accepts_today() -> None:
    SupplementDoseService.validate_date(seoul_now_date())


def test_supplement_dose_date_accepts_the_oldest_allowed_day() -> None:
    """365일 전 당일까지 허용된다. 오늘까지 세면 366일이라 오류 문구와 맞는다."""
    oldest = seoul_now_date() - timedelta(days=365)

    SupplementDoseService.validate_date(oldest)


def test_supplement_dose_window_really_spans_366_days() -> None:
    """오류 문구의 「366일」이 맞는지 직접 센다.

    코드는 timedelta(days=365) 를 쓰지만 양끝을 모두 포함하므로 날짜 개수는 366 이다.
    """
    today = seoul_now_date()
    oldest = today - timedelta(days=365)

    assert (today - oldest).days + 1 == 366


def test_supplement_dose_date_rejects_one_day_too_old() -> None:
    too_old = seoul_now_date() - timedelta(days=366)

    with pytest.raises(HTTPException) as exc_info:
        SupplementDoseService.validate_date(too_old)

    assert exc_info.value.status_code == 422
    assert "366일" in exc_info.value.detail


def test_supplement_dose_date_rejects_tomorrow() -> None:
    with pytest.raises(HTTPException) as exc_info:
        SupplementDoseService.validate_date(seoul_now_date() + timedelta(days=1))

    assert exc_info.value.status_code == 422


def test_supplement_dose_date_is_callable_without_an_instance() -> None:
    """staticmethod 라 서비스 인스턴스를 만들지 않아도 부를 수 있다."""
    assert isinstance(SupplementDoseService.__dict__["validate_date"], staticmethod)
    SupplementDoseService.validate_date(seoul_now_date())


# ────────────────────────────────── seoul_today ──────────────────────────────────


def test_seoul_today_returns_a_date() -> None:
    assert isinstance(seoul_today(), date)


def test_seoul_today_matches_the_korean_calendar_day() -> None:
    """반환값을 고정할 수 없으니 성질만 본다.

    한국 시간 0~9시에는 UTC 날짜가 하루 뒤처진다. 그 구간에서도 한국 날짜를 주는지
    확인하려면 UTC 날짜와 비교해서는 안 되고, 같은 +09:00 기준으로 비교해야 한다.
    """
    assert seoul_today() == datetime.now(config.TIMEZONE).date()


def test_seoul_today_is_never_behind_the_utc_date() -> None:
    """+09:00 이므로 UTC 날짜와 같거나 정확히 하루 앞선다. 뒤처지는 일은 없다.

    한국 시간 0~9시가 UTC 로는 전날 15~24시라, 그 구간에서만 하루 앞선다.
    """
    utc_date = datetime.now(UTC).date()
    korea_date = seoul_today()

    assert korea_date in {utc_date, utc_date + timedelta(days=1)}
