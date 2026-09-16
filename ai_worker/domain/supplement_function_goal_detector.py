"""건강기능식품의 기능성 목표를 묻는 자연어 질문을 판별한다."""

import re

_FORMAL_SUPPLEMENT_FUNCTION_GOAL_PATTERN = re.compile(
    r"(?:건강기능식품|기능성\s*원료|영양제).{0,24}(?:기능|개선|관리|도움)|"
    r"(?:기능|개선|관리|도움).{0,24}(?:건강기능식품|기능성\s*원료|영양제)",
    flags=re.IGNORECASE,
)
_NATURAL_SUPPLEMENT_FUNCTION_GOAL_PATTERN = re.compile(
    r"(?:좋아지|개선|관리|도움|잘\s*자|숙면).{0,20}"
    r"(?:뭘|무엇|어떤\s*(?:것|성분|영양제)?).{0,12}(?:먹|섭취)",
    flags=re.IGNORECASE,
)
_COLLOQUIAL_SUPPLEMENT_GOAL_PATTERN = re.compile(
    r"(?:숙면|수면|잠\s*잘\s*자|눈|관절|장|피부|혈행).{0,16}(?:좋은|위한).{0,8}(?:영양제|건강기능식품)"
)


def is_supplement_function_goal_question(question: str) -> bool:
    """특정 제품명이 없는 기능성 원료 탐색 질문인지 반환한다."""

    normalized = re.sub(r"\s+", " ", question).strip()
    return bool(
        _FORMAL_SUPPLEMENT_FUNCTION_GOAL_PATTERN.search(normalized)
        or _NATURAL_SUPPLEMENT_FUNCTION_GOAL_PATTERN.search(normalized)
        or _COLLOQUIAL_SUPPLEMENT_GOAL_PATTERN.search(normalized)
    )
