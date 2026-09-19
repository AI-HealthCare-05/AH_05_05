from decimal import Decimal

from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)


class FakeNutrient:
    def __init__(self, **values: object) -> None:
        self.name = str(values.pop("name", "시험 영양제"))
        for column, _, _ in DbActiveIntakeContextProvider._NUTRIENT_COLUMNS:
            setattr(self, column, values.pop(column, None))


def test_only_recorded_amounts_are_reported() -> None:
    """값이 없는 성분은 만들지 않는다. 자료에 없는 함량을 답변에 올리면 안 된다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        FakeNutrient(calcium_mg=300, vitamin_d_ug=Decimal("10.00"), iron_mg=Decimal("0.00"))
    )

    assert [(item.name, item.amount, item.unit) for item in amounts] == [
        ("칼슘", "300", "mg"),
        ("비타민 D", "10", "㎍"),
    ]


def test_omega_product_reports_its_fat_as_omega_3() -> None:
    """이 자료는 오메가3를 총지방으로만 기록한다. 지방으로 두면 무엇을 먹는지 알 수 없다."""
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        FakeNutrient(name="CHASCO 프리미엄 오메가-3", fat_g=Decimal("1.00"))
    )

    assert [item.name for item in amounts] == ["오메가-3"]


def test_other_products_keep_fat_labelled_as_fat() -> None:
    amounts = DbActiveIntakeContextProvider._nutrient_amounts(
        FakeNutrient(name="코랄칼슘 비타민K2&D 마그네슘", fat_g=Decimal("1.00"))
    )

    assert [item.name for item in amounts] == ["지방"]
