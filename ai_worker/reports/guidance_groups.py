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
COMMON_INGREDIENT_DISCLAIMER = "정확한 제품은 미확정이며, 확인된 성분 공통 안내입니다."


@dataclass
class GuidanceProductGroup:
    """A display group whose cards all refer to the same registered products."""

    key: str
    title: str
    cards: list[Any]


@dataclass(frozen=True)
class GuidanceProductDisplay:
    """One compact, product-level projection for every lifestyle export.

    ``warning_titles`` preserves every card in order, while ``categories``
    preserves first-seen exact values.  The
    summaries omit the exact common-ingredient disclaimer, which is instead
    emitted once through ``common_ingredient_disclaimer``.  Actions and source
    IDs are stable first-seen unions across every card in the product group.
    """

    title: str
    categories: tuple[str, ...]
    warning_titles: tuple[str, ...]
    common_ingredient_disclaimer: str | None
    summaries: tuple[str, ...]
    actions: tuple[str, ...]
    source_ids: tuple[str, ...]


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
    category labels once, all warning titles first, then the optional common
    disclaimer, summary paragraphs, distinct actions, and one evidence union.
    """
    categories: list[str] = []
    warning_titles: list[str] = []
    summaries: list[str] = []
    actions: list[str] = []
    source_ids: list[str] = []
    has_common_disclaimer = False
    action_keys: set[str] = set()

    for card in group.cards:
        category = str(_value(card, "category", "")).strip()
        if category and category not in categories:
            categories.append(category)
        warning_title = str(_value(card, "title", "")).strip()
        if warning_title:
            warning_titles.append(warning_title)

        summary = str(_value(card, "summary", "")).strip()
        if summary.startswith(COMMON_INGREDIENT_DISCLAIMER):
            has_common_disclaimer = True
            summary = summary.removeprefix(COMMON_INGREDIENT_DISCLAIMER).lstrip()
        if summary:
            summaries.append(summary)

        action = str(_value(card, "action", "")).strip()
        action_key = " ".join(unescape(action).split())
        if action_key and action_key not in action_keys:
            action_keys.add(action_key)
            actions.append(action)
        for source_id in _value(card, "source_ids", []) or []:
            source_id = str(source_id)
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)

    return GuidanceProductDisplay(
        title=group.title,
        categories=tuple(categories),
        warning_titles=tuple(warning_titles),
        common_ingredient_disclaimer=COMMON_INGREDIENT_DISCLAIMER if has_common_disclaimer else None,
        summaries=tuple(summaries),
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
