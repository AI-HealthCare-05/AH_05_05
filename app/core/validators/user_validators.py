import re
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from app.core import config

MIN_PASSWORD_LENGTH = 8
MIN_BIRTH_DATE = date(1900, 1, 1)

# 비밀번호에 반드시 포함되어야 하는 문자 종류.
_PASSWORD_CHARACTER_RULES = (
    (r"[A-Z]", "대문자"),
    (r"[a-z]", "소문자"),
    (r"[0-9]", "숫자"),
    (r"[^a-zA-Z0-9]", "특수문자"),
)


def validate_password(password: str) -> str:
    """사용자·관리자 공통 비밀번호 정책.

    두 곳이 같은 함수를 쓰므로 정책이 어긋날 일이 없다.
    무엇이 부족한지 알려줘야 사용자가 고칠 수 있으므로, 빠진 종류를 모아서 알려준다.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")

    missing = [label for pattern, label in _PASSWORD_CHARACTER_RULES if not re.search(pattern, password)]
    if missing:
        raise ValueError(f"비밀번호에 {', '.join(missing)}를 각각 1개 이상 포함해야 합니다.")

    return password


def validate_phone_number(phone_number: str) -> str:
    patterns = [
        r"01(?:0|1|[6-9])-\d{3,4}-\d{4}",  # 011-123-4567, 010-1234-5678
        r"01(?:0|1|[6-9])\d{7,8}",  # 0111234567, 01012345678
        r"\+821(?:0|1|[6-9])\d{7,8}",  # +821012345678
    ]

    if not any(re.fullmatch(p, phone_number) for p in patterns):
        raise ValueError("유효하지 않은 휴대폰 번호 형식입니다.")

    return phone_number


def validate_birthday(birthday: date | str) -> date:
    if isinstance(birthday, str):
        try:
            birthday = date.fromisoformat(birthday)
        except ValueError as e:
            raise ValueError("올바르지 않은 날짜 형식입니다. format: YYYY-MM-DD") from e

    today = datetime.now(tz=config.TIMEZONE).date()
    if birthday < MIN_BIRTH_DATE:
        raise ValueError("1900년 1월 1일 이후의 날짜를 입력해주세요.")
    if birthday > today:
        raise ValueError("미래 날짜는 입력할 수 없습니다.")
    if birthday > today - relativedelta(years=14):
        raise ValueError("서비스 약관에 따라 만14세 미만은 회원가입이 불가합니다.")

    return birthday
