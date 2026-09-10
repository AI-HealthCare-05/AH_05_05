import re


def mask_admin_user_name(name: str) -> str:
    """관리자 회원조회 응답에서 이름의 첫 글자와 마지막 글자만 남긴다."""
    if len(name) <= 2:
        return name
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


def mask_email_address(email: str) -> str:
    """이메일 로컬 영역의 처음 세 글자를 제외한 나머지를 가린다."""
    local_part, separator, domain = email.partition("@")
    if not separator:
        return email
    return f"{local_part[:3]}{'*' * max(0, len(local_part) - 3)}@{domain}"


def normalize_phone_number(phone_number: str) -> str:
    if phone_number.startswith("+82"):
        phone_number = "0" + phone_number[3:]
    phone_number = re.sub(r"\D", "", phone_number)

    return phone_number


def format_phone_number(phone_number: str | None) -> str | None:
    """휴대폰 번호의 숫자는 유지하고 국내 표시 형식으로 변환한다."""
    if phone_number is None:
        return None

    normalized = normalize_phone_number(phone_number)
    if len(normalized) == 11:
        return f"{normalized[:3]}-{normalized[3:7]}-{normalized[7:]}"
    if len(normalized) == 10:
        return f"{normalized[:3]}-{normalized[3:6]}-{normalized[6:]}"
    return normalized


def mask_phone_number(phone_number: str | None) -> str | None:
    """목록 노출용으로 전화번호 가운데 자리를 마스킹한다."""
    formatted = format_phone_number(phone_number)
    if formatted is None:
        return None

    parts = formatted.split("-")
    if len(parts) != 3:
        return formatted
    return f"{parts[0]}-{'•' * len(parts[1])}-{parts[2]}"
