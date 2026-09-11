"""Curated, source-backed food/timing lifestyle cards for v11 nutrient totals.

Facts here are a fixed Korean paraphrase of official primary sources (NIH Office
of Dietary Supplements fact sheets), reviewed 2026-09-11. They are not derived
from the request, the model, or a retrieval corpus: no new facts may be added
without updating this module, and nothing here reads scheduled slots or
product/ingredient names as medical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ai_worker.schemas.intake_report import IntakeReportDraft, IntakeReportItemType, IntakeReportNutrientTotal
from ai_worker.schemas.intake_report_cards import CardSource, LifestyleCard

_MICROGRAM_UNITS = frozenset({"μg", "µg", "mcg", "㎍"})
_SUPPORTED_CALCULATION_STATUSES = frozenset({"LABEL_SCHEDULE", "PARTIAL_LABEL_SCHEDULE"})

_FOOD_ACTION = (
    "이 정보는 제품 라벨의 하루 섭취 안내량 기준이며 실제 식사나 복용량이 아닙니다. "
    "식사와 라벨 함량을 확인할 수 없는 제품은 포함하지 않았고, 이 정보만으로 부족 여부를 "
    "진단하거나 섭취량을 늘리도록 권하지 않습니다. 예시로 든 식품이 있다고 해서 그 식품 섭취를 "
    "늘리라는 뜻은 아니며, 나이·알레르기·식이 제한과 복용 중인 약의 음식 관련 주의사항을 함께 "
    "확인하세요. 궁금한 점은 의사·약사에게 확인하세요."
)
_FOOD_CATEGORY = "영양소 식품 안내"
_TIMING_CATEGORY = "복용 시점"


@dataclass(frozen=True)
class _SourceFact:
    source_id: str
    title: str
    organization: str
    url: str
    evidence_level: str = "PUBLIC_GUIDE"

    def to_card_source(self) -> CardSource:
        return CardSource(
            id=self.source_id,
            title=self.title,
            organization=self.organization,
            url=self.url,
            evidence_level=self.evidence_level,
        )


_ODS = "National Institutes of Health, Office of Dietary Supplements (NIH ODS)"

_CALCIUM_SOURCE = _SourceFact(
    source_id="source:ods-calcium",
    title="Calcium — Health Professional Fact Sheet",
    organization=_ODS,
    url="https://ods.od.nih.gov/factsheets/Calcium-HealthProfessional/",
)
_IRON_FOOD_SOURCE = _SourceFact(
    source_id="source:ods-iron-food",
    title="Iron — Health Professional Fact Sheet (Sources of Iron section)",
    organization=_ODS,
    url="https://ods.od.nih.gov/factsheets/Iron-HealthProfessional/",
)
_VITAMIN_C_FOOD_SOURCE = _SourceFact(
    source_id="source:ods-vitaminc-food",
    title="Vitamin C — Consumer Fact Sheet (What foods provide vitamin C? section)",
    organization=_ODS,
    url="https://ods.od.nih.gov/factsheets/VitaminC-Consumer/",
)
_VITAMIN_D_SOURCE = _SourceFact(
    source_id="source:ods-vitamind-food",
    title="Vitamin D — Consumer Fact Sheet",
    organization=_ODS,
    url="https://ods.od.nih.gov/factsheets/VitaminD-Consumer/",
)


@dataclass(frozen=True)
class _FoodSpec:
    nutrient_name: str
    expected_units: frozenset[str]
    source: _SourceFact
    title: str
    summary: str
    card_id: str


_FOOD_SPECS: tuple[_FoodSpec, ...] = (
    _FoodSpec(
        nutrient_name="칼슘",
        expected_units=frozenset({"mg"}),
        source=_CALCIUM_SOURCE,
        title="칼슘이 들어있는 식품",
        summary=(
            "우유·요거트·치즈 같은 유제품과, 칼슘으로 응고했거나 칼슘으로 강화된 두부에 칼슘이 "
            "들어 있어요. (모든 두부가 아니라 응고·강화 방식에 따라 다르니 제품 표시를 확인하세요)"
        ),
        card_id="food:calcium",
    ),
    _FoodSpec(
        nutrient_name="철",
        expected_units=frozenset({"mg"}),
        source=_IRON_FOOD_SOURCE,
        title="철분이 들어있는 식품",
        summary="살코기 등 육류, 콩류, 견과류에 철분이 들어 있어요.",
        card_id="food:iron",
    ),
    _FoodSpec(
        nutrient_name="비타민 C",
        expected_units=frozenset({"mg"}),
        source=_VITAMIN_C_FOOD_SOURCE,
        title="비타민 C가 들어있는 식품",
        summary="빨간색·초록색 피망, 브로콜리, 딸기, 키위 같은 식품에 비타민 C가 들어 있어요.",
        card_id="food:vitamin-c",
    ),
    _FoodSpec(
        nutrient_name="비타민 D",
        expected_units=_MICROGRAM_UNITS,
        source=_VITAMIN_D_SOURCE,
        title="비타민 D가 들어있는 식품",
        summary=(
            "연어·고등어 같은 생선과 달걀노른자(소량 포함)에 비타민 D가 들어 있고, 비타민 D가 "
            "강화된 식품도 있어요. 강화 여부는 제품 표시로 확인하세요."
        ),
        card_id="food:vitamin-d",
    ),
)


@dataclass(frozen=True)
class _TimingSpec:
    nutrient_name: str
    expected_units: frozenset[str]
    source: _SourceFact
    title: str
    summary: str
    action: str
    card_id: str


_TIMING_SPECS: tuple[_TimingSpec, ...] = (
    _TimingSpec(
        nutrient_name="비타민 D",
        expected_units=_MICROGRAM_UNITS,
        source=_VITAMIN_D_SOURCE,
        title="비타민 D는 식사와 함께 먹는 게 흡수에 유리해요",
        summary="비타민 D는 지방이 포함된 식사나 간식과 함께 섭취할 때 흡수가 더 잘 되는 것으로 알려져 있어요.",
        action=(
            "복용 시간(알람)을 임의로 바꾸지 말고, 제품 라벨과 처방·복약 지시를 우선하세요. "
            "다른 약과의 복용 간격은 의사·약사와 상의하세요."
        ),
        card_id="timing:vitamin-d",
    ),
    _TimingSpec(
        nutrient_name="칼슘",
        expected_units=frozenset({"mg"}),
        source=_CALCIUM_SOURCE,
        title="칼슘 보충제는 성분 형태에 따라 복용 시점이 다를 수 있어요",
        summary=(
            "탄산칼슘(calcium carbonate)은 음식과 함께 먹을 때 흡수에 유리하고, 구연산칼슘"
            "(calcium citrate)은 음식 유무와 관계없이 먹을 수 있다고 알려져 있어요."
        ),
        action=(
            "내가 먹는 칼슘 제품이 탄산칼슘인지 구연산칼슘인지는 제품 라벨의 원료명에서 직접 "
            "확인하세요. 확실하지 않으면 약사에게 물어보고, 다른 약과의 복용 간격도 함께 "
            "확인하세요. 복용 시간(알람)을 임의로 바꾸지 마세요."
        ),
        card_id="timing:calcium",
    ),
)


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _food_card(spec: _FoodSpec, total: IntakeReportNutrientTotal) -> LifestyleCard | None:
    if total.calculation_status not in _SUPPORTED_CALCULATION_STATUSES:
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
        category=_FOOD_CATEGORY,
        title=spec.title,
        summary=(
            f"등록한 영양제에서 확인된 {spec.nutrient_name} 함량이 비교 기준보다 낮아, "
            f"식단에서 참고할 수 있는 식품을 안내해요. {spec.summary}"
        ),
        action=_FOOD_ACTION,
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


def _timing_card(spec: _TimingSpec, total: IntakeReportNutrientTotal, draft: IntakeReportDraft) -> LifestyleCard | None:
    if total.calculation_status not in _SUPPORTED_CALCULATION_STATUSES:
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
        category=_TIMING_CATEGORY,
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


def build_lifestyle_guidance_cards(draft: IntakeReportDraft) -> tuple[list[LifestyleCard], list[CardSource]]:
    """Return only the source-backed lifestyle cards whose trigger conditions hold."""
    totals_by_name = _deduplicated_totals_by_name(draft.nutrient_totals)
    cards: list[LifestyleCard] = []
    sources_by_id: dict[str, CardSource] = {}

    for food_spec in _FOOD_SPECS:
        total = totals_by_name.get(food_spec.nutrient_name)
        if total is None:
            continue
        if card := _food_card(food_spec, total):
            cards.append(card)
            sources_by_id[food_spec.source.source_id] = food_spec.source.to_card_source()

    for timing_spec in _TIMING_SPECS:
        total = totals_by_name.get(timing_spec.nutrient_name)
        if total is None:
            continue
        if card := _timing_card(timing_spec, total, draft):
            cards.append(card)
            sources_by_id[timing_spec.source.source_id] = timing_spec.source.to_card_source()

    return cards, list(sources_by_id.values())
