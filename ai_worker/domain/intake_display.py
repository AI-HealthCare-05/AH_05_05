import re
from collections.abc import Iterable

_PARENTHETICAL_DESCRIPTION_PATTERN = re.compile(r"\s*[\(（][^()（）]*[\)）]")


def format_active_medication_names(names: Iterable[str]) -> list[str]:
    """활성 복약정보를 설명 없는 제품명 목록으로 정규화한다."""

    formatted: list[str] = []
    seen: set[str] = set()
    for value in names:
        name = _PARENTHETICAL_DESCRIPTION_PATTERN.sub("", value)
        name = " ".join(name.split())
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        formatted.append(name)
    return formatted
