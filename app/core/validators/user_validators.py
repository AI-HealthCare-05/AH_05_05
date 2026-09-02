import re
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from app.core import config

MIN_PASSWORD_LENGTH = 8
# 화면에서 받아야 할 길이 기준. DB 에는 해시가 저장되므로 컬럼 폭과는 무관하다.
# 프론트 PASSWORD_MAX_LENGTH 와 같은 값이다.
MAX_PASSWORD_LENGTH = 30
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

    두 곳이 같은 함수를 쓰므로 정책이 어긋날 일이 없다. **상한도 관리자에 함께 적용된다.**
    (관리자 임시 비밀번호 생성기는 12자라 상한에 걸리지 않는다.)
    무엇이 부족한지 알려줘야 사용자가 고칠 수 있으므로, 빠진 종류를 모아서 알려준다.

    **이 함수는 「새로 정하는 비밀번호」에만 붙인다.** 로그인·탈퇴 확인·비밀번호 변경의
    *현재* 비밀번호처럼 대조용으로 받는 값에 붙이면, 이 정책이 생기기 전에 더 긴 비밀번호로
    가입한 계정이 로그인·탈퇴·변경 자체를 못 하게 된다.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"비밀번호는 {MAX_PASSWORD_LENGTH}자 이하여야 합니다.")

    missing = [label for pattern, label in _PASSWORD_CHARACTER_RULES if not re.search(pattern, password)]
    if missing:
        raise ValueError(f"비밀번호에 {', '.join(missing)}를 각각 1개 이상 포함해야 합니다.")

    return password


# 프론트 shared/lib/name.ts 의 NAME_PATTERN 과 같은 규칙이다. 한쪽만 고치면 안 된다.
_NAME_PATTERN = re.compile(r"[가-힣a-zA-Z]+")
MASK_MAX = 3


def validate_name(name: str) -> str:
    """이름은 한글 완성형과 영문만 받는다.

    프론트에서 막아도 API 를 직접 부르면 들어오므로 여기서도 막는다
    (validate_ascii_email 과 같은 이유다).

    공백을 허용하지 않는다 — 「김 진형」과 「김진형」이 같은 사람인데 다르게 저장되면
    관리자 콘솔 검색에서 갈린다. 영문 이름은 붙여 쓴다.
    낱자(ㄱ, ㅏ)도 막는다 — 한글 IME 조합이 끝나지 않은 값이 그대로 넘어온다.

    DTO 가 strip_whitespace 로 앞뒤 공백을 먼저 잘라내므로 여기에는 이미 다듬어진 값이 온다.
    """
    if not _NAME_PATTERN.fullmatch(name):
        raise ValueError("이름은 한글과 영문만 사용할 수 있습니다.")

    return name


def mask_name(raw: str) -> str:
    """공개 후기 작성자 이름의 가운데를 최대 세 글자까지 가린다."""
    name = (raw or "").strip()
    if not name:
        return "익명"
    if len(name) == 1:
        return "*"
    if len(name) == 2:
        return f"{name[0]}*"
    stars = "*" * min(len(name) - 2, MASK_MAX)
    return f"{name[0]}{stars}{name[-1]}"


def validate_ascii_email(email: str) -> str:
    """한글 같은 비 ASCII 이메일을 막는다.

    pydantic EmailStr 은 SMTPUTF8 주소를 허용해 `한글@example.com` 도 그대로 통과시킨다.
    프론트에서 한글 입력을 걸러도 API 를 직접 부르면 들어오므로 여기서도 막는다.
    """
    if isinstance(email, str) and not email.isascii():
        raise ValueError("이메일은 영문, 숫자와 기호만 사용할 수 있습니다.")

    return email


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
