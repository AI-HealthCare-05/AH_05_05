"""Curated, source-backed food/timing lifestyle cards for v11 nutrient totals.

Reviewed facts live in ``data/v11_lifestyle_guidance.json``. Adding guidance
requires a reviewed registry entry, never a nutrient-specific code branch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import cache
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from ai_worker.schemas.intake_report import IntakeReportDraft, IntakeReportItemType, IntakeReportNutrientTotal
from ai_worker.schemas.intake_report_cards import CardSource, LifestyleCard

# The only calculation statuses whose nutrient amount is a real computed total.
# Shared so every caller uses one definition of "this total is comparable".
SUPPORTED_CALCULATION_STATUSES = frozenset(
    {"LABEL_SCHEDULE", "PARTIAL_LABEL_SCHEDULE", "REGISTERED_SCHEDULE", "PARTIAL_REGISTERED_SCHEDULE"}
)
_REGISTRY_RESOURCE = "data/v11_lifestyle_guidance.json"


@dataclass(frozen=True)
class _SourceFact:
    source_id: str
    title: str
    organization: str
    url: str
    evidence_level: str

    def to_card_source(self) -> CardSource:
        return CardSource(
            id=self.source_id,
            title=self.title,
            organization=self.organization,
            url=self.url,
            evidence_level=self.evidence_level,
        )


@dataclass(frozen=True)
class _FoodSpec:
    nutrient_name: str
    expected_units: frozenset[str]
    source: _SourceFact
    title: str
    summary: str
    card_id: str


@dataclass(frozen=True)
class _TimingSpec:
    nutrient_name: str
    expected_units: frozenset[str]
    source: _SourceFact
    title: str
    summary: str
    action: str
    card_id: str


@dataclass(frozen=True)
class _LifestyleGuidanceRegistry:
    food_action: str
    food_category: str
    timing_category: str
    foods: tuple[_FoodSpec, ...]
    timings: tuple[_TimingSpec, ...]


def _required_mapping(value: object, *, path: str, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{path} must be an object")
    actual_keys = frozenset(value)
    missing = keys - actual_keys
    if missing:
        raise ValueError(f"{path}.{sorted(missing)[0]} is required")
    if actual_keys != keys:
        raise ValueError(f"{path} must contain exactly {sorted(keys)!r}")
    return value


def _required_string(value: object, *, path: str) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise ValueError(f"{path} must be a non-empty trimmed string")
    return value


def _expected_units(value: object, *, path: str) -> frozenset[str]:
    if type(value) is not list or not value:
        raise ValueError(f"{path} must be a non-empty list")
    units = [_required_string(unit, path=f"{path}[{index}]") for index, unit in enumerate(value)]
    if len(set(units)) != len(units):
        raise ValueError(f"{path} must not contain duplicates")
    return frozenset(units)


def _source_fact(value: object, *, path: str) -> _SourceFact:
    source = _required_mapping(
        value,
        path=path,
        keys=frozenset({"id", "title", "organization", "url", "evidence_level"}),
    )
    url = _required_string(source["url"], path=f"{path}.url")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{path}.url must be an absolute https URL")
    return _SourceFact(
        source_id=_required_string(source["id"], path=f"{path}.id"),
        title=_required_string(source["title"], path=f"{path}.title"),
        organization=_required_string(source["organization"], path=f"{path}.organization"),
        url=url,
        evidence_level=_required_string(source["evidence_level"], path=f"{path}.evidence_level"),
    )


def _food_spec(value: object, *, path: str) -> _FoodSpec:
    spec = _required_mapping(
        value,
        path=path,
        keys=frozenset({"nutrient_name", "expected_units", "source", "title", "summary", "card_id"}),
    )
    return _FoodSpec(
        nutrient_name=_required_string(spec["nutrient_name"], path=f"{path}.nutrient_name"),
        expected_units=_expected_units(spec["expected_units"], path=f"{path}.expected_units"),
        source=_source_fact(spec["source"], path=f"{path}.source"),
        title=_required_string(spec["title"], path=f"{path}.title"),
        summary=_required_string(spec["summary"], path=f"{path}.summary"),
        card_id=_required_string(spec["card_id"], path=f"{path}.card_id"),
    )


def _timing_spec(value: object, *, path: str) -> _TimingSpec:
    spec = _required_mapping(
        value,
        path=path,
        keys=frozenset({"nutrient_name", "expected_units", "source", "title", "summary", "action", "card_id"}),
    )
    return _TimingSpec(
        nutrient_name=_required_string(spec["nutrient_name"], path=f"{path}.nutrient_name"),
        expected_units=_expected_units(spec["expected_units"], path=f"{path}.expected_units"),
        source=_source_fact(spec["source"], path=f"{path}.source"),
        title=_required_string(spec["title"], path=f"{path}.title"),
        summary=_required_string(spec["summary"], path=f"{path}.summary"),
        action=_required_string(spec["action"], path=f"{path}.action"),
        card_id=_required_string(spec["card_id"], path=f"{path}.card_id"),
    )


def _validated_specs(value: object, *, path: str, parse: Any) -> tuple[Any, ...]:
    if type(value) is not list:
        raise ValueError(f"{path} must be a list")
    return tuple(parse(entry, path=f"{path}[{index}]") for index, entry in enumerate(value))


def _validate_unique_registry_ids(foods: tuple[_FoodSpec, ...], timings: tuple[_TimingSpec, ...]) -> None:
    specs: tuple[_FoodSpec | _TimingSpec, ...] = (*foods, *timings)
    card_ids = [spec.card_id for spec in specs]
    if len(set(card_ids)) != len(card_ids):
        raise ValueError("duplicate card_id in lifestyle guidance registry")

    sources_by_id: dict[str, _SourceFact] = {}
    for spec in specs:
        known = sources_by_id.setdefault(spec.source.source_id, spec.source)
        if known != spec.source:
            raise ValueError(f"source id {spec.source.source_id!r} has inconsistent source data")


def _parse_lifestyle_guidance_registry(value: object) -> _LifestyleGuidanceRegistry:
    registry = _required_mapping(
        value,
        path="registry",
        keys=frozenset({"food_action", "food_category", "timing_category", "foods", "timings"}),
    )
    foods = _validated_specs(registry["foods"], path="registry.foods", parse=_food_spec)
    timings = _validated_specs(registry["timings"], path="registry.timings", parse=_timing_spec)
    _validate_unique_registry_ids(foods, timings)
    return _LifestyleGuidanceRegistry(
        food_action=_required_string(registry["food_action"], path="registry.food_action"),
        food_category=_required_string(registry["food_category"], path="registry.food_category"),
        timing_category=_required_string(registry["timing_category"], path="registry.timing_category"),
        foods=foods,
        timings=timings,
    )


@cache
def _default_lifestyle_guidance_registry() -> _LifestyleGuidanceRegistry:
    resource = files(__package__).joinpath(_REGISTRY_RESOURCE)
    try:
        raw_registry = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("lifestyle guidance registry could not be loaded") from error
    return _parse_lifestyle_guidance_registry(raw_registry)


def load_lifestyle_guidance_registry(data: object | None = None) -> _LifestyleGuidanceRegistry:
    """Load reviewed guidance, or validate a supplied registry for isolated tests/tools."""
    if data is None:
        return _default_lifestyle_guidance_registry()
    return _parse_lifestyle_guidance_registry(data)


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _food_card(
    spec: _FoodSpec,
    total: IntakeReportNutrientTotal,
    *,
    food_action: str,
    food_category: str,
) -> LifestyleCard | None:
    if total.calculation_status not in SUPPORTED_CALCULATION_STATUSES:
        return None
    if total.reference_kind is None or total.unit not in spec.expected_units:
        return None
    amount = _decimal(total.amount)
    reference = _decimal(total.reference_value)
    if amount is None or amount < 0 or reference is None or reference <= 0:
        return None
    if amount >= reference:
        return None
    return LifestyleCard(
        id=spec.card_id,
        category=food_category,
        title=spec.title,
        summary=(
            f"등록한 영양제에서 확인된 {spec.nutrient_name} 함량이 비교 기준보다 낮아, "
            f"식단에서 참고할 수 있는 식품을 안내해요. {spec.summary}"
        ),
        action=food_action,
        source_ids=[spec.source.source_id],
    )


def _matched_supplement_ids(draft: IntakeReportDraft, product_names: list[str]) -> list[int]:
    ids_by_name: dict[str, list[int]] = {}
    for item in draft.current_stack:
        if item.item_type == IntakeReportItemType.SUPPLEMENT:
            ids_by_name.setdefault(item.product_name, []).append(item.item_id)
    matched: list[int] = []
    for name in dict.fromkeys(product_names):
        candidates = ids_by_name.get(name, [])
        if len(candidates) == 1:
            matched.append(candidates[0])
    return matched


def _timing_card(
    spec: _TimingSpec,
    total: IntakeReportNutrientTotal,
    draft: IntakeReportDraft,
    *,
    timing_category: str,
) -> LifestyleCard | None:
    if total.calculation_status not in SUPPORTED_CALCULATION_STATUSES:
        return None
    if total.unit not in spec.expected_units:
        return None
    amount = _decimal(total.amount)
    if amount is None or amount <= 0:
        return None
    related_item_ids = _matched_supplement_ids(draft, total.included_product_names)
    if not related_item_ids:
        return None
    return LifestyleCard(
        id=spec.card_id,
        category=timing_category,
        title=spec.title,
        summary=spec.summary,
        action=spec.action,
        related_item_ids=related_item_ids,
        source_ids=[spec.source.source_id],
    )


def _deduplicated_totals_by_name(
    totals: list[IntakeReportNutrientTotal],
) -> dict[str, IntakeReportNutrientTotal]:
    """Keep at most one row per nutrient name, conservatively dropping conflicting duplicates."""
    result: dict[str, IntakeReportNutrientTotal] = {}
    conflicting_names: set[str] = set()
    for total in totals:
        name = total.nutrient_name
        if name in conflicting_names:
            continue
        if name in result:
            del result[name]
            conflicting_names.add(name)
            continue
        result[name] = total
    return result


def build_lifestyle_guidance_cards(
    draft: IntakeReportDraft,
    *,
    registry: _LifestyleGuidanceRegistry | None = None,
) -> tuple[list[LifestyleCard], list[CardSource]]:
    """Return only the source-backed lifestyle cards whose trigger conditions hold."""
    registry = registry if registry is not None else load_lifestyle_guidance_registry()
    totals_by_name = _deduplicated_totals_by_name(draft.nutrient_totals)
    cards: list[LifestyleCard] = []
    sources_by_id: dict[str, CardSource] = {}

    for food_spec in registry.foods:
        total = totals_by_name.get(food_spec.nutrient_name)
        if total is None:
            continue
        if card := _food_card(
            food_spec,
            total,
            food_action=registry.food_action,
            food_category=registry.food_category,
        ):
            cards.append(card)
            sources_by_id[food_spec.source.source_id] = food_spec.source.to_card_source()

    for timing_spec in registry.timings:
        total = totals_by_name.get(timing_spec.nutrient_name)
        if total is None:
            continue
        if card := _timing_card(timing_spec, total, draft, timing_category=registry.timing_category):
            cards.append(card)
            sources_by_id[timing_spec.source.source_id] = timing_spec.source.to_card_source()

    return cards, list(sources_by_id.values())
