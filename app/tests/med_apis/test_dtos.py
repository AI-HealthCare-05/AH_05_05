from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError


def valid_payload() -> dict[str, object]:
    return {
        "dose_amount": "1.000",
        "dose_unit": " 정 ",
        "start_date": "2026-08-24",
        "end_date": None,
        "slots": ["MORNING", "EVENING"],
        "note": " 식후 복용 ",
    }


def test_upsert_normalizes_text_and_accepts_valid_slots() -> None:
    from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpsertRequest

    request = UserSupplementNutrientUpsertRequest.model_validate(valid_payload())

    assert request.dose_amount == Decimal("1.000")
    assert request.dose_unit == "정"
    assert request.note == "식후 복용"
    assert [slot.value for slot in request.slots] == ["MORNING", "EVENING"]


def test_upsert_rejects_duplicate_and_empty_slots() -> None:
    from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpsertRequest

    duplicate = valid_payload()
    duplicate["slots"] = ["MORNING", "MORNING"]
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(duplicate)

    empty = valid_payload()
    empty["slots"] = []
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(empty)


def test_upsert_rejects_non_positive_dose_and_invalid_date_range() -> None:
    from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpsertRequest

    non_positive = valid_payload()
    non_positive["dose_amount"] = 0
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(non_positive)

    invalid_dates = valid_payload()
    invalid_dates["end_date"] = date(2026, 8, 23)
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(invalid_dates)


def test_update_rejects_duplicate_slots_and_blank_dose_unit() -> None:
    from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpdateRequest

    with pytest.raises(ValidationError):
        UserSupplementNutrientUpdateRequest.model_validate({"slots": ["LUNCH", "LUNCH"]})
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpdateRequest.model_validate({"dose_unit": "   "})
