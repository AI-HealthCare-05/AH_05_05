import re

_EXPLICIT_INTERACTION_PATTERN = re.compile(
    r"상호작용|병용|조합|시간(?:을)?\s*띄",
)
_COADMINISTRATION_PATTERN = re.compile(
    r"(?:같이|함께)\s*(?:먹|복용|섭취)",
)
_RELATIONAL_AVOIDANCE_PATTERN = re.compile(
    r"(?:\S+(?:과|와)\s*)?(?:같이|함께)\s*"
    r"(?:피해야|피할|주의해야)\s*(?:할\s*)?"
    r"(?:약|의약품|영양제|음식|식품|음료)",
)
_INTAKE_CONTEXT_AVOIDANCE_PATTERN = re.compile(
    r"(?:먹(?:을|는)?|복용|섭취)\s*"
    r"(?:중|동안|할\s*때|하는\s*동안|했을\s*때|때)"
    r".{1,48}?"
    r"(?:피해야|피하|먹지\s*말|복용하지\s*말|섭취하지\s*말)",
)


def is_interaction_question(question: str) -> bool:
    """두 복용 대상 사이의 관계를 묻는 표현인지 판별한다."""

    normalized = re.sub(r"\s+", " ", question).strip()
    if not normalized:
        return False
    return any(
        pattern.search(normalized) is not None
        for pattern in (
            _EXPLICIT_INTERACTION_PATTERN,
            _COADMINISTRATION_PATTERN,
            _RELATIONAL_AVOIDANCE_PATTERN,
            _INTAKE_CONTEXT_AVOIDANCE_PATTERN,
        )
    )
