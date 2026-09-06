"""app/core/utils/common.py 의 전화번호 3종 테스트.

회원 관리 화면의 번호 표시를 만드는 함수다.

    phone=mask_phone_number(...)    목록 — 가운데를 가린다
    phone=format_phone_number(...)  상세 — 전체를 보여준다

DB·API 를 쓰지 않는다.
"""

import pytest

from app.core.utils.common import format_phone_number, mask_phone_number, normalize_phone_number

# ───────────────────────── normalize_phone_number ──────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01012345678", "01012345678"),  # 이미 정규화된 값 — 멱등
        ("010-1234-5678", "01012345678"),
        ("010 1234 5678", "01012345678"),
        ("(010) 1234.5678", "01012345678"),
        ("+821012345678", "01012345678"),
        ("+82-10-1234-5678", "01012345678"),
        ("+82 10 1234 5678", "01012345678"),
        ("0111234567", "0111234567"),
    ],
)
def test_normalize_phone_number_strips_to_domestic_digits(raw: str, expected: str) -> None:
    assert normalize_phone_number(raw) == expected


def test_normalize_phone_number_replaces_country_code_before_stripping() -> None:
    """`+82` 치환이 `\\D` 제거보다 **먼저** 일어난다. 순서가 결과를 바꾼다.

    숫자만 먼저 지웠다면 `+821012345678` 은 `821012345678`(12자리)이 되어
    앞자리 0 이 붙지 않는다.
    """
    assert normalize_phone_number("+821012345678") == "01012345678"
    assert len(normalize_phone_number("+821012345678")) == 11


def test_normalize_phone_number_is_idempotent() -> None:
    once = normalize_phone_number("+82-10-1234-5678")

    assert normalize_phone_number(once) == once


@pytest.mark.parametrize(("raw", "expected"), [("", ""), ("abc", ""), ("---", ""), ("전화번호", "")])
def test_normalize_phone_number_returns_empty_when_no_digits(raw: str, expected: str) -> None:
    assert normalize_phone_number(raw) == expected


# ────────────────────────── format_phone_number ────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01012345678", "010-1234-5678"),  # 11자리
        ("0111234567", "011-123-4567"),  # 10자리
        ("010-1234-5678", "010-1234-5678"),
        ("+821012345678", "010-1234-5678"),  # 내부에서 정규화를 먼저 부른다
    ],
)
def test_format_phone_number_adds_hyphens(raw: str, expected: str) -> None:
    assert format_phone_number(raw) == expected


def test_format_phone_number_passes_none_through() -> None:
    assert format_phone_number(None) is None


@pytest.mark.parametrize("raw", ["012345678", "0101234567890", "1", ""])
def test_format_phone_number_returns_digits_unformatted_for_other_lengths(raw: str) -> None:
    """11자리도 10자리도 아니면 하이픈 없이 숫자만 돌려준다.

    이 갈래가 mask_phone_number 의 마스킹 누락으로 이어진다.
    """
    assert format_phone_number(raw) == normalize_phone_number(raw)
    assert "-" not in format_phone_number(raw)


def test_format_phone_number_is_stable_on_round_trip() -> None:
    once = format_phone_number("01012345678")

    assert format_phone_number(once) == once


# ─────────────────────────── mask_phone_number ─────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01012345678", "010-••••-5678"),  # 11자리 — 가운데 4자리
        ("010-1234-5678", "010-••••-5678"),
        ("+821012345678", "010-••••-5678"),
        ("0111234567", "011-•••-4567"),  # 10자리 — 가운데 3자리
    ],
)
def test_mask_phone_number_hides_the_middle_block(raw: str, expected: str) -> None:
    assert mask_phone_number(raw) == expected


def test_mask_phone_number_passes_none_through() -> None:
    assert mask_phone_number(None) is None


@pytest.mark.parametrize(("raw", "middle_length"), [("01012345678", 4), ("0111234567", 3)])
def test_mask_phone_number_uses_one_bullet_per_hidden_digit(raw: str, middle_length: int) -> None:
    masked = mask_phone_number(raw)

    assert masked.split("-")[1] == "•" * middle_length


@pytest.mark.parametrize("raw", ["01012345678", "0111234567"])
def test_mask_phone_number_keeps_the_first_and_last_blocks(raw: str) -> None:
    """앞 3자리와 뒷 4자리는 그대로 남는다. 가리는 것은 가운데뿐이다."""
    formatted = format_phone_number(raw)
    masked = mask_phone_number(raw)

    assert masked.split("-")[0] == formatted.split("-")[0]
    assert masked.split("-")[2] == formatted.split("-")[2]


@pytest.mark.parametrize("raw", ["012345678", "0101234567890", "1"])
def test_mask_phone_number_returns_the_value_unmasked_when_it_has_no_hyphens(raw: str) -> None:
    """⚠️ 자릿수가 10·11 이 아니면 **가리지 않고 원본을 그대로 돌려준다.**

    format_phone_number 가 하이픈을 붙이지 못해 `parts` 가 3개가 아니고,
    `if len(parts) != 3: return formatted` 로 빠진다.

    입구에서 validate_phone_number 가 10·11 자리 휴대폰 형식만 통과시키므로
    저장된 값으로는 현재 도달하지 않는다. 다만 이 함수 단독으로는 마스킹을
    보장하지 않는다는 사실을 남긴다.
    """
    masked = mask_phone_number(raw)

    assert masked == normalize_phone_number(raw)
    assert "•" not in masked


def test_mask_phone_number_goes_through_format_phone_number() -> None:
    """같은 번호를 어떤 표기로 넣어도 결과가 같다 — 내부에서 정규화·서식을 거치기 때문이다."""
    variants = ["01012345678", "010-1234-5678", "010 1234 5678", "+821012345678"]

    assert len({mask_phone_number(v) for v in variants}) == 1
