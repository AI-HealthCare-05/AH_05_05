from datetime import date, datetime
from types import SimpleNamespace

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
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )
    totals = {total.nutrient_name: total for total in data.totals}

    assert data.profile_label == "여자 · 30-49세"
    assert data.product_labels[2] == "제품 안내량 · 하루 1캡슐 (실제 등록량과 별도 비교)"
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
    assert "실제 섭취량 합계가 아닙니다" in data.basis_note
    assert "식사" in data.basis_note


def test_missing_profile_or_invalid_label_schedule_keeps_unknown_values_null() -> None:
    """Would fail if an unknown amount/reference is silently rendered as numeric zero."""
    data = build_report_nutrient_data(
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
        products=[product],
        profile=SimpleNamespace(birth_date=date(2000, 9, 11), gender="MALE"),
        standards=[_standard(grp="남자", age="19-29세", calcium_mg_rni="800")],
        today=date(2026, 9, 10),
    )
    ambiguous = build_report_nutrient_data(
        products=[product],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard(id=1), _standard(id=2)],
        today=date(2026, 9, 10),
    )

    male_calcium = next(total for total in male.totals if total.nutrient_name == "칼슘")
    ambiguous_calcium = next(total for total in ambiguous.totals if total.nutrient_name == "칼슘")
    assert male.profile_label == "남자 · 19-29세"
    assert male_calcium.reference_value == "800"
    assert male_calcium.reference_percent == "12.5"
    assert ambiguous.profile_label == "비교 기준 확인 필요"
    assert ambiguous_calcium.amount == "100"
    assert ambiguous_calcium.reference_value is None
    assert ambiguous_calcium.reference_percent is None


def test_future_birth_date_does_not_select_a_standard() -> None:
    """Would fail if future dates are coerced to the youngest or sample demographic group."""
    data = build_report_nutrient_data(
        products=[_product(1, "제품", calcium="100", iron="1", vitamin_c="1", vitamin_d="1")],
        profile=SimpleNamespace(birth_date=date(2026, 9, 11), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )

    assert data.profile_label == "비교 기준 확인 필요"
    assert next(total for total in data.totals if total.nutrient_name == "칼슘").reference_value is None


def test_zero_label_amount_remains_a_known_zero_without_a_redundancy_contributor() -> None:
    """Would fail if zero-label products trigger a false overlapping-nutrient card."""
    data = build_report_nutrient_data(
        products=[
            _product(1, "칼슘 0 제품", calcium="0", iron="0", vitamin_c="0", vitamin_d="0"),
            _product(2, "또 다른 칼슘 0 제품", calcium="0", iron="0", vitamin_c="0", vitamin_d="0"),
        ],
        profile=SimpleNamespace(birth_date=date(1990, 1, 1), gender="FEMALE"),
        standards=[_standard()],
        today=date(2026, 9, 10),
    )

    calcium = next(total for total in data.totals if total.nutrient_name == "칼슘")

    assert calcium.amount == "0"
    assert calcium.daily_total == "0 mg"
    assert calcium.included_product_names == []
    assert calcium.unknown_product_names == []


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
                dose_unit="정",
                start_date=date(2026, 9, 1),
            ),
            ActiveSupplement(
                registration_id=2,
                supplement_nutrient_id=10,
                name="활성 제품",
                dose_amount="9",
                dose_unit="정",
                start_date=date(2026, 9, 1),
            ),
        ],
    )

    await load_report_nutrients(context)

    assert calls["user"] == [{"id": 77}]
    assert calls["product"] == [{"id__in": [10, 20]}]
    assert calls["standard"] == [{"grp": "여자", "age": "30-49세"}]
