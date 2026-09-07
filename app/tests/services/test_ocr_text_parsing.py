"""OCR 단위 교정·수량 파싱. 동작 변경은 없다. (박준영님 코드)

    app/services/medication_ocr_v3/pipeline/ocr_normalization.py
      :15  normalize_measurement_unit_ocr
      :25  normalize_strength_ocr
      :34  normalize_dose_unit_ocr
    app/services/medication_ocr_v3/pipeline/medication_rows.py
      :196  parse_times_per_day
      :203  parse_days
      :1640 dose_quantity_value_and_unit

⭐ **교정되는 경우와 교정되면 안 되는 경우를 함께 고정한다.**

이 함수들은 OCR 오독을 되돌리지만, 너무 넓게 고치면 약 이름을 망가뜨린다. 약
이름에 진짜로 `mI` 가 들어 있는데 `mL` 로 바꾸면 없는 약을 만들어낸다. 그래서
정규식마다 `(?<=\\d)`(앞에 숫자가 올 때만)·`(?![A-Za-z])`(뒤에 영문이 없을 때만)
같은 좁히는 조건이 달려 있다.

**이 테스트의 값은 「안 바뀜」을 박아두는 쪽에 있다.** 누가 나중에 정규식을 넓히면
`test_real_medication_names_are_never_rewritten` 이 먼저 깨진다.

기대값은 정규식을 베끼지 않고 입력·출력 쌍으로 적었다. 코드를 옮겨 적으면 같은
오류를 그대로 재현하기 때문이다.

⚠️ 복용량 칸에서 교정을 놓치는 두 경우를 찾아 이슈로 올렸다. **수정되면 걸려야
하므로 그 동작은 고정하지 않았고**, 정상 경로만 고정했다.

    #293  `1전씩3회,7일분` — 복용량·일정이 한 칸에 붙으면 정→전 교정이 안 된다
    #294  `5 mI`        — 숫자와 단위 사이 공백이 있으면 mg/mL 교정이 안 된다

DB·픽스처·이미지를 쓰지 않는다. 전부 문자열만 받는 순수 함수다.
"""

import pytest

from app.services.medication_ocr_v3.pipeline.medication_rows import (
    dose_quantity_value_and_unit,
    parse_days,
    parse_times_per_day,
)
from app.services.medication_ocr_v3.pipeline.ocr_normalization import (
    normalize_dose_unit_ocr,
    normalize_measurement_unit_ocr,
    normalize_strength_ocr,
)

# JSON 으로 안전하게 실어 보낼 수 있는 최대 정수. 파서가 이 값을 상한으로 쓴다.
MAX_JSON_SAFE = 9007199254740991


# ────────────────────── normalize_measurement_unit_ocr ──────────────────────
# 나머지 두 함수가 이 함수를 거쳐 가므로 먼저 고정한다.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("500m9", "500mg"),
        ("500M9", "500mg"),
        ("500MG", "500mg"),
        ("500mG", "500mg"),
        ("500mg", "500mg"),
    ],
)
def test_a_milligram_misread_after_a_number_is_corrected(raw: str, expected: str) -> None:
    """`g` 를 `9` 로 읽은 형태와 대문자 표기를 소문자 `mg` 으로 모은다."""
    assert normalize_measurement_unit_ocr(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10mI", "10mL"),
        ("10ml", "10mL"),
        ("10mL", "10mL"),
        ("10Ml", "10mL"),
        ("10mℓ", "10mL"),
        ("10m1", "10mL"),
    ],
)
def test_a_milliliter_misread_after_a_number_is_corrected(raw: str, expected: str) -> None:
    """대문자 `I`·숫자 `1`·기호 `ℓ` 을 모두 `L` 로 본다.

    `10m1` 이 `10mL` 이 되는 것에 주의한다 — 소문자 `l` 을 숫자 `1` 로 읽는 오독을
    되돌리려는 것이고, 그래서 숫자도 후보에 들어 있다.
    """
    assert normalize_measurement_unit_ocr(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("500밀리그람", "500밀리그램"),
        ("500밀리그랑", "500밀리그램"),
        ("500미리그램", "500밀리그램"),
        ("500밀리그램", "500밀리그램"),
    ],
)
def test_korean_milligram_misspellings_are_corrected(raw: str, expected: str) -> None:
    """한글 오기 3종을 「밀리그램」으로 모은다. 여기서는 `mg` 으로 바꾸지 않는다."""
    assert normalize_measurement_unit_ocr(raw) == expected


def test_korean_milliliter_becomes_the_latin_unit() -> None:
    """「밀리리터」만 곧바로 `mL` 이 된다 — 밀리그램 쪽과 처리가 다르다."""
    assert normalize_measurement_unit_ocr("10밀리리터") == "10mL"


@pytest.mark.parametrize(
    "raw",
    ["m9", "mI", "mg", "밀리그람", "밀리리터", "미리그램", "mL"],
)
def test_a_unit_with_no_number_in_front_is_left_alone(raw: str) -> None:
    """⭐ `(?<=\\d)` 의 목적 — 숫자가 앞에 없으면 단위로 보지 않는다.

    단위처럼 생긴 조각이 약 이름 안에 들어 있을 때 건드리지 않기 위한 조건이다.
    """
    assert normalize_measurement_unit_ocr(raw) == raw


@pytest.mark.parametrize(
    "raw",
    ["500m9X2", "5mIx", "5m9Liquid", "500mIx"],
)
def test_a_unit_followed_by_a_letter_is_left_alone(raw: str) -> None:
    """⭐ `(?![A-Za-z])` 의 목적 — 뒤에 영문이 이어지면 단위가 아니라고 본다.

    오독인 것이 사람 눈에 뻔한 경우(`500m9X2`)도 고치지 않는다. 덜 고치는 쪽으로
    기운 판단이고, 약 이름을 지키는 대가로 이런 경우를 놓친다.
    """
    assert normalize_measurement_unit_ocr(raw) == raw


@pytest.mark.parametrize(
    "name",
    [
        "아목시실린250mg",
        "크레스토10mg",
        "가스모틴5mg",
        "뮤코미스트400mg",
        "아모잘탄플러스5/2.5mg",
        "타이레놀8시간이알서방정",
        "비타민B12",
        "5-FU",
        "MgO",
        "MgO500",
        "코푸시럽S",
        "메가트루",
        "박스터5%포도당",
    ],
)
def test_real_medication_names_are_never_rewritten(name: str) -> None:
    """⭐ 이 테스트가 이 파일의 핵심이다 — 정규식을 넓히면 여기가 먼저 깨진다.

    실제 약 이름·표기를 넣어 **한 글자도 바뀌지 않는지** 확인한다. `MgO` 는 앞에
    숫자가 없어 안전하고, `MgO500` 은 `Mg` 앞에 숫자가 없어 안전하다.
    """
    assert normalize_measurement_unit_ocr(name) == name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("５００ｍ９", "500mg"),
        ("５mI", "5mL"),
        ("500㎎", "500mg"),
        ("500㎖", "500mL"),
        ("1０mＩ", "10mL"),
    ],
)
def test_full_width_and_composed_unit_characters_are_folded_first(raw: str, expected: str) -> None:
    """NFKC 가 먼저 돌아 전각·합자 문자를 반각으로 편다.

    이 단계가 없으면 전각 숫자가 `(?<=\\d)` 에 걸리지 않아 뒤 교정이 전부 불발한다.
    """
    assert normalize_measurement_unit_ocr(raw) == expected


def test_whitespace_is_preserved_here_unlike_the_other_two() -> None:
    """이 함수는 공백을 지우지 않는다 — 그래서 `500 m9` 이 교정되지 않는다.

    공백이 숫자와 단위를 갈라놓아 `(?<=\\d)` 에 걸리지 않는다. 공백 제거는 이 함수를
    감싸는 함량·복용량 쪽 책임이고, 두 곳이 그 순서를 다르게 잡고 있다(#294).
    """
    assert normalize_measurement_unit_ocr("500 m9") == "500 m9"
    assert normalize_measurement_unit_ocr("5 mI") == "5 mI"


# ───────────────────────────── normalize_strength_ocr ─────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("500 m9", "500mg"),
        ("5 0 0 m I", "500mL"),
        ("  500mg  ", "500mg"),
        ("500\tm9", "500mg"),
        ("500\nmI", "500mL"),
    ],
)
def test_a_strength_field_drops_every_space_before_correcting(raw: str, expected: str) -> None:
    """공백을 먼저 전부 없애서, 띄어 읽힌 단위도 교정 대상이 된다."""
    assert normalize_strength_ocr(raw) == expected


@pytest.mark.parametrize("raw", ["500밀리그램", "500밀리그람", "500밀리그랑", "500미리그램"])
def test_a_strength_field_converts_korean_milligram_to_the_latin_unit(raw: str) -> None:
    """⭐ 두 함수가 갈리는 지점 — 이쪽은 `mg` 까지 가고 저쪽은 「밀리그램」에서 멈춘다."""
    assert normalize_strength_ocr(raw) == "500mg"
    assert normalize_measurement_unit_ocr(raw) == "500밀리그램"


def test_korean_milligram_is_replaced_even_without_a_number_in_front() -> None:
    """현재 동작 — 「밀리그램」→`mg` 치환에는 숫자 조건이 없다.

    앞의 교정들은 모두 `(?<=\\d)` 로 좁혀 두었는데, 이 마지막 치환만 조건 없는
    문자열 바꾸기(`str.replace`)다. 그래서 숫자가 없어도 바뀐다.

    함량 칸만 통과하는 함수라 칸 전체가 함량이고, 지금은 해롭지 않다고 본다.
    오기(「밀리그람」)는 숫자가 없으면 그대로 남아, 두 단계의 조건이 어긋난다.
    """
    assert normalize_strength_ocr("밀리그램") == "mg"
    assert normalize_strength_ocr("밀리그람") == "밀리그람"


@pytest.mark.parametrize("name", ["아목시실린250mg", "크레스토10mg", "5-FU", "MgO"])
def test_a_strength_field_does_not_rewrite_medication_names(name: str) -> None:
    assert normalize_strength_ocr(name) == name


# ──────────────────────────── normalize_dose_unit_ocr ────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1전", "1정"),
        ("1점", "1정"),
        ("10전", "10정"),
        ("1전씩", "1정씩"),
        ("2점씩", "2정씩"),
        ("1 전", "1정"),
    ],
)
def test_a_tablet_unit_misread_is_corrected_at_the_end_of_the_cell(raw: str, expected: str) -> None:
    """`전`·`점` 을 `정` 으로 되돌린다. 공백을 먼저 지우므로 `1 전` 도 걸린다."""
    assert normalize_dose_unit_ocr(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [("1캡술", "1캡슐"), ("1캡술씩", "1캡슐씩")])
def test_a_capsule_unit_misread_is_corrected(raw: str, expected: str) -> None:
    assert normalize_dose_unit_ocr(raw) == expected


@pytest.mark.parametrize("raw", ["1전정", "1전씩2", "1전씩3회", "전", "전씩"])
def test_a_tablet_misread_that_is_not_at_the_end_is_left_alone(raw: str) -> None:
    """⭐ `(?=(?:씩)?$)` 의 목적 — 끝 또는 `씩` 바로 앞에서만 고친다.

    `전` 이 문장 가운데 있으면 단위가 아닐 가능성이 있어 건드리지 않는다. `전` 만
    있는 경우도 앞에 숫자가 없어 대상이 아니다.

    ⚠️ `1전씩3회` 처럼 복용량과 일정이 한 칸에 붙은 형태는 이 조건 때문에 교정을
    놓친다. #293 으로 올렸다.
    """
    assert normalize_dose_unit_ocr(raw) == raw


def test_a_dose_cell_also_gets_the_measurement_corrections() -> None:
    """같은 정수장을 거치므로 단위 오독 교정이 함께 적용된다.

    ⚠️ 숫자와 단위 사이에 공백이 있으면(`5 mI`) 교정을 놓친다 — 이 함수는 공백을
    교정 **뒤에** 지우기 때문이다. 함량 쪽은 순서가 반대여서 잡는다. #294 로 올렸고
    수정되면 걸려야 하므로 여기서는 공백 없는 경로만 고정한다.
    """
    assert normalize_dose_unit_ocr("5mI") == "5mL"
    assert normalize_dose_unit_ocr("500m9") == "500mg"
    assert normalize_dose_unit_ocr("10밀리리터") == "10mL"


def test_the_dose_cell_and_the_strength_field_agree_when_there_is_no_whitespace() -> None:
    """공백이 없으면 두 정규화가 같은 결과를 낸다.

    갈리는 것은 공백이 낀 경우뿐이라는 사실을 한쪽만 고정해 둔다. 반대편(공백이
    있을 때의 복용량 결과)은 #294 라서 고정하지 않는다.
    """
    for raw in ["500m9", "5mI", "10밀리리터"]:
        assert normalize_dose_unit_ocr(raw) == normalize_strength_ocr(raw)


def test_a_zero_quantity_is_still_unit_corrected() -> None:
    """현재 동작 — `0` 도 숫자라 교정된다. 0 인지 판단은 호출부 몫이다."""
    assert normalize_dose_unit_ocr("0전") == "0정"


# ──────────────────────── parse_times_per_day / parse_days ────────────────────


@pytest.mark.parametrize(("raw", "expected"), [("3", 3), ("3회", 3), ("12", 12), ("1", 1)])
def test_times_per_day_accepts_a_bare_number_or_a_counter_suffix(raw: str, expected: int) -> None:
    assert parse_times_per_day(raw) == expected


@pytest.mark.parametrize("raw", ["3,", "3회,", "3회，", "3，"])
def test_times_per_day_tolerates_a_trailing_comma(raw: str) -> None:
    """반각·전각 쉼표를 모두 흘려보낸다. 표에서 회수 뒤에 구분자가 붙어 나온다."""
    assert parse_times_per_day(raw) == 3


@pytest.mark.parametrize(("raw", "expected"), [("7", 7), ("7일", 7), ("7일분", 7), ("30일분", 30)])
def test_days_accepts_a_bare_number_or_either_day_suffix(raw: str, expected: int) -> None:
    assert parse_days(raw) == expected


@pytest.mark.parametrize("raw", ["7,", "7일,", "7일분,", "7，"])
def test_days_does_not_tolerate_a_trailing_comma(raw: str) -> None:
    """⭐ 회수와 달리 일수는 쉼표를 받지 않는다 — 비대칭이지만 근거가 있다.

    붙어 나오는 표 형태가 `3회,7일분` 이라, 쉼표는 항상 회수 **뒤**에 오고 일수
    뒤에는 오지 않는다. 한 칸을 가를 때 구분자를 회수 쪽이 떠안는 구조다.
    `_COMBINED_SCHEDULE_SUFFIX_PATTERN` 이 그 배치를 그대로 담고 있어, 이 비대칭은
    의도로 읽힌다.
    """
    assert parse_days(raw) is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
@pytest.mark.parametrize("raw", ["0", "00", "0회", "0일"])
def test_zero_is_not_a_valid_count(parse, raw: str) -> None:
    """`[1-9]` 로 시작을 강제해 0 을 막는다. 하루 0회·0일은 처방이 아니다."""
    assert parse(raw) is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
@pytest.mark.parametrize("raw", ["03", "007", "0012"])
def test_a_leading_zero_is_rejected(parse, raw: str) -> None:
    """⭐ 앞자리 0 이 아예 못 들어온다 — 상한 검사의 자릿수 비교가 안전한 이유.

    상한 판정이 문자열 사전순 비교(`digits > _MAX_JSON_SAFE_DIGITS`)를 쓰는데,
    앞자리 0 이 있으면 자릿수가 부풀어 잘못 걸릴 수 있다. 그런데 패턴이 `[1-9]`
    로 시작을 강제하므로 **그 경로에 도달할 수 없다.** 여기서 그 사실을 고정한다.
    """
    assert parse(raw) is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
@pytest.mark.parametrize("raw", ["-1", "1.5", "3.0", "+3", "", " ", "  ", "일", "회"])
def test_non_integer_shapes_are_rejected(parse, raw: str) -> None:
    """음수·소수·부호·빈 칸은 패턴에 없다."""
    assert parse(raw) is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
@pytest.mark.parametrize("raw", ["하루3회", "3회3", "총7일분", "7일분씩", "약 3회"])
def test_surrounding_text_makes_the_whole_cell_unparseable(parse, raw: str) -> None:
    """⭐ `fullmatch` 다 — 부분 일치가 아니라 칸 전체가 패턴이어야 한다.

    설명이 섞인 칸에서 숫자만 주워오지 않는다. 근거 없는 값을 만들지 않으려는
    선택이다.
    """
    assert parse(raw) is None


def test_the_two_parsers_do_not_accept_each_others_suffix() -> None:
    """회수 칸과 일수 칸을 서로 헷갈리지 않는다."""
    assert parse_times_per_day("3일") is None
    assert parse_times_per_day("3일분") is None
    assert parse_days("7회") is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
def test_the_json_safe_upper_bound_is_inclusive(parse) -> None:
    """상한값 자체는 통과하고, 하나 넘으면 떨어진다.

    JSON 으로 나갈 때 정밀도가 깨지지 않는 최대 정수(2**53 - 1)가 경계다.
    """
    assert parse(str(MAX_JSON_SAFE)) == MAX_JSON_SAFE
    assert parse(str(MAX_JSON_SAFE - 1)) == MAX_JSON_SAFE - 1
    assert parse(str(MAX_JSON_SAFE + 1)) is None


@pytest.mark.parametrize("parse", [parse_times_per_day, parse_days], ids=["times", "days"])
@pytest.mark.parametrize(
    ("raw", "accepted"),
    [
        ("1000000000000000", True),  # 16자리, 상한보다 작음
        ("9999999999999999", False),  # 16자리, 상한보다 큼
        ("90071992547409910", False),  # 17자리
        ("10000000000000000000", False),  # 20자리
    ],
)
def test_the_upper_bound_compares_digit_count_then_the_digits(parse, raw: str, accepted: bool) -> None:
    """자릿수가 같으면 사전순 비교가 수치 비교와 일치한다.

    앞자리 0 이 들어올 수 없으므로(위 테스트) 같은 자릿수의 두 수는 사전순으로도
    크기 순서가 같다. 자릿수가 다르면 길이만 보고 판정한다.
    """
    assert (parse(raw) is not None) is accepted


# ───────────────────── dose_quantity_value_and_unit ──────────────────────────
# ⚠️ 문자열 튜플을 돌려준다. 값도 숫자가 아니라 문자열이다.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1정", ("1", "정")),
        ("2캡슐", ("2", "캡슐")),
        ("1포", ("1", "포")),
        ("10정", ("10", "정")),
    ],
)
def test_an_integer_quantity_and_its_dosage_form(raw: str, expected: tuple[str, str]) -> None:
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.5정", ("0.5", "정")),
        ("1.5정", ("1.5", "정")),
        ("0.25", ("0.25", None)),
        ("0.5포", ("0.5", "포")),
    ],
)
def test_a_decimal_quantity_keeps_its_written_form(raw: str, expected: tuple[str, str | None]) -> None:
    """`0.5` 를 `0.5` 문자열로 그대로 돌려준다 — 소수로 바꾸지 않는다."""
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1/2정", ("1/2", "정")),
        ("1/4정", ("1/4", "정")),
        ("10/3포", ("10/3", "포")),
    ],
)
def test_a_fraction_quantity_is_kept_as_written(raw: str, expected: tuple[str, str]) -> None:
    """반 알 처방을 `1/2` 문자열로 남긴다. 나눗셈을 하지 않는다."""
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize("raw", ["1/0정", "0/2정", "1/정"])
def test_a_fraction_with_a_zero_or_missing_denominator_is_not_a_quantity(raw: str) -> None:
    """분모도 `[1-9]` 로 시작해야 한다 — 0 으로 나누는 값이 들어오지 않는다."""
    _, unit = dose_quantity_value_and_unit(raw)

    assert unit is None


@pytest.mark.parametrize("raw", ["5mL", "5ml", "5mℓ", "5MI", "5Ml", "5m1"])
def test_every_milliliter_spelling_collapses_to_one_form(raw: str) -> None:
    """⭐ `mL` 표기를 하나로 모은다.

    `ℓ` 은 NFKC 가 `l` 로 펴고, 그 다음 단위 교정이 `mL` 로 만든다. 그래서 이
    함수가 `mℓ` 을 그대로 돌려주는 경우는 없다 — 호출부(`_canonical_dose_value`)가
    `{"포", "mL", "mℓ"}` 를 보는데 `mℓ` 쪽은 닿지 않는 분기다.
    """
    assert dose_quantity_value_and_unit(raw) == ("5", "mL")


@pytest.mark.parametrize(("raw", "expected"), [("1", ("1", None)), ("2", ("2", None)), ("1씩", ("1", None))])
def test_a_quantity_without_a_dosage_form_returns_no_unit(raw: str, expected: tuple[str, None]) -> None:
    """단위 없이 숫자만 있는 칸도 값으로 인정한다."""
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("1정씩", ("1", "정")), ("2캡슐씩", ("2", "캡슐")), ("5mL씩", ("5", "mL"))]
)
def test_a_trailing_per_dose_marker_is_dropped(raw: str, expected: tuple[str, str]) -> None:
    """`씩` 은 값이 아니라 표식이라 결과에 남지 않는다."""
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1정씩3회,7일분", ("1", "정")),
        ("1정씩3회，7일분", ("1", "정")),
        ("1정씩3회7일분", ("1", "정")),
        ("2정씩3회,14일분", ("2", "정")),
        ("5mL씩2회,3일분", ("5", "mL")),
    ],
)
def test_a_cell_holding_both_the_quantity_and_the_schedule_is_split(raw: str, expected: tuple[str, str]) -> None:
    """⭐ 복용량과 일정이 한 칸에 붙어 나오면 `씩` 앞만 떼어 쓴다.

    일정 부분이 `N회[,]N일분` 꼴로 **정확히** 맞을 때만 갈라낸다. 아무 글자나
    붙어 있으면 갈라내지 않는다(아래 테스트).
    """
    assert dose_quantity_value_and_unit(raw) == expected


@pytest.mark.parametrize("raw", ["1정씩3회", "1정씩7일분", "1정씩3회,7일", "1정씩아침저녁"])
def test_a_schedule_suffix_that_does_not_match_exactly_blocks_the_split(raw: str) -> None:
    """일정 꼴이 어긋나면 갈라내지 않고 칸 전체를 파싱 실패로 둔다.

    `회`·`일분` 이 둘 다 있어야 한다. 하나만 있으면 표를 잘못 읽었을 가능성이 커서
    값을 만들어내지 않는 쪽을 택한다.
    """
    value, unit = dose_quantity_value_and_unit(raw)

    assert unit is None
    assert value == raw


@pytest.mark.parametrize(
    "raw",
    ["복용법참조", "복용법 참조", "필요시", "-", "0정", "0.0정", "취침전", "1일3회"],
)
def test_an_unparseable_cell_returns_the_normalized_text_and_no_unit(raw: str) -> None:
    """현재 동작 — 못 알아들으면 예외가 아니라 `(정규화된 원문, None)` 이다.

    OCR 이 읽은 것을 없애지 않고 그대로 넘기는 계약이다. 다만 **호출부가 값과
    원문을 구분할 수 없다.** `_canonical_dose_value`(medication_rows.py:1635)는
    단위가 없으면 값을 그대로 쓰고, `_dose_field` 는 `0` 꼴만 따로 걸러
    `INVALID_FIELD_VALUE` 를 붙인다. 즉 `"복용법참조"` 는 이슈 코드 없이 복용량
    값으로 실려 나간다.

    지금 무해하다고 본다 — 값을 지어내는 것보다 읽은 그대로 두는 것이 이 모듈의
    방침이고, 셀 신뢰도는 별도 필드로 함께 전달된다. 파싱 실패에 이슈 코드를 붙일
    것인지는 판단이 필요해 §2 로 분류했다.
    """
    normalized = "".join(raw.split())

    assert dose_quantity_value_and_unit(raw) == (normalized, None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1전", ("1", "정")),
        ("1점", ("1", "정")),
        ("1캡술", ("1", "캡슐")),
        ("1 전", ("1", "정")),
        ("5mI", ("5", "mL")),
        ("5m1", ("5", "mL")),
    ],
)
def test_a_misread_dose_cell_is_corrected_before_parsing(raw: str, expected: tuple[str, str]) -> None:
    """⭐ 이 함수는 `normalize_dose_unit_ocr` 을 먼저 거친다.

    오독된 단위가 교정된 뒤 파싱되므로, `1전` 이 값 `1` + 단위 `정` 으로 갈린다.
    교정이 없으면 파싱 실패로 떨어졌을 입력이다.

    `1 전` 은 공백이 있어도 걸린다 — `전→정` 치환이 공백 제거 **뒤에** 있기 때문이다.
    반면 `5 mI` 는 단위 교정이 공백 제거 앞에 있어 놓친다(#294).
    """
    assert dose_quantity_value_and_unit(raw) == expected


def test_a_zero_quantity_is_not_handled_by_this_function() -> None:
    """현재 동작 — `_ZERO_DOSE_QUANTITY_PATTERN` 이 따로 있지만 여기서는 안 쓴다.

    `0정` 은 그냥 파싱 실패로 떨어지고, 0 판정은 호출부(`_dose_field`)가 별도
    패턴으로 한다. 이 함수만 보면 0 과 알 수 없는 글자가 구분되지 않는다.
    """
    assert dose_quantity_value_and_unit("0정") == ("0정", None)
    assert dose_quantity_value_and_unit("0") == ("0", None)


@pytest.mark.parametrize("raw", ["  1 정  ", "1\t정", "1\n정"])
def test_whitespace_around_and_inside_the_cell_is_removed(raw: str) -> None:
    assert dose_quantity_value_and_unit(raw) == ("1", "정")


def test_the_returned_value_is_always_a_string() -> None:
    """숫자로 바꾸지 않는다 — 분수·소수를 그대로 실어 보내기 위한 선택이다."""
    for raw in ["1정", "0.5정", "1/2정", "복용법참조"]:
        value, _ = dose_quantity_value_and_unit(raw)

        assert isinstance(value, str)
