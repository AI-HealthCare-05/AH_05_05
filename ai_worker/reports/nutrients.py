"""Deterministic product-label nutrient totals for the AI intake report.

The calculations deliberately describe catalog label schedules.  They do not
infer the quantity a user actually consumed.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from ai_worker.schemas.intake_report import IntakeReportNutrientTotal
from ai_worker.schemas.medication_chat import ActiveIntakeContext
from app.models.supplement_nutrients import NutrientStandard, SupplementNutrient
from app.models.users import User
from app.services.nutrient_standards import resolve_age_range


@dataclass(frozen=True)
class ReportNutrientData:
    totals: list[IntakeReportNutrientTotal]
    profile_label: str
    basis_note: str
    product_labels: dict[int, str]


@dataclass(frozen=True)
class _NutrientSpec:
    field: str
    name: str
    unit: str


class _ProductLike(Protocol):
    id: int
    name: str
    basis_qty: object
    serving_size: object
    serving_desc: object
    daily_freq: object


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


_NUTRIENTS = (
    _NutrientSpec("calcium_mg", "칼슘", "mg"),
    _NutrientSpec("iron_mg", "철", "mg"),
    _NutrientSpec("vitamin_c_mg", "비타민 C", "mg"),
    _NutrientSpec("vitamin_d_ug", "비타민 D", "μg"),
)
_MASS_RE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*(mg|g|μg|µg|ug)\s*")
_SERVING_RE = re.compile(r"\s*([1-9]\d*)\s*(정|캡슐|포)\s*")
_FREQUENCY_RE = re.compile(r"\s*([1-9]\d*)\s*회\s*")
_GENDER_GROUPS = {"MALE": "남자", "FEMALE": "여자"}
_BASIS_NOTE = (
    "표시된 값은 제품 라벨의 1일 섭취 안내량 기준이며 실제 섭취량 합계가 아닙니다. "
    "식사와 성분값·섭취 안내량이 누락된 제품은 제외했습니다."
)
_REFERENCE_NEEDED_LABEL = "비교 기준 확인 필요"
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


def _label_schedule(product: _ProductLike) -> tuple[Decimal, str] | None:
    basis = _mass_in_mg(product.basis_qty)
    serving = _mass_in_mg(product.serving_size)
    serving_match = _SERVING_RE.fullmatch(str(product.serving_desc))
    frequency_match = _FREQUENCY_RE.fullmatch(str(product.daily_freq))
    if basis is None or serving is None or serving_match is None or frequency_match is None:
        return None

    daily_count = int(serving_match.group(1)) * int(frequency_match.group(1))
    return serving / basis * Decimal(frequency_match.group(1)), f"{daily_count}{serving_match.group(2)}"


def _profile_target(profile: object | None, *, today: date) -> tuple[str, str] | None:
    if profile is None:
        return None
    birth_date = getattr(profile, "birth_date", None)
    if not isinstance(birth_date, date) or birth_date > today:
        return None
    gender = _GENDER_GROUPS.get(str(getattr(profile, "gender", "")))
    if gender is None:
        return None
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age < 0:
        return None
    return gender, resolve_age_range(age)


def _select_standard(
    standards: list[object],
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
    if standard is None:
        return None, None
    rni = _positive_number(getattr(standard, f"{spec.field}_rni", None))
    ai = _positive_number(getattr(standard, f"{spec.field}_ai", None))
    if rni is not None and ai is not None:
        return None, None
    if rni is not None:
        return _display(rni), "RNI"
    if ai is not None:
        return _display(ai), "AI"
    return None, None


def _percent(amount: Decimal | None, reference: str | None) -> str | None:
    reference_number = _positive_number(reference)
    if amount is None or reference_number is None:
        return None
    return _display((amount / reference_number * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_report_nutrient_data(
    *,
    products: list[_ProductLike],
    profile: object | None,
    standards: list[object],
    today: date,
) -> ReportNutrientData:
    """Build totals from public catalog rows and a real user's demographic profile."""
    target = _profile_target(profile, today=today)
    standard = _select_standard(standards, target)
    profile_label = (
        f"{target[0]} · {target[1]}" if standard is not None and target is not None else _REFERENCE_NEEDED_LABEL
    )
    product_schedules = {product.id: _label_schedule(product) for product in products}
    product_labels = {
        product.id: f"제품 안내량 · 하루 {schedule[1]} (실제 등록량과 별도 비교)"
        for product in products
        if (schedule := product_schedules[product.id]) is not None
    }

    totals: list[IntakeReportNutrientTotal] = []
    for spec in _NUTRIENTS:
        contributions: list[tuple[str, Decimal]] = []
        unknown_product_names: list[str] = []
        for product in products:
            schedule = product_schedules[product.id]
            amount = _number(getattr(product, spec.field, None))
            if schedule is None or amount is None:
                unknown_product_names.append(product.name)
                continue
            contributions.append((product.name, amount * schedule[0]))

        total = sum((contribution for _, contribution in contributions), Decimal(0)) if contributions else None
        reference_value, reference_kind = _reference(standard, spec)
        totals.append(
            IntakeReportNutrientTotal(
                nutrient_name=spec.name,
                daily_total=f"{_display(total)} {spec.unit}" if total is not None else "확인 필요",
                included_product_names=[name for name, contribution in contributions if contribution > 0],
                calculation_status=(
                    "UNAVAILABLE"
                    if total is None
                    else ("PARTIAL_LABEL_SCHEDULE" if unknown_product_names else "LABEL_SCHEDULE")
                ),
                amount=_display(total),
                unit=spec.unit,
                reference_value=reference_value,
                reference_kind=reference_kind,
                reference_percent=_percent(total, reference_value),
                unknown_product_names=unknown_product_names,
            )
        )
    return ReportNutrientData(
        totals=totals,
        profile_label=profile_label,
        basis_note=_BASIS_NOTE,
        product_labels=product_labels,
    )


async def load_report_nutrients(context: ActiveIntakeContext) -> ReportNutrientData:
    """Load the requesting user's profile and only public products named by its active context."""
    today = _service_today()
    profile = await User.filter(id=context.user_id).first()
    product_ids = sorted({supplement.supplement_nutrient_id for supplement in context.supplements})
    catalog_rows = await SupplementNutrient.filter(id__in=product_ids).order_by("id") if product_ids else []
    catalog_by_id = {product.id: product for product in catalog_rows}
    products: list[_ProductLike] = [
        catalog_by_id.get(
            supplement.supplement_nutrient_id,
            _MissingCatalogProduct(id=supplement.supplement_nutrient_id, name=supplement.name),
        )
        for supplement in context.supplements
    ]
    target = _profile_target(profile, today=today)
    standards = (
        await NutrientStandard.filter(grp=target[0], age=target[1]).order_by("id").limit(2)
        if target is not None
        else []
    )
    return build_report_nutrient_data(
        products=products,
        profile=profile,
        standards=standards,
        today=today,
    )
