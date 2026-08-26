import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from ai_worker.schemas.interaction import (
    InteractionEntity,
    InteractionEntityKind,
    build_interaction_pair_key,
)


class SupplementInteractionPair(BaseModel):
    """현재 코퍼스에서 검색 가능한 영양성분 조합의 어휘 계약."""

    model_config = ConfigDict(frozen=True)

    canonical_names: tuple[str, str]
    alias_groups: tuple[tuple[str, ...], tuple[str, ...]]
    english_query: str = Field(min_length=1)

    @property
    def pair_key(self) -> str:
        left, right = (
            InteractionEntity(
                kind=InteractionEntityKind.SUPPLEMENT,
                display_name=name,
            )
            for name in self.canonical_names
        )
        return build_interaction_pair_key(left, right)


_KNOWN_PAIRS = (
    SupplementInteractionPair(
        canonical_names=("칼슘", "철분"),
        alias_groups=(
            ("칼슘", "calcium", "ca"),
            ("철분", "iron", "ferrous", "ferric", "fe"),
        ),
        english_query="calcium iron absorption interaction",
    ),
    SupplementInteractionPair(
        canonical_names=("아연", "철분"),
        alias_groups=(
            ("아연", "zinc", "zn"),
            ("철분", "iron", "ferrous", "ferric", "fe"),
        ),
        english_query="zinc iron status interaction supplementation",
    ),
    SupplementInteractionPair(
        canonical_names=("비타민 C", "철분"),
        alias_groups=(
            ("비타민 c", "비타민c", "vitamin c", "ascorbic acid", "ascorbate"),
            ("철분", "iron", "ferrous", "ferric", "fe"),
        ),
        english_query="vitamin C iron supplementation interaction",
    ),
    SupplementInteractionPair(
        canonical_names=("비타민 C", "구리"),
        alias_groups=(
            ("비타민 c", "비타민c", "vitamin c", "ascorbic acid", "ascorbate"),
            ("구리", "copper", "cu"),
        ),
        english_query="vitamin C copper interaction oxidative stress",
    ),
)


def find_supplement_interaction_pair(
    text: str,
) -> SupplementInteractionPair | None:
    for pair in _KNOWN_PAIRS:
        if supplement_pair_matches_text(pair, text):
            return pair
    return None


def supplement_pair_matches_text(
    pair: SupplementInteractionPair,
    *values: str,
) -> bool:
    text = _normalize_text(" ".join(values))
    return all(any(_contains_alias(text, alias) for alias in aliases) for aliases in pair.alias_groups)


def known_supplement_names_in(text: str) -> list[str]:
    normalized = _normalize_text(text)
    names: list[str] = []
    for pair in _KNOWN_PAIRS:
        for name, aliases in zip(
            pair.canonical_names,
            pair.alias_groups,
            strict=True,
        ):
            if name not in names and any(_contains_alias(normalized, alias) for alias in aliases):
                names.append(name)
    return names


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _contains_alias(normalized_text: str, alias: str) -> bool:
    normalized_alias = _normalize_text(alias)
    if re.fullmatch(r"[a-z0-9]{1,2}", normalized_alias):
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])",
                normalized_text,
            )
        )
    return normalized_alias in normalized_text
