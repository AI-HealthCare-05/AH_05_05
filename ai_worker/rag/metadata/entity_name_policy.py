"""지식 release의 정식 엔터티 이름에 적용하는 공통 품질 규칙."""

_GENERIC_KNOWLEDGE_ENTITY_CATEGORY_NAMES = frozenset(
    {
        "영양제",
        "보충제",
        "건강기능식품",
        "의약품",
        "약물",
        "음식",
        "식품",
        "음료",
    },
)


def is_generic_knowledge_entity_category(name: str) -> bool:
    """제품·성분·음식의 정식명이 아닌 일반 범주명인지 판정한다."""
    return "".join(name.casefold().split()) in _GENERIC_KNOWLEDGE_ENTITY_CATEGORY_NAMES
