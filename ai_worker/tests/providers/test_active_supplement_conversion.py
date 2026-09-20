from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from ai_worker.providers.db_active_intake_context_provider import (
    DbActiveIntakeContextProvider,
)


def registration(*, serving_desc: str, dose_unit: str) -> SimpleNamespace:
    """1일 2회 1정씩 등록한 칼슘 제품. 라벨 100g당 1000mg, 1회 제공량 2g(2정)."""
    return SimpleNamespace(
        id=1,
        supplement_nutrient_id=1,
        supplement_nutrient=SimpleNamespace(
            name="코랄칼슘",
            basis_qty="100g",
            serving_size="2g",
            serving_desc=serving_desc,
            calcium_mg=Decimal("1000.00"),
        ),
        dose_amount=Decimal("1"),
        dose_unit=dose_unit,
        start_date=date(2026, 9, 1),
        end_date=None,
        note=None,
        slots=[
            SimpleNamespace(slot=SimpleNamespace(value="MORNING")),
            SimpleNamespace(slot=SimpleNamespace(value="EVENING")),
        ],
    )


def test_registered_plan_amounts_reach_the_answer() -> None:
    """환산이 성립하는데도 성분이 비면, 있는 자료를 없다고 답하게 된다."""
    supplement = DbActiveIntakeContextProvider._to_active_supplement(registration(serving_desc="2정", dose_unit="정"))

    # 100g당 1000mg → 2g(=1회 제공량)당 20mg → 1정당 10mg → 하루 2정이면 20mg.
    assert [(item.name, item.amount, item.unit) for item in supplement.nutrients] == [("칼슘", "20", "mg")]


def test_products_that_cannot_be_converted_carry_no_amounts() -> None:
    """환산에 실패한 제품에 라벨 원본값을 실으면, 먹지도 않은 양을 먹는다고 답한다."""
    supplement = DbActiveIntakeContextProvider._to_active_supplement(registration(serving_desc="2정", dose_unit="ml"))

    assert supplement.nutrients == []
