"""말뭉치에서 유도한 성분명 한/영 별칭.

지식베이스의 상호작용 근거 일부가 영문 성분명(`warfarin`)으로만 색인돼 있어 한국어 질의로는
닿지 않는다. 이 사전은 그 간극만 메운다. 항목은 사람이 쓰지 않고
`scripts/build_ingredient_name_aliases.py`가 말뭉치와 허가 성분 카탈로그에서 생성한다.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class IngredientNameAliases(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    generated_at: str
    source_collection: str
    aliases: dict[str, str] = Field(min_length=1)


@lru_cache(maxsize=1)
def load_ingredient_name_aliases() -> IngredientNameAliases:
    return IngredientNameAliases.model_validate_json(
        (Path(__file__).parent / "data" / "ingredient_name_aliases.json").read_text(encoding="utf-8")
    )


def aliases_match_collection(collection_name: str) -> bool:
    """사전이 지금 조회하는 말뭉치에서 만들어진 것인지 확인한다."""
    return load_ingredient_name_aliases().source_collection == collection_name.strip()


_active_collection: str | None = None


def use_collection(collection_name: str) -> None:
    """조회할 말뭉치를 고정한다. 사전이 다른 말뭉치에서 왔으면 별칭을 쓰지 않는다.

    컬렉션이 교체되면 사전은 조용히 다른 말뭉치에 적용된다. 성분 표기가 바뀐
    말뭉치에 낡은 별칭을 쓰면 없는 근거를 엮는다. 불일치를 예외로 막지는 않는다.
    별칭이 없어도 검색은 변경 이전과 동일하게 동작하므로, 서비스를 세우지 못하게
    하는 쪽이 더 위험하다.
    """
    global _active_collection
    _active_collection = collection_name.strip()
    _alias_pairs.cache_clear()


@lru_cache(maxsize=1)
def _alias_pairs() -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """영문→한글, 한글→영문 두 방향을 만든다. 한글 하나에 영문 이형이 여럿일 수 있다."""
    if _active_collection is not None and not aliases_match_collection(_active_collection):
        return {}, {}
    english_to_korean = {
        english.casefold(): korean for english, korean in load_ingredient_name_aliases().aliases.items()
    }
    korean_to_english: dict[str, list[str]] = {}
    for english, korean in english_to_korean.items():
        korean_to_english.setdefault(korean.casefold(), []).append(english)
    return english_to_korean, {korean: tuple(values) for korean, values in korean_to_english.items()}


def english_aliases_for(korean_name: str) -> tuple[str, ...]:
    """한글 성분명에 대응하는 영문 이름들. 없으면 빈 튜플."""
    _, korean_to_english = _alias_pairs()
    return korean_to_english.get(korean_name.casefold(), ())


def korean_alias_for(english_name: str) -> str | None:
    """영문 성분명에 대응하는 한글 이름. 없으면 None."""
    english_to_korean, _ = _alias_pairs()
    return english_to_korean.get(english_name.casefold())
