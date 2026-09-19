from decimal import Decimal
from types import SimpleNamespace

from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)
from ai_worker.reports.nutrients import nutrient_display_specs
from app.models.supplement_nutrients import SupplementNutrient

ONE = Decimal("1")


def test_only_recorded_amounts_are_reported() -> None:
    """값이 없는 성분은 만들지 않는다. 자료에 없는 함량을 답변에 올리면 안 된다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        SimpleNamespace(name="시험 영양제", calcium_mg=300, vitamin_d_ug=Decimal("10.00"), iron_mg=Decimal("0.00")),
        factor=ONE,
    )

    assert [(item.name, item.amount, item.unit) for item in amounts] == [
        ("칼슘", "300", "mg"),
        ("비타민 D", "10", "μg"),
    ]


def test_amounts_follow_the_registered_intake_plan() -> None:
    """컬럼 값은 자료가 정한 기준량 기준이다. 환산하지 않으면 리포트와 다른 숫자가 나온다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        SimpleNamespace(name="시험 영양제", calcium_mg=300),
        factor=Decimal("0.5"),
    )

    assert [(item.name, item.amount) for item in amounts] == [("칼슘", "150")]


def test_omega_product_reports_its_fat_as_omega_3() -> None:
    """이 자료는 오메가3를 총지방으로만 기록한다. 지방으로 두면 무엇을 먹는지 알 수 없다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        SimpleNamespace(name="CHASCO 프리미엄 오메가-3", fat_g=Decimal("1.00")),
        factor=ONE,
    )

    assert [item.name for item in amounts] == ["오메가-3"]


def test_other_products_keep_fat_labelled_as_fat() -> None:
    """정규식이 넓어 과매칭되면 지방을 오메가-3라고 부르게 된다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        SimpleNamespace(name="코랄칼슘 비타민K2&D 마그네슘", fat_g=Decimal("1.00")),
        factor=ONE,
    )

    assert [item.name for item in amounts] == ["지방"]


def test_every_reported_column_exists_on_the_catalog_model() -> None:
    """컬럼명이 어긋나면 그 성분이 예외 없이 조용히 사라진다."""
    columns = {column for column, _, _ in nutrient_display_specs()}

    assert columns <= set(SupplementNutrient._meta.fields_map)


def test_chat_and_report_use_one_nutrient_label_table() -> None:
    """표가 둘이면 같은 영양소를 리포트와 챗봇이 다르게 부른다."""
    labels = {name for _, name, _ in nutrient_display_specs()}

    assert "나이아신" in labels
    assert "니아신" not in labels
