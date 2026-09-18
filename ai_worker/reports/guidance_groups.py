"""Stable registered-product grouping for lifestyle guidance projections."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import unescape
from typing import Any

_RAG_ITEM_TYPE_RE = re.compile(r"^rag:[^:]+:(medication|supplement):", re.IGNORECASE)
_REGISTERED_ITEM_TYPES = frozenset({"medication", "supplement"})
_MEDICATION_ONLY_CARD_RE = re.compile(r"^(?:food-drink|driving):\d+$", re.IGNORECASE)
_SUPPLEMENT_ONLY_CARD_RE = re.compile(r"^timing:", re.IGNORECASE)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。])(?!(?:\.|(?<=\d\.)(?=\d)))\s*")
_GUIDANCE_WORD_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_GUIDANCE_STOP_WORDS = frozenset(
    {
        "있는",
        "있으면",
        "있다면",
        "있",
        "경우",
        "때문",
        "위해",
        "대해",
        "대한",
        "때",
        "시",
        "섭취",
        "복용",
        "필요",
        "상담",
        "전문가",
        "의사",
        "약사",
        "주의",
        "확인",
        "하세요",
        "합니다",
        "있습니다",
        "나타날",
        "나타나면",
        "수",
        "것",
        "및",
        "또는",
        "그리고",
    }
)
_GUIDANCE_PARTICLE_SUFFIXES = (
    "이라면",
    "이라도",
    "라면",
    "다면",
    "하면",
    "하세요",
    "하십시오",
    "해야",
    "하기",
    "하는",
    "할",
    "하고",
    "에는",
    "에서",
    "으로",
    "에게",
    "와",
    "과",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "도",
    "만",
    "의",
    "로",
    "요",
)
_NEGATION_RE = re.compile(r"(?:않|없|금지|중단|피하|주의)")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|g|ml|정|회|일|시간|%|밀리그램|그램)?", re.IGNORECASE)
_ACTION_SIGNAL_RE = re.compile(r"(?:상담|확인|중단|피하|복용하|섭취하|주의하|하세요|하십시오)")
COMMON_INGREDIENT_DISCLAIMER = "정확한 제품은 미확정이며, 확인된 성분 공통 안내입니다."
BODY_PREVIEW_LIMIT = 200


@dataclass
class GuidanceProductGroup:
    """A display group whose cards all refer to the same registered products."""

    key: str
    title: str
    cards: list[Any]


@dataclass(frozen=True)
class GuidanceProductDisplay:
    """One compact, product-level projection for every lifestyle export.

    ``warning_titles`` and ``categories`` both preserve first-seen exact
    values.  The summaries omit the exact common-ingredient disclaimer, which
    is instead emitted once through ``common_ingredient_disclaimer``.
    Warning titles, actions, summaries, and source IDs are all stable
    first-seen unions across every card in the product group: an identical
    title, body, or action repeated by more than one card is merged into a
    single entry, while distinct wording is preserved as-is.

    ``body_preview`` is set only when the joined ``body`` entries exceed
    ``BODY_PREVIEW_LIMIT`` characters. It is cut on a sentence boundary only
    (never mid-sentence), so callers show it in place of the full summaries
    with an accessible control that reveals the untouched ``summaries`` text.
    """

    title: str
    categories: tuple[str, ...]
    warning_titles: tuple[str, ...]
    common_ingredient_disclaimer: str | None
    summaries: tuple[str, ...]
    body: tuple[str, ...]
    body_preview: str | None
    actions: tuple[str, ...]
    source_ids: tuple[str, ...]


def _normalized_key(text: str) -> str:
    return " ".join(unescape(text).split())


def _contains_guidance_key(longer: str, shorter: str) -> bool:
    if shorter not in longer:
        return False
    escaped = re.escape(shorter)
    return re.search(rf"(?<![0-9A-Za-z가-힣]){escaped}(?![0-9A-Za-z가-힣])", longer) is not None


def _guidance_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _GUIDANCE_WORD_RE.findall(unescape(text).casefold()):
        for suffix in _GUIDANCE_PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 1:
                token = token[: -len(suffix)]
                break
        if token not in _GUIDANCE_STOP_WORDS and token:
            tokens.add(token)
    return tokens


def _near_duplicate_guidance(left: str, right: str) -> bool:
    """Recognize only high-confidence paraphrases with retained content.

    Boilerplate words are removed only for comparison. Every remaining token
    from the shorter entry must occur in the longer one, and negation/numeric
    qualifiers must agree. This leaves uncertain complementary wording in the
    body without relying on a vocabulary limited to known conditions.
    """
    left_tokens = _guidance_tokens(left)
    right_tokens = _guidance_tokens(right)
    if min(len(left_tokens), len(right_tokens)) < 2:
        return False
    if set(_NEGATION_RE.findall(left)) != set(_NEGATION_RE.findall(right)):
        return False
    if {match.casefold() for match in _NUMBER_RE.findall(left)} != {
        match.casefold() for match in _NUMBER_RE.findall(right)
    }:
        return False
    return left_tokens <= right_tokens or right_tokens <= left_tokens


def _merge_guidance_body(entries: Iterable[tuple[str, bool]]) -> tuple[str, ...]:
    """Merge summary/action entries while retaining distinct medical details."""
    merged: list[str] = []
    keys: list[str] = []
    for raw_text, is_action in entries:
        text = raw_text.strip()
        key = _normalized_key(text).casefold()
        if not key:
            continue
        duplicate_index: int | None = None
        for index, existing_key in enumerate(keys):
            if (
                key == existing_key
                or _contains_guidance_key(existing_key, key)
                or _contains_guidance_key(key, existing_key)
                or _near_duplicate_guidance(merged[index], text)
            ):
                duplicate_index = index
                break
        if duplicate_index is None:
            merged.append(text)
            keys.append(key)
            continue
        existing = merged[duplicate_index]
        # A same-fact action is generally the fuller, actionable sentence;
        # replace only when it has at least as many meaningful tokens.
        existing_tokens = _guidance_tokens(existing)
        new_tokens = _guidance_tokens(text)
        action_is_clearer = (
            is_action and bool(_ACTION_SIGNAL_RE.search(text)) and not bool(_ACTION_SIGNAL_RE.search(existing))
        )
        if new_tokens >= existing_tokens and (
            action_is_clearer or (is_action and new_tokens == existing_tokens) or len(text) >= len(existing)
        ):
            merged[duplicate_index] = text
            keys[duplicate_index] = key
    return tuple(merged)


def _guidance_sentences(paragraphs: Iterable[str]) -> list[str]:
    """Split the body into the units a preview may end on.

    A paragraph break and a line break are both sentence boundaries, so a
    body whose paragraphs carry no closing punctuation still yields a bounded
    preview instead of collapsing into one unsplittable run.
    """
    sentences: list[str] = []
    for paragraph in paragraphs:
        for line in (paragraph or "").splitlines():
            for sentence in _SENTENCE_BOUNDARY_RE.split(line):
                sentence = sentence.strip()
                if sentence:
                    sentences.append(sentence)
    return sentences


def summarize_guidance_body(paragraphs: Iterable[str], *, limit: int = BODY_PREVIEW_LIMIT) -> str | None:
    """Return a sentence-safe preview of joined paragraphs, or ``None`` if they already fit.

    The cut only ever falls between sentences, so the preview is never a
    fragment a reader could misread as the whole warning. When even the first
    sentence alone exceeds ``limit`` the whole sentence is kept, so the preview
    can exceed ``limit`` in that one case: an over-long medical sentence is
    shown whole rather than truncated into a misleading half-warning.
    """
    sentences = _guidance_sentences(paragraphs)
    joined = " ".join(sentences)
    if len(joined) <= limit:
        return None
    preview = ""
    for sentence in sentences:
        candidate = f"{preview} {sentence}".strip() if preview else sentence
        if len(candidate) > limit and preview:
            break
        preview = candidate
        if len(preview) >= limit:
            break
    return preview or joined


def _value(item: object, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _item_type(item: object) -> str:
    value = _value(item, "item_type", "")
    value = getattr(value, "value", value)
    return str(value).casefold()


def _related_item_ids(card: object) -> tuple[int, ...]:
    values = _value(card, "related_item_ids", []) or []
    return tuple(sorted({int(value) for value in values if not isinstance(value, bool)}))


def _rag_item_type(card: object) -> str:
    match = _RAG_ITEM_TYPE_RE.match(str(_value(card, "id", "")))
    return match.group(1).casefold() if match else ""


def _declared_item_type(card: object, related_item_ids: tuple[int, ...]) -> str:
    """Return only a type explicitly carried by the card's stable ID.

    Fixed medication and supplement cards are authoritative even for a
    multi-product card.  A RAG type tag is only an owner hint for singleton
    cards: applying it to a mixed multi-ID card would incorrectly hide the
    other registration type.
    """
    card_id = str(_value(card, "id", ""))
    if _MEDICATION_ONLY_CARD_RE.match(card_id):
        return "medication"
    if _SUPPLEMENT_ONLY_CARD_RE.match(card_id):
        return "supplement"
    return _rag_item_type(card) if len(related_item_ids) == 1 else ""


def _singleton_type_hint(related_item_ids: tuple[int, ...], items_by_id: dict[int, list[object]], card: object) -> str:
    """Use an explicit card type first; only infer an unambiguous singleton."""
    declared_type = _declared_item_type(card, related_item_ids)
    if declared_type:
        return declared_type
    if len(related_item_ids) != 1:
        return ""
    matching_types = {
        _item_type(item)
        for item in items_by_id.get(related_item_ids[0], [])
        if _item_type(item) in _REGISTERED_ITEM_TYPES
    }
    if len(matching_types) == 1:
        return next(iter(matching_types))
    # Medication and supplement tables can both contain the same numeric ID.
    # An untyped collision is intentionally left as a common, non-product box.
    return ""


def _group_key(related_item_ids: tuple[int, ...], type_hint: str) -> str:
    return json.dumps(
        {"rag_type_hint": type_hint, "related_item_ids": related_item_ids},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _group_title(
    related_item_ids: tuple[int, ...],
    type_hint: str,
    current_stack: list[object],
) -> str:
    names: list[str] = []
    related_id_set = set(related_item_ids)
    if not related_id_set:
        return "공통 안내"

    candidates_by_id: dict[int, list[object]] = {item_id: [] for item_id in related_id_set}
    for item in current_stack:
        item_id = _value(item, "item_id")
        if item_id not in related_id_set:
            continue
        if type_hint and _item_type(item) != type_hint:
            continue
        candidates_by_id[item_id].append(item)

    # Without a declared type, one numeric ID that resolves to multiple (or no)
    # registrations is genuinely ambiguous.  Never concatenate both names.
    if not type_hint and any(len(candidates) != 1 for candidates in candidates_by_id.values()):
        return "공통 안내"

    for item in current_stack:
        if _value(item, "item_id") not in related_id_set:
            continue
        if type_hint and _item_type(item) != type_hint:
            continue
        product_name = str(_value(item, "product_name", "")).strip()
        if product_name and product_name not in names:
            names.append(product_name)
    return " · ".join(names) if names else "공통 안내"


def product_guidance_display(group: GuidanceProductGroup) -> GuidanceProductDisplay:
    """Consolidate one product group's display fields without dropping cards.

    This is the shared renderer contract: callers show one product container,
    category labels once, the optional common disclaimer, one merged body, and
    one evidence union. Legacy ``summaries`` and ``actions`` remain available
    for saved-report callers, but renderers should use ``body``.
    """
    categories: list[str] = []
    warning_titles: list[str] = []
    summaries: list[str] = []
    actions: list[str] = []
    source_ids: list[str] = []
    has_common_disclaimer = False
    title_keys: set[str] = set()
    summary_keys: set[str] = set()
    action_keys: set[str] = set()
    body_entries: list[tuple[str, bool]] = []

    for card in group.cards:
        category = str(_value(card, "category", "")).strip()
        if category and category not in categories:
            categories.append(category)
        warning_title = str(_value(card, "title", "")).strip()
        title_key = _normalized_key(warning_title)
        if title_key and title_key not in title_keys:
            title_keys.add(title_key)
            warning_titles.append(warning_title)

        summary = str(_value(card, "summary", "")).strip()
        if summary.startswith(COMMON_INGREDIENT_DISCLAIMER):
            has_common_disclaimer = True
            summary = summary.removeprefix(COMMON_INGREDIENT_DISCLAIMER).lstrip()
        summary_key = _normalized_key(summary)
        if summary_key and summary_key not in summary_keys:
            summary_keys.add(summary_key)
            summaries.append(summary)
            body_entries.append((summary, False))

        action = str(_value(card, "action", "")).strip()
        action_key = _normalized_key(action)
        if action_key and action_key not in action_keys:
            action_keys.add(action_key)
            actions.append(action)
            body_entries.append((action, True))
        for source_id in _value(card, "source_ids", []) or []:
            source_id = str(source_id)
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)

    merged_body = _merge_guidance_body(body_entries)
    return GuidanceProductDisplay(
        title=group.title,
        categories=tuple(categories),
        warning_titles=tuple(warning_titles),
        common_ingredient_disclaimer=COMMON_INGREDIENT_DISCLAIMER if has_common_disclaimer else None,
        summaries=tuple(summaries),
        body=merged_body,
        body_preview=summarize_guidance_body(merged_body),
        actions=tuple(actions),
        source_ids=tuple(source_ids),
    )


def group_lifestyle_guidance_cards(
    cards: Iterable[object],
    current_stack: Iterable[object],
) -> list[GuidanceProductGroup]:
    """Keep product groups contiguous while leaving each original card untouched."""
    stack = list(current_stack)
    items_by_id: dict[int, list[object]] = {}
    for item in stack:
        item_id = _value(item, "item_id")
        if isinstance(item_id, bool):
            continue
        try:
            items_by_id.setdefault(int(item_id), []).append(item)
        except (TypeError, ValueError):
            continue

    groups: list[GuidanceProductGroup] = []
    indexes: dict[str, int] = {}
    for card in cards:
        related_item_ids = _related_item_ids(card)
        type_hint = _singleton_type_hint(related_item_ids, items_by_id, card)
        key = _group_key(related_item_ids, type_hint)
        existing = indexes.get(key)
        if existing is None:
            indexes[key] = len(groups)
            groups.append(
                GuidanceProductGroup(
                    key=key,
                    title=_group_title(related_item_ids, type_hint, stack),
                    cards=[card],
                )
            )
        else:
            groups[existing].cards.append(card)
    return groups


@dataclass(frozen=True)
class GuidanceEvidenceGroup:
    """One cited source with every distinct quote drawn from it, shown once."""

    title: str
    organization: str | None
    url: str | None
    quotes: tuple[str, ...]


def group_guidance_evidence(sources: Iterable[object]) -> list[GuidanceEvidenceGroup]:
    """Group a product group's evidence by source so a title/link is shown once.

    A source cited for two different quotes (each stored as its own
    ``CardSource`` id) must not repeat its heading and link per quote. Grouping
    is keyed on (title, organization, url): distinct sources, including two
    different URLs from the same organization, stay separate.
    """
    groups: list[GuidanceEvidenceGroup] = []
    indexes: dict[tuple[str, str, str], int] = {}
    for source in sources:
        quote = str(_value(source, "quote") or "").strip()
        if not quote:
            continue
        title = str(_value(source, "title") or "").strip()
        organization = _value(source, "organization")
        organization = str(organization).strip() or None if organization else None
        # Only a pre-validated safe URL is ever linked. A caller that has not
        # computed one (no "safe_url" key) yields no link, never a raw URL.
        url = _value(source, "safe_url", None)
        url = str(url).strip() or None if url else None
        key = (title, organization or "", url or "")
        existing = indexes.get(key)
        if existing is None:
            indexes[key] = len(groups)
            groups.append(GuidanceEvidenceGroup(title=title, organization=organization, url=url, quotes=(quote,)))
        elif quote not in groups[existing].quotes:
            groups[existing] = GuidanceEvidenceGroup(
                title=groups[existing].title,
                organization=groups[existing].organization,
                url=groups[existing].url,
                quotes=(*groups[existing].quotes, quote),
            )
    return groups
