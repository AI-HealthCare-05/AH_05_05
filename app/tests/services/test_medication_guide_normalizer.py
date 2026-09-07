"""처방전 정규화 6개 테스트 — 박준영님 코드 대상. 동작 변경은 없다.

    app/services/medication_guide_normalizer.py
      normalize_text · normalize_date · split_name_strength
      split_category_efficacy · strip_storage_labels · parse_dose_line

OCR 이 읽은 처방전 글자를 창구 뒤로 넘기기 전에 다듬는 단계다. 틀려도 예외가 나지
않고 조금 다른 문자열이 조용히 통과한다.

`normalize_text` 는 나머지 다섯이 전부 거쳐 가는 입구다 — 정수장 같은 구조라
여기가 틀리면 아래가 전부 조용히 틀린다. 그래서 먼저 고정한다.

DB·픽스처를 쓰지 않는다.

`normalize_date` 의 한 자리 월·일 처리는 결함으로 판단해 여기서 고정하지 않았다.
정규식이 `\\d{1,2}` 로 잡은 값을 date.fromisoformat 이 거부해 조용히 None 이 된다.
→ #274 로 분리했다.
"""

from datetime import date

import pytest

from app.services.medication_guide_normalizer import (
    normalize_date,
    normalize_text,
    parse_dose_line,
    split_category_efficacy,
    split_name_strength,
    strip_storage_labels,
)

# ───────────────────────────────── normalize_text ─────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ＡＢＣ", "ABC"),  # 전각 영문
        ("１２３", "123"),  # 전각 숫자
        ("㎎", "mg"),  # 단위 합자
        ("５００㎎", "500mg"),
        ("（주）", "(주)"),  # 전각 괄호
    ],
)
def test_normalize_text_applies_nfkc(raw: str, expected: str) -> None:
    """전각·합자를 반각으로 편다. OCR 이 전각으로 읽어오는 경우가 있다."""
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  타이레놀정  ", "타이레놀정"),  # 앞뒤
        ("타이레놀정  500mg", "타이레놀정 500mg"),  # 연속 공백
        ("줄\n바꿈", "줄 바꿈"),  # 개행도 공백이다
        ("탭\t구분", "탭 구분"),
        ("여러\n\n  줄\t\t섞임", "여러 줄 섞임"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_text_collapses_whitespace(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("손상된위점막", "손상된 위점막"),
        ("뜨거운음료", "뜨거운 음료"),
        ("상 담하세요", "상담하세요"),
    ],
)
def test_normalize_text_applies_the_confirmed_corrections(raw: str, expected: str) -> None:
    """확정된 오탈자 교정 3건. OCR 이 반복해서 틀리는 것만 표에 넣는다."""
    assert normalize_text(raw) == expected


def test_normalize_text_collapses_whitespace_before_correcting() -> None:
    """공백 정리가 교정보다 먼저 돈다.

    그래서 「상  담하세요」(공백 2개)도 「상 담하세요」로 줄어든 뒤 교정표에 걸린다.
    순서가 반대라면 공백이 여러 개인 입력은 교정되지 않았을 것이다.
    """
    assert normalize_text("상  담하세요") == "상담하세요"
    assert normalize_text("상\n담하세요") == "상담하세요"


def test_normalize_text_applies_corrections_inside_a_longer_sentence() -> None:
    assert normalize_text("복용 후 손상된위점막 이 회복됩니다") == "복용 후 손상된 위점막 이 회복됩니다"


def test_normalize_text_leaves_ordinary_text_untouched() -> None:
    assert normalize_text("타이레놀정 500mg") == "타이레놀정 500mg"


def test_normalize_text_is_idempotent() -> None:
    once = normalize_text("  ＡＢＣ  손상된위점막  ")

    assert normalize_text(once) == once


# ───────────────────────────────── normalize_date ─────────────────────────────────


def test_normalize_date_parses_a_zero_padded_iso_date() -> None:
    assert normalize_date("2026-09-07") == date(2026, 9, 7)


def test_normalize_date_finds_the_date_inside_a_sentence() -> None:
    """정규식 search 라 앞뒤에 글자가 붙어 있어도 찾아낸다."""
    assert normalize_date("다음 방문일 2026-09-07 입니다") == date(2026, 9, 7)


def test_normalize_date_takes_the_first_date_when_several_appear() -> None:
    assert normalize_date("2026-09-07 및 2027-01-01") == date(2026, 9, 7)


def test_normalize_date_applies_nfkc_before_matching() -> None:
    """전각 숫자로 읽힌 날짜도 파싱된다."""
    assert normalize_date("２０２６-０９-０７") == date(2026, 9, 7)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "날짜 없음",
        "2026/09/07",  # 구분자가 다르면 정규식이 잡지 못한다
        "20260907",
        "26-09-07",  # 연도 4자리를 요구한다
    ],
)
def test_normalize_date_returns_none_when_nothing_matches(raw: str) -> None:
    assert normalize_date(raw) is None


@pytest.mark.parametrize("raw", ["2026-13-01", "2026-02-30", "2026-00-10"])
def test_normalize_date_returns_none_for_a_date_that_does_not_exist(raw: str) -> None:
    """정규식은 통과하지만 달력에 없는 날짜라 파싱에서 걸러진다."""
    assert normalize_date(raw) is None


# ─────────────────────────────── split_name_strength ───────────────────────────────


@pytest.mark.parametrize(
    ("raw", "name", "strength"),
    [
        ("타이레놀정 500mg", "타이레놀정", "500mg"),
        ("타이레놀정500mg", "타이레놀정", "500mg"),
        ("아스피린 100 mg", "아스피린", "100mg"),  # 함량 안의 공백은 제거된다
        ("시럽 5.5mL", "시럽", "5.5mL"),
        ("연고 0.1%", "연고", "0.1%"),
        ("주사액 10mcg", "주사액", "10mcg"),
        ("가루약 1g", "가루약", "1g"),
        ("대문자단위 500MG", "대문자단위", "500MG"),  # 대소문자를 가리지 않는다
    ],
)
def test_split_name_strength_separates_a_trailing_strength(raw: str, name: str, strength: str) -> None:
    assert split_name_strength(raw) == (name, strength)


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("타이레놀정", "타이레놀정"),
        ("종합비타민", "종합비타민"),
        ("500mg 타이레놀정", "500mg 타이레놀정"),  # 끝이 아니면 함량으로 보지 않는다
        ("", ""),
    ],
)
def test_split_name_strength_returns_none_when_there_is_no_trailing_strength(raw: str, name: str) -> None:
    assert split_name_strength(raw) == (name, None)


def test_split_name_strength_keeps_the_whole_text_when_the_name_would_be_empty() -> None:
    """함량만 있으면 쪼개지 않고 원문을 이름으로 둔다. 이름 없는 약을 만들지 않는다."""
    assert split_name_strength("500mg") == ("500mg", None)
    assert split_name_strength("  500mg  ") == ("500mg", None)


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("타이레놀정, 500mg", "타이레놀정"),
        ("타이레놀정 - 500mg", "타이레놀정"),
        ("타이레놀정/500mg", "타이레놀정"),
    ],
)
def test_split_name_strength_trims_separators_left_behind(raw: str, name: str) -> None:
    """이름 끝에 남는 쉼표·하이픈·슬래시를 떼낸다."""
    assert split_name_strength(raw) == (name, "500mg")


def test_split_name_strength_normalizes_before_splitting() -> None:
    assert split_name_strength("  타이레놀정   ５００㎎  ") == ("타이레놀정", "500mg")


# ────────────────────────────── split_category_efficacy ──────────────────────────────


def test_split_category_efficacy_separates_a_bracketed_category() -> None:
    assert split_category_efficacy("[해열진통제] 두통, 발열") == ("해열진통제", "두통, 발열")


def test_split_category_efficacy_returns_only_efficacy_without_brackets() -> None:
    assert split_category_efficacy("두통, 발열") == (None, "두통, 발열")


def test_split_category_efficacy_returns_a_pair_of_none_for_blank_input() -> None:
    assert split_category_efficacy("") == (None, None)
    assert split_category_efficacy("   ") == (None, None)


def test_split_category_efficacy_returns_none_efficacy_when_only_a_category_is_given() -> None:
    assert split_category_efficacy("[해열진통제]") == ("해열진통제", None)


def test_split_category_efficacy_treats_empty_brackets_as_plain_text() -> None:
    """대괄호 안이 비면 분류로 보지 않는다 — 정규식이 1자 이상을 요구한다."""
    assert split_category_efficacy("[] 두통") == (None, "[] 두통")


def test_split_category_efficacy_only_matches_brackets_at_the_start() -> None:
    assert split_category_efficacy("두통 [해열진통제]") == (None, "두통 [해열진통제]")


def test_split_category_efficacy_normalizes_both_halves() -> None:
    category, efficacy = split_category_efficacy("[  해열   진통제 ]   두통   발열  ")

    assert category == "해열 진통제"
    assert efficacy == "두통 발열"


# ─────────────────────────────── strip_storage_labels ───────────────────────────────


@pytest.mark.parametrize("label", ["실온보관", "기밀용기", "냉장보관", "차광보관"])
def test_strip_storage_labels_removes_each_known_label(label: str) -> None:
    assert strip_storage_labels(f"밀폐용기에 담아 {label}") == "밀폐용기에 담아"
    assert strip_storage_labels(label) == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("밀폐용기 실온보관, 기밀용기", "밀폐용기"),
        ("실온보관/차광보관·냉장보관", ""),
        ("보관 실온보관 기밀용기 냉장보관", "보관"),
        ("실온보관 실온보관 실온보관", ""),
    ],
)
def test_strip_storage_labels_removes_several_labels_in_a_row(raw: str, expected: str) -> None:
    assert strip_storage_labels(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["보관방법", "직사광선을 피하세요", "", "실온보관 후 복용하세요"],
)
def test_strip_storage_labels_leaves_text_without_a_trailing_label(raw: str) -> None:
    """라벨이 끝에 없으면 건드리지 않는다 — 문장 가운데 라벨은 내용의 일부다."""
    assert strip_storage_labels(raw) == normalize_text(raw)


def test_strip_storage_labels_terminates_on_repeated_labels() -> None:
    """while True 루프가 끝나는지 본다.

    한 번 돌 때마다 문자열이 짧아지거나 그대로이고, 그대로면 즉시 반환하므로 멈춘다.
    라벨을 많이 붙여도 무한 루프가 되지 않는다.
    """
    assert strip_storage_labels("약 " + "실온보관, " * 50) == "약"
    assert strip_storage_labels("실온보관" * 50) == ""


# ───────────────────────────────── parse_dose_line ─────────────────────────────────


def test_parse_dose_line_reads_quantity_times_and_days() -> None:
    result = parse_dose_line("1회 1정씩 1일 3회 7일분")

    assert result.dose_quantity == "1정"
    assert result.times_per_day == 3
    assert result.days == 7


def test_parse_dose_line_uses_the_fallback_when_the_main_pattern_misses() -> None:
    """「씩」이 없으면 보조 정규식이 「1회 … 1일」 사이를 읽는다."""
    result = parse_dose_line("1회 1정 1일 3회")

    assert result.dose_quantity == "1정"
    assert result.times_per_day == 3


def test_parse_dose_line_reads_a_quantity_without_the_leading_per_dose_marker() -> None:
    """「1회」 접두어가 없어도 「…씩」 만으로 1회 투약량을 읽는다."""
    result = parse_dose_line("1정씩 1일 2회")

    assert result.dose_quantity == "1정"
    assert result.times_per_day == 2


def test_parse_dose_line_reads_a_quantity_that_ends_the_line() -> None:
    result = parse_dose_line("1정씩")

    assert result.dose_quantity == "1정"
    assert result.times_per_day is None
    assert result.days is None


@pytest.mark.parametrize(
    ("raw", "days"),
    [("3일분", 3), ("3일간", 3), ("14일분 복용", 14)],
)
def test_parse_dose_line_reads_the_day_count(raw: str, days: int) -> None:
    assert parse_dose_line(raw).days == days


def test_parse_dose_line_returns_all_none_for_text_it_cannot_read() -> None:
    result = parse_dose_line("")

    assert result.dose_quantity is None
    assert result.times_per_day is None
    assert result.days is None


def test_parse_dose_line_fills_only_the_parts_it_finds() -> None:
    """세 조각이 독립적이다. 일부만 있어도 나머지를 억지로 채우지 않는다."""
    only_times = parse_dose_line("1일 3회")

    assert only_times.dose_quantity is None
    assert only_times.times_per_day == 3
    assert only_times.days is None


def test_parse_dose_line_normalizes_before_parsing() -> None:
    result = parse_dose_line("  1회  1정씩   1일  3회   7일분  ")

    assert result.dose_quantity == "1정"
    assert result.times_per_day == 3
    assert result.days == 7
