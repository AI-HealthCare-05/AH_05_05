from datetime import date, datetime
from types import SimpleNamespace

import pytest

from ai_worker.reports import nutrients
from ai_worker.reports.nutrients import build_report_nutrient_data, load_report_nutrients
from ai_worker.schemas.medication_chat import ActiveIntakeContext, ActiveSupplement


def _product(
    product_id: int,
    name: str,
    *,
    calcium: str | None,
    iron: str | None,
    vitamin_c: str | None,
    vitamin_d: str | None,
    basis_qty: str = "1 mg",
    serving_size: str = "1 mg",
    serving_desc: str = "1캡슐",
    daily_freq: str = "1회",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=product_id,
        name=name,
        basis_qty=basis_qty,
        serving_size=serving_size,
        serving_desc=serving_desc,
        daily_freq=daily_freq,
        calcium_mg=calcium,
        iron_mg=iron,
        vitamin_c_mg=vitamin_c,
        vitamin_d_ug=vitamin_d,
    )


def _standard(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": 1,
        "grp": "여자",
        "age": "30-49세",
        "calcium_mg_rni": "650",
        "calcium_mg_ai": None,
        "iron_mg_rni": "12",
        "iron_mg_ai": None,
        "vitamin_c_mg_rni": "100",
        "vitamin_c_mg_ai": None,
        "vitamin_d_ug_rni": None,
        "vitamin_d_ug_ai": "10",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _registration(
    product_id: int,
    *,
    dose: str = "1",
    unit: str = "캡슐",
    slots: list[str] | None = None,
    registration_id: int | None = None,
) -> ActiveSupplement:
    return ActiveSupplement(
        registration_id=registration_id or product_id,
        supplement_nutrient_id=product_id,
        name=f"제품 {product_id}",
        dose_amount=dose,
        dose_unit=unit,
        start_date=date(2026, 9, 1),
        scheduled_slots=["MORNING"] if slots is None else slots,
    )


def test_label_schedule_sums_decimal_catalog_amounts_against_actual_female_profile() -> None:
    """Would fail if a label factor, decimal total, or real-profile reference is changed."""
    products = [
        _product(1, "제품 1", calcium="50", iron="5", vitamin_c="20", vitamin_d="5"),
        _product(
            2,
            "제품 2",
            calcium="25",
            iron="2.5",
            vitamin_c="10",
            vitamin_d="2.5",
            serving_size="2 mg",
        ),
        _product(3, "제품 3", calcium="100", iron="10", vitamin_c="20", vitamin_d="10"),
        _product(4, "제품 4", calcium="100", iron="10", vitamin_c="20", vitamin_d="3"),
    ]

    data = build_report_nutrient_data(
        products=products,
        registrations=[_registration(i) for i in range(1, 5)],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert data.profile_label == "36세 여성"
    assert data.product_labels[2] == "등록한 계획 · 하루 1캡슐 (1회 1캡슐 × 1회)"
    assert totals["칼슘"].amount == "300"
    assert totals["칼슘"].unit == "mg"
    assert totals["칼슘"].reference_value == "650"
    assert totals["칼슘"].reference_kind == "RNI"
    assert totals["칼슘"].reference_percent == "46.15"
    assert totals["철"].amount == "30"
    assert totals["철"].reference_percent == "250"
    assert totals["비타민 C"].amount == "80"
    assert totals["비타민 C"].reference_percent == "80"
    assert totals["비타민 D"].amount == "23"
    assert totals["비타민 D"].reference_kind == "AI"
    assert totals["비타민 D"].reference_percent == "230"
    assert data.basis_note == (
        "표시된 값은 영양제 탭에 등록한 1회 복용량과 하루 복용 횟수를 제품 라벨 함량에 반영한 합계입니다. "
        "식사와 함량·복용량·단위를 환산할 수 없는 제품은 제외했습니다."
    )


def test_missing_profile_or_invalid_label_schedule_keeps_unknown_values_null() -> None:
    """Would fail if an unknown amount/reference is silently rendered as numeric zero."""
    data = build_report_nutrient_data(
        registrations=[_registration(1)],
        products=[
            _product(
                1,
                "안내량 미확인 제품",
                calcium="100",
                iron=None,
                vitamin_c=None,
                vitamin_d=None,
                basis_qty="한 포",
                daily_freq="0회",
            )
        ],
        profile=SimpleNamespace(birth_date=None, gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )

    calcium = next(total for total in data.totals if total.nutrient_name == "칼슘")

    assert data.profile_label == "비교 기준 확인 필요"
    assert data.product_labels == {}
    assert calcium.amount is None
    assert calcium.daily_total == "확인 필요"
    assert calcium.reference_value is None
    assert calcium.reference_percent is None
    assert calcium.unknown_product_names == ["안내량 미확인 제품"]
    assert calcium.calculation_status == "UNAVAILABLE"


def test_other_profile_groups_and_ambiguous_standards_never_use_female_sample_reference() -> None:
    """Would fail if a fixed 30–49 female baseline is used for another user or duplicate standard."""
    product = _product(1, "칼슘", calcium="100", iron="1", vitamin_c="1", vitamin_d="1")
    male = build_report_nutrient_data(
        registrations=[_registration(1)],
        products=[product],
        profile=SimpleNamespace(birth_date=date(2000, 9, 11), gender="MALE"),
        standards=[_standard(grp="남자", age="19-29세", calcium_mg_rni="800")],
        today=date(2026, 9, 10),
    )
    ambiguous = build_report_nutrient_data(
        registrations=[_registration(1)],
        products=[product],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard(id=1), _standard(id=2)],
        today=date(2026, 9, 10),
    )

    male_calcium = next(total for total in male.totals if total.nutrient_name == "칼슘")
    ambiguous_calcium = next(total for total in ambiguous.totals if total.nutrient_name == "칼슘")
    assert male.profile_label == "25세 남성"
    assert male_calcium.reference_value == "800"
    assert male_calcium.reference_percent == "12.5"
    assert ambiguous.profile_label == "비교 기준 확인 필요"
    assert ambiguous_calcium.amount == "100"
    assert ambiguous_calcium.reference_value is None
    assert ambiguous_calcium.reference_percent is None


@pytest.mark.parametrize(
    ("birth_date", "today", "gender", "expected_label"),
    [
        (date(1999, 9, 12), date(2026, 9, 12), "MALE", "27세 남성"),
        (date(1996, 9, 12), date(2026, 9, 11), "MALE", "29세 남성"),
        (date(1996, 9, 12), date(2026, 9, 12), "MALE", "30세 남성"),
        (date(1996, 9, 12), date(2026, 9, 13), "FEMALE", "30세 여성"),
    ],
)
def test_profile_displays_exact_age_without_unrepresented_nutrient_rows(
    birth_date: date, today: date, gender: str, expected_label: str
) -> None:
    data = build_report_nutrient_data(
        products=[],
        registrations=[],
        profile=SimpleNamespace(birth_date=birth_date, gender=gender),
        standards=[
            _standard(grp="남자", age="19-29세", calcium_mg_rni="800"),
            _standard(grp="남자", age="30-49세", calcium_mg_rni="900"),
            _standard(),
        ],
        today=today,
    )
    assert data.profile_label == expected_label
    assert data.totals == []


def test_future_birth_date_does_not_select_a_standard() -> None:
    """Would fail if future dates are coerced to the youngest or sample demographic group."""
    data = build_report_nutrient_data(
        registrations=[_registration(1)],
        products=[_product(1, "제품", calcium="100", iron="1", vitamin_c="1", vitamin_d="1")],
        profile=SimpleNamespace(birth_date=date(2026, 9, 11), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )

    assert data.profile_label == "비교 기준 확인 필요"
    assert next(total for total in data.totals if total.nutrient_name == "칼슘").reference_value is None


def test_zero_label_amounts_do_not_create_totals_or_ingredient_summaries() -> None:
    """Zero-only catalog fields must not appear as nutrients in the report."""
    data = build_report_nutrient_data(
        registrations=[_registration(1), _registration(2)],
        products=[
            _product(1, "칼슘 0 제품", calcium="0", iron="0", vitamin_c="0", vitamin_d="0"),
            _product(2, "또 다른 칼슘 0 제품", calcium="0", iron="0", vitamin_c="0", vitamin_d="0"),
        ],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )

    assert data.totals == []
    assert data.product_ingredient_summaries == {}


@pytest.mark.parametrize(
    ("dose", "slots", "serving_desc", "expected", "expected_percent"),
    [
        ("1", ["MORNING"], "1정", "12", "100"),
        ("2", ["MORNING"], "1정", "24", "200"),
        ("2", ["MORNING", "EVENING"], "1정", "48", "400"),
        ("2", ["MORNING"], "2정", "12", "100"),
        ("0.5", ["MORNING"], "1정", "6", "50"),
    ],
)
def test_report_iron_uses_registered_count_and_slots_not_catalog_frequency(
    dose, slots, serving_desc, expected, expected_percent
) -> None:
    data = build_report_nutrient_data(
        products=[
            _product(
                1,
                "멀티비타민 & 미네랄 24 맥스",
                calcium=None,
                iron="12",
                vitamin_c=None,
                vitamin_d=None,
                serving_desc=serving_desc,
                daily_freq="3회",
            )
        ],
        registrations=[_registration(1, dose=dose, unit="정", slots=slots, registration_id=99)],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 12),
    )
    iron = next(total for total in data.totals if total.nutrient_name == "철")
    assert iron.amount == expected
    assert iron.reference_percent == expected_percent
    assert iron.calculation_status == "REGISTERED_SCHEDULE"
    assert 99 in data.product_labels and 1 not in data.product_labels


@pytest.mark.parametrize(
    ("dose", "unit", "slots"),
    [("2", "포", ["MORNING"]), ("2", "정", []), ("NaN", "정", ["MORNING"]), ("0", "정", ["MORNING"])],
)
def test_unconvertible_registered_schedule_is_unknown_not_catalog_default(dose, unit, slots) -> None:
    data = build_report_nutrient_data(
        products=[
            _product(1, "미확인 제품", calcium=None, iron="12", vitamin_c=None, vitamin_d=None, serving_desc="1정")
        ],
        registrations=[_registration(1, dose=dose, unit=unit, slots=slots)],
        profile=None,
        standards=[],
        today=date(2026, 9, 12),
    )
    iron = next(total for total in data.totals if total.nutrient_name == "철")
    assert iron.amount is None
    assert iron.unknown_product_names == ["미확인 제품"]
    assert data.product_labels == {}


def test_same_catalog_product_keeps_each_registered_dose_separate() -> None:
    data = build_report_nutrient_data(
        products=[_product(1, "철분", calcium=None, iron="12", vitamin_c=None, vitamin_d=None, serving_desc="1정")],
        registrations=[
            _registration(1, dose="1", unit="정", registration_id=10),
            _registration(1, dose="2", unit="정", registration_id=20),
        ],
        profile=None,
        standards=[],
        today=date(2026, 9, 12),
    )
    iron = next(total for total in data.totals if total.nutrient_name == "철")
    assert iron.amount == "36"
    assert "하루 1정" in data.product_labels[10]
    assert "하루 2정" in data.product_labels[20]


def test_product_ingredient_summaries_use_each_registered_daily_dose_and_ignore_unknown_or_nonpositive_values() -> None:
    """Would fail if a summary uses a catalog default, merges registrations, or exposes invalid ingredients."""
    product = _product(1, "종합 영양제", calcium="100", iron="0", vitamin_c="NaN", vitamin_d="5", serving_desc="1정")
    product.fiber_g = "3"
    product.phosphorus_mg = "0"
    product.potassium_mg = "Infinity"
    product.sodium_mg = "-2"
    product.vitamin_a_ug_rae = "700"
    product.retinol_ug = None
    product.beta_carotene_ug = "10"
    product.thiamine_mg = "0.5"
    product.riboflavin_mg = "0"
    product.niacin_mg = "-1"
    product.energy_kcal = "50"
    product.fat_g = "2"
    product.carb_g = "8"
    product.cholesterol_mg = "20"

    data = build_report_nutrient_data(
        products=[product],
        registrations=[
            _registration(1, dose="1", unit="정", registration_id=10),
            _registration(1, dose="2", unit="정", slots=["MORNING", "EVENING"], registration_id=20),
            _registration(1, dose="NaN", unit="정", registration_id=30),
        ],
        profile=None,
        standards=[],
        today=date(2026, 9, 12),
    )

    assert data.product_ingredient_summaries == {
        10: "식이섬유 3g · 칼슘 100mg · 비타민 A 700μg RAE · 베타카로틴 10μg · 티아민 0.5mg · 비타민 D 5μg",
        20: "식이섬유 12g · 칼슘 400mg · 비타민 A 2800μg RAE · 베타카로틴 40μg · 티아민 2mg · 비타민 D 20μg",
    }


def test_registered_ingredient_metadata_expands_totals_without_converting_vitamin_a_sources_or_niacin_ne() -> None:
    """Would fail if totals stay on the legacy four-field allowlist or infer unsupported nutrient equivalences."""
    product = _product(1, "종합 영양제", calcium="100", iron="5", vitamin_c="60", vitamin_d="10", serving_desc="1정")
    product.fiber_g = "3"
    product.phosphorus_mg = "100"
    product.potassium_mg = "200"
    product.sodium_mg = "50"
    product.vitamin_a_ug_rae = "700"
    product.retinol_ug = "200"
    product.beta_carotene_ug = "500"
    product.thiamine_mg = "0.5"
    product.riboflavin_mg = "0.6"
    product.niacin_mg = "8"
    standard = _standard(
        fiber_g_ai="20",
        phosphorus_mg_rni="700",
        potassium_mg_ai="3500",
        sodium_mg_ai="1500",
        vitamin_a_ug_rae_rni="700",
        thiamine_mg_rni="1.1",
        riboflavin_mg_rni="1.2",
        niacin_mg_rni="16",
    )

    data = build_report_nutrient_data(
        products=[product],
        registrations=[_registration(1, unit="정")],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[standard],
        today=date(2026, 9, 12),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert totals["식이섬유"].amount == "3"
    assert totals["인"].reference_value == "700"
    assert totals["비타민 A"].amount == "700"
    assert totals["비타민 A"].unit == "μg RAE"
    assert totals["비타민 A"].reference_percent == "100"
    assert totals["레티놀"].amount == "200"
    assert totals["레티놀"].reference_value is None
    assert totals["베타카로틴"].amount == "500"
    assert totals["나이아신"].amount == "8"
    assert totals["나이아신"].unit == "mg"
    assert totals["나이아신"].reference_value is None
    assert totals["나이아신"].reference_percent is None


def test_zero_observation_and_unknown_registered_schedule_render_only_relevant_nutrients() -> None:
    """Would fail if absent fields become zero rows or a known label amount becomes a fabricated total."""
    known_zero = _product(
        1, "식이섬유 0 제품", calcium=None, iron=None, vitamin_c=None, vitamin_d=None, serving_desc="1정"
    )
    known_zero.fiber_g = "0"
    schedule_unknown = _product(
        2,
        "인 함량 제품",
        calcium=None,
        iron=None,
        vitamin_c=None,
        vitamin_d=None,
        serving_desc="1정",
    )
    schedule_unknown.phosphorus_mg = "100"

    data = build_report_nutrient_data(
        products=[known_zero, schedule_unknown],
        registrations=[_registration(1, unit="정"), _registration(2, unit="포")],
        profile=None,
        standards=[],
        today=date(2026, 9, 12),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert set(totals) == {"인"}
    assert totals["인"].amount is None
    assert totals["인"].calculation_status == "UNAVAILABLE"
    assert totals["인"].unknown_product_names == ["식이섬유 0 제품", "인 함량 제품"]


def test_zero_contribution_does_not_mask_an_unavailable_positive_label_amount() -> None:
    data = build_report_nutrient_data(
        products=[
            _product(1, "칼슘 없는 제품", calcium="0", iron=None, vitamin_c=None, vitamin_d=None),
            _product(2, "칼슘 있는 제품", calcium="100", iron=None, vitamin_c=None, vitamin_d=None),
        ],
        registrations=[_registration(1), _registration(2, unit="포")],
        profile=None,
        standards=[],
        today=date(2026, 9, 12),
    )
    assert len(data.totals) == 1
    assert data.totals[0].nutrient_name == "칼슘"
    assert data.totals[0].amount is None
    assert data.totals[0].calculation_status == "UNAVAILABLE"


def test_server_profile_age_uses_seoul_calendar_day(monkeypatch) -> None:
    """Would fail if an UTC-hosted server selects the previous day's demographic standard."""

    class SeoulClock:
        @classmethod
        def now(cls, timezone):
            assert timezone.key == "Asia/Seoul"
            return datetime(2026, 9, 10, 0, 1)

    monkeypatch.setattr(nutrients, "datetime", SeoulClock)

    assert nutrients._service_today() == date(2026, 9, 10)


class _AwaitableRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def order_by(self, *_: str) -> "_AwaitableRows":
        return self

    def limit(self, _: int) -> "_AwaitableRows":
        return self

    def __await__(self):
        async def resolve() -> list[object]:
            return self.rows

        return resolve().__await__()


class _UserQuery:
    def __init__(self, user: object) -> None:
        self.user = user

    async def first(self) -> object:
        return self.user


async def test_loader_queries_only_context_user_and_public_context_product_ids(monkeypatch) -> None:
    """Would fail if the loader broadens a user/profile or public-product query beyond active context IDs."""
    calls: dict[str, list[dict[str, object]]] = {"user": [], "product": [], "standard": []}
    profile = SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE")
    products = [
        _product(10, "활성 제품", calcium="100", iron="1", vitamin_c="1", vitamin_d="1"),
        _product(20, "다른 활성 제품", calcium="100", iron="1", vitamin_c="1", vitamin_d="1"),
    ]

    def user_filter(**criteria: object) -> _UserQuery:
        calls["user"].append(criteria)
        return _UserQuery(profile)

    def product_filter(**criteria: object) -> _AwaitableRows:
        calls["product"].append(criteria)
        return _AwaitableRows(products)

    def standard_filter(**criteria: object) -> _AwaitableRows:
        calls["standard"].append(criteria)
        return _AwaitableRows([_standard()])

    monkeypatch.setattr(nutrients, "User", SimpleNamespace(filter=user_filter))
    monkeypatch.setattr(nutrients, "SupplementNutrient", SimpleNamespace(filter=product_filter))
    monkeypatch.setattr(nutrients, "NutrientStandard", SimpleNamespace(filter=standard_filter))
    context = ActiveIntakeContext(
        user_id=77,
        supplements=[
            ActiveSupplement(
                registration_id=1,
                supplement_nutrient_id=20,
                name="다른 활성 제품",
                dose_amount="9",
                dose_unit="캡슐",
                start_date=date(2026, 9, 1),
                scheduled_slots=["MORNING"],
            ),
            ActiveSupplement(
                registration_id=2,
                supplement_nutrient_id=10,
                name="활성 제품",
                dose_amount="9",
                dose_unit="캡슐",
                start_date=date(2026, 9, 1),
                scheduled_slots=["MORNING", "EVENING"],
            ),
        ],
    )

    result = await load_report_nutrients(context)

    assert calls["user"] == [{"id": 77}]
    assert calls["product"] == [{"id__in": [10, 20]}]
    assert calls["standard"] == [{"grp": "여자", "age": "30-49세"}]
    assert next(total for total in result.totals if total.nutrient_name == "철").amount == "27"
    assert "하루 9캡슐" in result.product_labels[1]
    assert "하루 18캡슐" in result.product_labels[2]
