import re

_EXPLICIT_INTERACTION_PATTERN = re.compile(
    r"상호작용|병용|조합|시간(?:을)?\s*띄",
)
_COADMINISTRATION_PATTERN = re.compile(
    r"(?:같이|함께)\s*(?:(?:먹|머|묵)[가-힣]*|복용|섭취)",
)
_TYPOED_COADMINISTRATION_PATTERN = re.compile(
    r"(?:같이|함께)\s*(?:머|묵)[가-힣]*",
)
_RELATIONAL_INTAKE_PATTERN = re.compile(
    r"\S*(?:과|와|이랑|랑)\s+"
    r"(?:[가-힣A-Za-z0-9]+\s+){0,3}[가-힣A-Za-z0-9]+(?:을|를)?\s+"
    r"먹어도\s*(?:돼|되나요)\??",
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
_RELATIONAL_EFFECT_PATTERN = re.compile(
    r"(?:복용|섭취).{1,48}?"
    r"(?:흡수|효과|작용|수치|농도).{0,24}?"
    r"(?:영향|변화|감소|증가)",
)
_DRUG_FOOD_USAGE_PATTERN = re.compile(
    r"(?:음식|식품|음료|주스|물)(?:이나|나|과|와|이랑|랑)?"
    r".{0,32}?(?:복용|먹|섭취)",
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
            _RELATIONAL_INTAKE_PATTERN,
            _RELATIONAL_AVOIDANCE_PATTERN,
            _INTAKE_CONTEXT_AVOIDANCE_PATTERN,
            _RELATIONAL_EFFECT_PATTERN,
            _DRUG_FOOD_USAGE_PATTERN,
        )
    )


def requires_resolved_pair_for_interaction(question: str) -> bool:
    """오타가 있는 병용 표현은 두 대상이 확인된 경우에만 상호작용으로 취급한다."""

    normalized = re.sub(r"\s+", " ", question).strip()
    return _TYPOED_COADMINISTRATION_PATTERN.search(normalized) is not None
