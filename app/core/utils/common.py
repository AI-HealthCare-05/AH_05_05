import re


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
