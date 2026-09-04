"""app/core/validators/user_validators.py 의 순수 함수 테스트.

DB·API 를 쓰지 않는다. 값을 넣으면 값이 나오는 함수라 함수를 직접 부른다.

DTO 가 거는 길이 제한(이름 2~20자 등)은 여기서 보지 않는다. 그쪽은
app/tests/user_apis/test_input_length_limits.py 가 맡는다.
"""

from datetime import date, datetime, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from app.core import config
from app.core.validators.user_validators import (
    MASK_MAX,
    MAX_PASSWORD_LENGTH,
    MIN_BIRTH_DATE,
    MIN_PASSWORD_LENGTH,
    mask_name,
    validate_ascii_email,
    validate_birthday,
    validate_name,
    validate_password,
    validate_phone_number,
)


def _today() -> date:
    """validate_birthday 와 같은 기준으로 오늘을 구한다.

    오늘 날짜를 하드코딩하면 내년에 이 테스트가 저절로 깨진다.
    """
    return datetime.now(tz=config.TIMEZONE).date()


# ─────────────────────────── validate_phone_number ───────────────────────────


@pytest.mark.parametrize(
    "phone_number",
    [
        "010-1234-5678",  # 하이픈 4자리
        "011-123-4567",  # 하이픈 3자리
        "01012345678",  # 하이픈 없음 8자리
        "0111234567",  # 하이픈 없음 7자리
        "+821012345678",  # 국가번호
        "016-1234-5678",
        "017-1234-5678",
        "018-1234-5678",
        "019-1234-5678",
    ],
)
def test_validate_phone_number_accepts_mobile_formats(phone_number: str) -> None:
    assert validate_phone_number(phone_number) == phone_number


@pytest.mark.parametrize(
    "phone_number",
    [
        "0212345678",  # 지역번호
        "0151234567",  # 015 는 허용 접두사가 아니다
        "012-1234-5678",
        "010-12345-6789",  # 자릿수 초과
        "010 1234 5678",  # 공백 구분
        "01012345678a",  # 뒤에 문자 — re.fullmatch 라 거부된다
        "a01012345678",  # 앞에 문자
        "+8201012345678",  # 국가번호 뒤에 0
        "",
    ],
)
def test_validate_phone_number_rejects_invalid_formats(phone_number: str) -> None:
    with pytest.raises(ValueError, match="유효하지 않은 휴대폰 번호 형식입니다."):
        validate_phone_number(phone_number)


# ───────────────────────────── validate_birthday ─────────────────────────────


def test_validate_birthday_accepts_exact_fourteenth_birthday() -> None:
    """만 14세가 되는 날 당일은 통과한다. 이 경계가 이 함수의 핵심이다."""
    fourteen = _today() - relativedelta(years=14)

    assert validate_birthday(fourteen) == fourteen


def test_validate_birthday_rejects_one_day_short_of_fourteen() -> None:
    one_day_short = _today() - relativedelta(years=14) + timedelta(days=1)

    with pytest.raises(ValueError, match="만14세 미만은 회원가입이 불가합니다."):
        validate_birthday(one_day_short)


def test_validate_birthday_accepts_adult() -> None:
    thirty = _today() - relativedelta(years=30)

    assert validate_birthday(thirty) == thirty


@pytest.mark.parametrize("offset_days", [1, 30])
def test_validate_birthday_rejects_future(offset_days: int) -> None:
    with pytest.raises(ValueError, match="미래 날짜는 입력할 수 없습니다."):
        validate_birthday(_today() + timedelta(days=offset_days))


def test_validate_birthday_rejects_today_as_under_fourteen() -> None:
    with pytest.raises(ValueError, match="만14세 미만은 회원가입이 불가합니다."):
        validate_birthday(_today())


def test_validate_birthday_accepts_lower_bound_itself() -> None:
    """1900-01-01 당일은 하한에 포함된다(`<` 비교라 같은 날은 통과)."""
    assert validate_birthday(MIN_BIRTH_DATE) == date(1900, 1, 1)


def test_validate_birthday_rejects_before_lower_bound() -> None:
    with pytest.raises(ValueError, match="1900년 1월 1일 이후의 날짜를 입력해주세요."):
        validate_birthday(date(1899, 12, 31))


def test_validate_birthday_parses_iso_string_into_date() -> None:
    result = validate_birthday("1990-05-03")

    assert result == date(1990, 5, 3)
    assert isinstance(result, date)


@pytest.mark.parametrize("raw", ["1990/05/03", "1990-13-01", "1990-02-30", "", "not-a-date"])
def test_validate_birthday_rejects_malformed_string(raw: str) -> None:
    with pytest.raises(ValueError, match="올바르지 않은 날짜 형식입니다. format: YYYY-MM-DD"):
        validate_birthday(raw)


# ───────────────────────────── validate_password ─────────────────────────────

# 정상 조합을 유지하면서 길이만 늘린다. 대문자·소문자·숫자·특수문자가 모두 들어 있다.
_PASSWORD_8 = "Abcd123!"
_PASSWORD_30 = "Abcd123!" + "e" * (MAX_PASSWORD_LENGTH - len(_PASSWORD_8))
_PASSWORD_31 = _PASSWORD_30 + "f"


def test_validate_password_accepts_minimum_length() -> None:
    assert len(_PASSWORD_8) == MIN_PASSWORD_LENGTH
    assert validate_password(_PASSWORD_8) == _PASSWORD_8


def test_validate_password_accepts_maximum_length() -> None:
    assert len(_PASSWORD_30) == MAX_PASSWORD_LENGTH
    assert validate_password(_PASSWORD_30) == _PASSWORD_30


def test_validate_password_rejects_too_short() -> None:
    with pytest.raises(ValueError, match="비밀번호는 8자 이상이어야 합니다."):
        validate_password("Abc123!")


def test_validate_password_rejects_too_long() -> None:
    assert len(_PASSWORD_31) == MAX_PASSWORD_LENGTH + 1
    with pytest.raises(ValueError, match="비밀번호는 30자 이하여야 합니다."):
        validate_password(_PASSWORD_31)


@pytest.mark.parametrize(
    ("password", "missing"),
    [
        ("abcd123!", "대문자"),
        ("ABCD123!", "소문자"),
        ("Abcdefg!", "숫자"),
        ("Abcd1234", "특수문자"),
    ],
)
def test_validate_password_reports_the_missing_character_type(password: str, missing: str) -> None:
    with pytest.raises(ValueError, match=f"비밀번호에 {missing}를 각각 1개 이상 포함해야 합니다."):
        validate_password(password)


def test_validate_password_reports_every_missing_type_in_one_message() -> None:
    """빠진 종류를 모아서 알려준다. 순서는 대문자 → 소문자 → 숫자 → 특수문자다."""
    with pytest.raises(ValueError, match="비밀번호에 대문자, 특수문자를 각각 1개 이상 포함해야 합니다."):
        validate_password("test1234")


# ────────────────────────────── validate_name ───────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "김진형",
        "KimJinhyeong",
        "김Kim",
        "金鎭亨",  # 한자
        "山田",
        "Мария",  # 키릴
        "Élodie",
        "ㅋㅋㅋ",  # 한글 낱자도 Unicode 상 문자(Lo)라 통과한다
    ],
)
def test_validate_name_accepts_letters_of_any_language(name: str) -> None:
    assert validate_name(name) == name


def test_validate_name_does_not_check_length() -> None:
    """길이 제한(2~20자)은 DTO 의 StringConstraints 가 건다. 이 함수는 보지 않는다."""
    assert validate_name("가") == "가"
    assert validate_name("가" * 50) == "가" * 50


@pytest.mark.parametrize(
    "name",
    [
        "김 진형",  # 가운데 공백
        "  김진형  ",  # 앞뒤 공백 — 잘라내지 않고 거부한다
        "김진형2",
        "김철수!",
        "김철수\U0001f600",  # 이모지
        "Kim-Jinhyeong",
        "",
        "   ",
    ],
)
def test_validate_name_rejects_non_letters(name: str) -> None:
    with pytest.raises(ValueError, match="이름에는 숫자, 공백, 특수문자를 사용할 수 없습니다."):
        validate_name(name)


def test_validate_name_returns_nfc_normalized_value() -> None:
    """NFD 로 들어와도 NFC 로 저장되게 정규화한다.

    같은 이름이 표기만 달라 두 행으로 갈리면 관리자 목록 검색이 어긋난다.
    """
    decomposed = "Élodie"  # E + 결합 악센트
    composed = "Élodie"  # É

    assert decomposed != composed
    assert validate_name(decomposed) == composed


# ──────────────────────────────── mask_name ─────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "익명"),
        ("   ", "익명"),  # strip 후 판단한다
        (None, "익명"),
        ("홍", "*"),
        ("홍길", "홍*"),
        ("홍길동", "홍*동"),
        ("홍길동일", "홍**일"),
        ("홍길동일이", "홍***이"),
        ("  홍길동  ", "홍*동"),
    ],
)
def test_mask_name_keeps_first_and_last_characters(raw: str | None, expected: str) -> None:
    """검증기가 아니라 변환 함수다. 예외를 던지지 않고 값을 돌려준다."""
    assert mask_name(raw) == expected


def test_mask_name_caps_stars_at_three() -> None:
    """이름이 길어져도 별은 세 개를 넘지 않는다."""
    assert mask_name("홍길동일이삼사") == "홍***사"
    assert mask_name("가" * 30) == "가***가"
    assert mask_name("가" * 30).count("*") == MASK_MAX


# ──────────────────────────── validate_ascii_email ──────────────────────────


@pytest.mark.parametrize("email", ["user@example.com", "USER+tag@sub.example.co.kr", "a1@b.io"])
def test_validate_ascii_email_accepts_ascii(email: str) -> None:
    assert validate_ascii_email(email) == email


@pytest.mark.parametrize(
    "email",
    ["한글@example.com", "user@한글.com", "ユーザー@example.com", "user@exámple.com"],
)
def test_validate_ascii_email_rejects_non_ascii(email: str) -> None:
    with pytest.raises(ValueError, match="이메일은 영문, 숫자와 기호만 사용할 수 있습니다."):
        validate_ascii_email(email)


def test_validate_ascii_email_does_not_check_the_address_format() -> None:
    """형식 검사는 pydantic EmailStr 이 한다. 이 함수는 ASCII 여부만 본다."""
    assert validate_ascii_email("not-an-email") == "not-an-email"
