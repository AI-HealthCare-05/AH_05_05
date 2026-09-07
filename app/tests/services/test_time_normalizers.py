"""MySQL TIME 값을 time 으로 바꾸는 정규화 함수 3개.

asyncmy 가 TIME 컬럼을 timedelta 로 돌려주기 때문에 필요한 변환이다.

    app/services/settings.py                   normalize_medication_time
    app/services/follow_up_visit_alarms.py     normalize_time
    app/services/user_supplement_nutrients.py  normalize_mysql_time

**본문이 동일한 복사본이다.** 같은 부품이 세 곳에 따로 끼워져 있어, 한 곳을
고쳐도 나머지 둘은 그대로다. 그래서 세 개를 각각 돌리고 셋이 같은지도 본다.

합치는 것은 이 테스트의 범위가 아니다 — 어느 모듈에 둘지는 팀이 정할 일이다.
"""

from datetime import time, timedelta

import pytest

from app.services.follow_up_visit_alarms import normalize_time
from app.services.settings import normalize_medication_time
from app.services.user_supplement_nutrients import normalize_mysql_time

NORMALIZERS = [normalize_medication_time, normalize_time, normalize_mysql_time]
NORMALIZER_IDS = ["settings", "follow_up_visit_alarms", "user_supplement_nutrients"]


def _parametrize_normalizers():
    return pytest.mark.parametrize("normalize", NORMALIZERS, ids=NORMALIZER_IDS)


@_parametrize_normalizers()
def test_returns_a_time_value_untouched(normalize) -> None:
    """이미 time 이면 변환하지 않고 그대로 돌려준다."""
    value = time(8, 30, 15)

    assert normalize(value) is value


@_parametrize_normalizers()
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(0), time(0, 0, 0)),
        (timedelta(hours=8), time(8, 0, 0)),
        (timedelta(hours=13, minutes=30), time(13, 30, 0)),
        (timedelta(hours=1, minutes=2, seconds=3), time(1, 2, 3)),  # 초가 살아 있다
        (timedelta(seconds=59), time(0, 0, 59)),
        (timedelta(hours=23, minutes=59, seconds=59), time(23, 59, 59)),
    ],
)
def test_converts_timedelta_into_time(normalize, delta: timedelta, expected: time) -> None:
    assert normalize(delta) == expected


@_parametrize_normalizers()
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(hours=24), time(0, 0, 0)),  # 정확히 하루 → 0시로 되돌아온다
        (timedelta(hours=25), time(1, 0, 0)),
        (timedelta(days=1, hours=8, minutes=30), time(8, 30, 0)),
        (timedelta(days=3, seconds=1), time(0, 0, 1)),
    ],
)
def test_wraps_values_longer_than_a_day(normalize, delta: timedelta, expected: time) -> None:
    """`% (24*60*60)` 이 하루를 넘는 값을 하루 안으로 되감는다."""
    assert normalize(delta) == expected


@_parametrize_normalizers()
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(hours=-1), time(23, 0, 0)),  # 파이썬 % 는 양수 나머지를 준다
        (timedelta(seconds=-1), time(23, 59, 59)),
        (timedelta(hours=-25), time(23, 0, 0)),
        (timedelta(days=-1), time(0, 0, 0)),  # 정확히 -하루 → 0시
    ],
)
def test_wraps_negative_values_into_the_same_day(normalize, delta: timedelta, expected: time) -> None:
    """음수도 예외가 아니라 되감긴다.

    파이썬의 `%` 는 나누는 수가 양수면 나머지도 양수라, `-3600 % 86400` 은 82800 이다.
    C 계열 언어처럼 음수 나머지가 나왔다면 time() 생성에서 ValueError 가 났을 것이다.
    """
    assert normalize(delta) == expected


@_parametrize_normalizers()
@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=1, microseconds=500_000), time(0, 0, 1)),  # 1.5초 → 1초
        (timedelta(microseconds=999_999), time(0, 0, 0)),
        (timedelta(hours=8, microseconds=1), time(8, 0, 0)),
    ],
)
def test_truncates_microseconds(normalize, delta: timedelta, expected: time) -> None:
    """`int()` 는 반올림이 아니라 0 방향으로 버린다. 결과에 마이크로초가 남지 않는다."""
    result = normalize(delta)

    assert result == expected
    assert result.microsecond == 0


@pytest.mark.parametrize(
    "value",
    [
        time(9, 30),
        timedelta(0),
        timedelta(hours=8, minutes=30, seconds=15),
        timedelta(hours=25),
        timedelta(hours=-1),
        timedelta(seconds=1, microseconds=500_000),
        timedelta(days=2, hours=3),
    ],
)
def test_the_three_normalizers_agree(value: time | timedelta) -> None:
    """세 함수는 현재 같은 구현이다. 한쪽만 고치면 이 테스트가 알려준다.

    같은 부품이 세 곳에 복사돼 있어, 갈라지는 순간을 잡아 두는 것이 이 파일의 목적이다.
    """
    results = [normalize(value) for normalize in NORMALIZERS]

    assert len(set(results)) == 1, dict(zip(NORMALIZER_IDS, results, strict=True))
