"""Product-label nutrients scaled to registered doses and daily time slots.

The registered plan is not evidence that a user actually took the products.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from ai_worker.schemas.intake_report import IntakeReportNutrientTotal
from ai_worker.schemas.medication_chat import ActiveIntakeContext, ActiveSupplement
from app.models.supplement_nutrients import NutrientStandard, SupplementNutrient
from app.models.users import User
from app.services.nutrient_standards import resolve_age_range


@dataclass(frozen=True)
class ReportNutrientData:
    totals: list[IntakeReportNutrientTotal]
    profile_label: str
    basis_note: str
    product_labels: dict[int, str]
    product_ingredient_summaries: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _NutrientSpec:
    field: str
    name: str
    unit: str
    reference_field: str | None
    upper_limit_field: str | None


class _ProductLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def basis_qty(self) -> object: ...
    @property
    def serving_size(self) -> object: ...
    @property
    def serving_desc(self) -> object: ...
    @property
    def daily_freq(self) -> object: ...


@dataclass(frozen=True)
class _MissingCatalogProduct:
    id: int
    name: str
    basis_qty: str | None = None
    serving_size: str | None = None
    serving_desc: str | None = None
    daily_freq: str | None = None
    calcium_mg: Decimal | None = None
    iron_mg: Decimal | None = None
    vitamin_c_mg: Decimal | None = None
    vitamin_d_ug: Decimal | None = None


_NUTRIENT_SPECS = (
    _NutrientSpec("fiber_g", "식이섬유", "g", "fiber_g", None),
    _NutrientSpec("calcium_mg", "칼슘", "mg", "calcium_mg", "calcium_mg_ul"),
    _NutrientSpec("iron_mg", "철", "mg", "iron_mg", "iron_mg_ul"),
    _NutrientSpec("phosphorus_mg", "인", "mg", "phosphorus_mg", "phosphorus_mg_ul"),
    _NutrientSpec("potassium_mg", "칼륨", "mg", "potassium_mg", None),
    _NutrientSpec("sodium_mg", "나트륨", "mg", "sodium_mg", None),
    _NutrientSpec("vitamin_a_ug_rae", "비타민 A", "μg RAE", "vitamin_a_ug_rae", None),
    # These source values are intentionally kept separate from vitamin A RAE.
    _NutrientSpec("retinol_ug", "레티놀", "μg", None, None),
    _NutrientSpec("beta_carotene_ug", "베타카로틴", "μg", None, None),
    _NutrientSpec("thiamine_mg", "티아민", "mg", "thiamine_mg", None),
    _NutrientSpec("riboflavin_mg", "리보플라빈", "mg", "riboflavin_mg", None),
    # Catalog mg is not interchangeable with the standard's mg NE without source evidence.
    _NutrientSpec("niacin_mg", "나이아신", "mg", None, None),
    _NutrientSpec("vitamin_c_mg", "비타민 C", "mg", "vitamin_c_mg", "vitamin_c_mg_ul"),
    _NutrientSpec("vitamin_d_ug", "비타민 D", "μg", "vitamin_d_ug", "vitamin_d_ug_ul"),
)
_MASS_RE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(mg|g|μg|µg|ug)\s*")
_SERVING_RE = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*([^\d\s]+)\s*")
_GENDER_GROUPS = {"MALE": "남자", "FEMALE": "여자"}
_GENDER_LABELS = {"남자": "남성", "여자": "여성"}
_BASIS_NOTE = (
    "표시된 값은 영양제 탭에 등록한 1회 복용량과 하루 복용 횟수를 제품 라벨 함량에 반영한 합계입니다. "
    "식사와 함량·복용량·단위를 환산할 수 없는 제품은 제외했습니다."
)
_REFERENCE_NEEDED_LABEL = "비교 기준 확인 필요"
_UPPER_LIMIT_UNAVAILABLE_NOTE = "상한 기준을 확인할 수 없어요."
_VITAMIN_A_UPPER_LIMIT_NOTE = "성분 형태별 상한 기준이 달라 비교하지 않았어요."
_SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")


def _service_today() -> date:
    return datetime.now(_SEOUL_TIMEZONE).date()


def _number(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number >= 0 else None


def _positive_number(value: object) -> Decimal | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _display(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _mass_in_mg(value: object) -> Decimal | None:
    match = _MASS_RE.fullmatch(str(value))
    if match is None:
        return None
    amount = _positive_number(match.group(1))
    if amount is None:
        return None
    return (
        amount
        * {
            "g": Decimal("1000"),
            "mg": Decimal("1"),
            "μg": Decimal(".001"),
            "µg": Decimal(".001"),
            "ug": Decimal(".001"),
        }[match.group(2)]
    )


def _registered_schedule(product: _ProductLike, registration: ActiveSupplement) -> tuple[Decimal, str] | None:
    basis = _mass_in_mg(product.basis_qty)
    serving = _mass_in_mg(product.serving_size)
    serving_match = _SERVING_RE.fullmatch(str(product.serving_desc))
    dose = _positive_number(registration.dose_amount)
    frequency = len(set(registration.scheduled_slots))
    if basis is None or serving is None or serving_match is None or dose is None or frequency == 0:
        return None
    serving_count = _positive_number(serving_match.group(1).replace(",", "."))
    unit = serving_match.group(2)
    if serving_count is None or unit.casefold() != registration.dose_unit.strip().casefold():
        return None
    daily_count = dose * frequency
    label = f"등록한 계획 · 하루 {_display(daily_count)}{unit} (1회 {_display(dose)}{unit} × {frequency}회)"
    return serving / basis / serving_count * daily_count, label


def _profile_age(profile: object | None, *, today: date) -> int | None:
    birth_date = getattr(profile, "birth_date", None)
    if not isinstance(birth_date, date) or birth_date > today:
        return None
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def _profile_target(profile: object | None, *, today: date) -> tuple[str, str] | None:
    age = _profile_age(profile, today=today)
    if age is None:
        return None
    gender = _GENDER_GROUPS.get(str(getattr(profile, "gender", "")))
    if gender is None:
        return None
    return gender, resolve_age_range(age)


def _select_standard(
    standards: Sequence[object],
    target: tuple[str, str] | None,
) -> object | None:
    if target is None:
        return None
    group, age = target
    matches = [
        standard
        for standard in standards
        if getattr(standard, "grp", None) == group and getattr(standard, "age", None) == age
    ]
    return matches[0] if len(matches) == 1 else None


def _reference(
    standard: object | None,
    spec: _NutrientSpec,
) -> tuple[str | None, Literal["RNI", "AI"] | None]:
    if standard is None or spec.reference_field is None:
        return None, None
    rni = _positive_number(getattr(standard, f"{spec.reference_field}_rni", None))
    ai = _positive_number(getattr(standard, f"{spec.reference_field}_ai", None))
    if rni is not None and ai is not None:
        return None, None
    if rni is not None:
        return _display(rni), "RNI"
    if ai is not None:
        return _display(ai), "AI"
    return None, None


def _upper_limit(
    standard: object | None,
    spec: _NutrientSpec,
    reference_value: str | None,
) -> tuple[str | None, str | None]:
    if spec.field == "vitamin_a_ug_rae":
        return None, _VITAMIN_A_UPPER_LIMIT_NOTE
    if standard is None or spec.upper_limit_field is None:
        return None, _UPPER_LIMIT_UNAVAILABLE_NOTE
    upper_limit = _positive_number(getattr(standard, spec.upper_limit_field, None))
    reference = _positive_number(reference_value)
    if upper_limit is None or (reference is not None and upper_limit < reference):
        return None, _UPPER_LIMIT_UNAVAILABLE_NOTE
    return _display(upper_limit), None


def _percent(amount: Decimal | None, reference: str | None) -> str | None:
    reference_number = _positive_number(reference)
    if amount is None or reference_number is None:
        return None
    return _display((amount / reference_number * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ingredient_summary(product: _ProductLike, factor: Decimal) -> str | None:
    ingredients = []
    for spec in _NUTRIENT_SPECS:
        amount = _positive_number(getattr(product, spec.field, None))
        if amount is not None:
            ingredients.append(f"{spec.name} {_display(amount * factor)}{spec.unit}")
    return " · ".join(ingredients) or None


def build_report_nutrient_data(
    *,
    products: Sequence[_ProductLike],
    registrations: list[ActiveSupplement],
    profile: object | None,
    standards: Sequence[object],
    today: date,
) -> ReportNutrientData:
    """Build totals from public catalog rows and a real user's demographic profile."""
    target = _profile_target(profile, today=today)
    standard = _select_standard(standards, target)
    profile_label = (
        f"{_profile_age(profile, today=today)}세 {_GENDER_LABELS[target[0]]}"
        if standard is not None and target is not None
        else _REFERENCE_NEEDED_LABEL
    )
    catalog_by_id = {product.id: product for product in products}
    registered_products = [
        (
            registration,
            catalog_by_id.get(
                registration.supplement_nutrient_id,
                _MissingCatalogProduct(id=registration.supplement_nutrient_id, name=registration.name),
            ),
        )
        for registration in registrations
    ]
    product_schedules = {
        registration.registration_id: _registered_schedule(product, registration)
        for registration, product in registered_products
    }
    product_labels = {
        registration_id: schedule[1] for registration_id, schedule in product_schedules.items() if schedule is not None
    }
    product_ingredient_summaries = {
        registration.registration_id: summary
        for registration, product in registered_products
        if (schedule := product_schedules[registration.registration_id]) is not None
        and (summary := _ingredient_summary(product, schedule[0])) is not None
    }

    observed_specs = [
        spec
        for spec in _NUTRIENT_SPECS
        if any(_positive_number(getattr(product, spec.field, None)) is not None for _, product in registered_products)
    ]

    totals: list[IntakeReportNutrientTotal] = []
    for spec in observed_specs:
        contributions: list[tuple[str, Decimal]] = []
        unknown_product_names: list[str] = []
        for registration, product in registered_products:
            schedule = product_schedules[registration.registration_id]
            amount = _number(getattr(product, spec.field, None))
            if amount == 0:
                continue
            if amount is None or schedule is None:
                unknown_product_names.append(product.name)
                continue
            contributions.append((product.name, amount * schedule[0]))

        total = sum((contribution for _, contribution in contributions), Decimal(0)) if contributions else None
        reference_value, reference_kind = _reference(standard, spec)
        upper_limit_value, upper_limit_note = _upper_limit(standard, spec, reference_value)
        totals.append(
            IntakeReportNutrientTotal(
                nutrient_name=spec.name,
                daily_total=f"{_display(total)} {spec.unit}" if total is not None else "확인 필요",
                included_product_names=[name for name, contribution in contributions if contribution > 0],
                calculation_status=(
                    "UNAVAILABLE"
                    if total is None
                    else ("PARTIAL_REGISTERED_SCHEDULE" if unknown_product_names else "REGISTERED_SCHEDULE")
                ),
                amount=_display(total),
                unit=spec.unit,
                reference_value=reference_value,
                reference_kind=reference_kind,
                reference_percent=_percent(total, reference_value),
                upper_limit_value=upper_limit_value,
                upper_limit_note=upper_limit_note,
                unknown_product_names=unknown_product_names,
            )
        )
    return ReportNutrientData(
        totals=totals,
        profile_label=profile_label,
        basis_note=_BASIS_NOTE,
        product_labels=product_labels,
        product_ingredient_summaries=product_ingredient_summaries,
    )


async def load_report_nutrients(context: ActiveIntakeContext) -> ReportNutrientData:
    """Load the requesting user's profile and only public products named by its active context."""
    today = _service_today()
    profile = await User.filter(id=context.user_id).first()
    product_ids = sorted({supplement.supplement_nutrient_id for supplement in context.supplements})
    catalog_rows = await SupplementNutrient.filter(id__in=product_ids).order_by("id") if product_ids else []
    target = _profile_target(profile, today=today)
    standards = (
        await NutrientStandard.filter(grp=target[0], age=target[1]).order_by("id").limit(2)
        if target is not None
        else []
    )
    return build_report_nutrient_data(
        products=catalog_rows,
        registrations=context.supplements,
        profile=profile,
        standards=standards,
        today=today,
    )
