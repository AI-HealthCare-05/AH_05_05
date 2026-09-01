import re
import unicodedata

from ai_worker.schemas.medication_search import SupplementInteractionPair

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


def canonical_supplement_name(value: str) -> str | None:
    normalized = _normalize_text(value)
    for pair in _KNOWN_PAIRS:
        for name, aliases in zip(
            pair.canonical_names,
            pair.alias_groups,
            strict=True,
        ):
            if any(_contains_alias(normalized, alias) for alias in aliases):
                return name
    return None


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
    if len(normalized_alias) == 2 and normalized_alias.endswith("분"):
        base_name = normalized_alias[:-1]
        if re.search(
            rf"(?<![가-힣a-z0-9]){re.escape(base_name)}(?![가-힣a-z0-9])",
            normalized_text,
        ):
            return True
    return normalized_alias in normalized_text
