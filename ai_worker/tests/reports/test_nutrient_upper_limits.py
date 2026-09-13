from datetime import date
from types import SimpleNamespace

import pytest

from ai_worker.reports.nutrients import build_report_nutrient_data
from ai_worker.schemas.medication_chat import ActiveSupplement
from app.dtos.intake_reports import IntakeReportNutrientTotalResponse


def _product(product_id: int, **amounts: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=product_id,
        name=f"제품 {product_id}",
        basis_qty="1 mg",
        serving_size="1 mg",
        serving_desc="1캡슐",
        daily_freq="1회",
        **amounts,
    )


def _registration(product_id: int) -> ActiveSupplement:
    return ActiveSupplement(
        registration_id=product_id,
        supplement_nutrient_id=product_id,
        name=f"제품 {product_id}",
        dose_amount="1",
        dose_unit="캡슐",
        start_date=date(2026, 9, 1),
        scheduled_slots=["MORNING"],
    )


def _standard(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": 1,
        "grp": "여자",
        "age": "30-49세",
        "calcium_mg_rni": "650",
        "calcium_mg_ul": "2500",
        "iron_mg_rni": "12",
        "iron_mg_ul": "45",
        "phosphorus_mg_rni": "700",
        "phosphorus_mg_ul": "3000",
        "vitamin_c_mg_rni": "100",
        "vitamin_c_mg_ul": "2000",
        "vitamin_d_ug_ai": "10",
        "vitamin_d_ug_ul": "100",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _build(*, products: list[SimpleNamespace], standard: object | None = None, profile: object | None = None):
    return build_report_nutrient_data(
        products=products,
        registrations=[_registration(product.id) for product in products],
        profile=profile or SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[] if standard is None else [standard],
        today=date(2026, 9, 12),
    )


def test_report_totals_use_selected_standard_upper_limits_and_serialize_camel_case() -> None:
    """Would fail if UL values do not cross the build→schema→DTO boundary or a different standard is used."""
    data = _build(
        products=[
            _product(1, calcium_mg="200", vitamin_d_ug="20"),
        ],
        standard=_standard(),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert totals["칼슘"].upper_limit_value == "2500"
    assert totals["칼슘"].upper_limit_note is None
    assert totals["비타민 D"].upper_limit_value == "100"
    assert IntakeReportNutrientTotalResponse.from_schema(totals["칼슘"]).model_dump(by_alias=True) == {
        "nutrientName": "칼슘",
        "dailyTotal": "200 mg",
        "includedProductNames": ["제품 1"],
        "calculationStatus": "REGISTERED_SCHEDULE",
        "amount": "200",
        "unit": "mg",
        "referenceValue": "650",
        "referenceKind": "RNI",
        "referencePercent": "30.77",
        "upperLimitValue": "2500",
        "upperLimitNote": None,
        "unknownProductNames": [],
    }


def test_upper_limit_follows_the_profile_selected_standard() -> None:
    """Would fail if upper-limit lookup uses the female sample standard for another demographic profile."""
    data = _build(
        products=[_product(1, calcium_mg="200")],
        profile=SimpleNamespace(birth_date=date(2000, 9, 13), gender="MALE"),
        standard=_standard(grp="남자", age="19-29세", calcium_mg_rni="800", calcium_mg_ul="2000"),
    )

    calcium = next(total for total in data.totals if total.nutrient_name == "칼슘")
    assert calcium.reference_value == "800"
    assert calcium.upper_limit_value == "2000"


def test_unmatched_profile_standard_does_not_expose_an_upper_limit() -> None:
    """Would fail if an upper limit survives when its demographic standard was not selected."""
    data = _build(
        products=[_product(1, calcium_mg="200")],
        standard=_standard(grp="남자", age="30-49세"),
    )

    calcium = next(total for total in data.totals if total.nutrient_name == "칼슘")
    assert calcium.reference_value is None
    assert calcium.upper_limit_value is None
    assert calcium.upper_limit_note == "상한 기준을 확인할 수 없어요."


@pytest.mark.parametrize("upper_limit", [None, "0", "NaN", "Infinity", "600"])
def test_invalid_or_lower_than_reference_upper_limit_is_not_exposed(upper_limit: str | None) -> None:
    """Would fail if missing, nonpositive, nonfinite, or lower-than-reference values become a bar target."""
    data = _build(
        products=[_product(1, calcium_mg="200")],
        standard=_standard(calcium_mg_ul=upper_limit),
    )

    calcium = next(total for total in data.totals if total.nutrient_name == "칼슘")
    assert calcium.upper_limit_value is None
    assert calcium.upper_limit_note == "상한 기준을 확인할 수 없어요."


def test_noncomparable_forms_never_fabricate_upper_limits() -> None:
    """Would fail if vitamin A RAE, retinol, beta-carotene, or niacin is compared to a guessed UL."""
    data = _build(
        products=[
            _product(
                1,
                vitamin_a_ug_rae="700",
                retinol_ug="200",
                beta_carotene_ug="500",
                niacin_mg="8",
                potassium_mg="200",
            )
        ],
        standard=_standard(
            vitamin_a_ug_rae_rni="700",
            vitamin_a_ug_rae_ul="3000",
            potassium_mg_ai="3500",
            potassium_mg_ul="4700",
            niacin_mg_ul="35",
        ),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert totals["비타민 A"].upper_limit_value is None
    assert totals["비타민 A"].upper_limit_note == "성분 형태별 상한 기준이 달라 비교하지 않았어요."
    for name in ("레티놀", "베타카로틴", "나이아신", "칼륨"):
        assert totals[name].upper_limit_value is None
        assert totals[name].upper_limit_note == "상한 기준을 확인할 수 없어요."
