from __future__ import annotations

import pytest

from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationFields,
    MedicationRow,
    MedicationRowsResult,
)
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox
from app.services.medication_ocr_v3.pipeline.review_projection import build_project_review


def _field(value: str | int | None, source_text: str, block_id: str) -> MedicationField:
    return MedicationField(
        value=value,
        source_text=source_text,
        block_ids=(block_id,),
        bbox=AxisAlignedBBox(0, 0, 10, 10),
        confidence=0.95,
        issues=(),
    )


def _project_dose_quantity(source_text: str, field_value: str | int | None) -> dict[str, object]:
    fields = MedicationFields(
        name=_field("비강분무제", "비강분무제", "name"),
        dose_quantity=_field(field_value, source_text, "dose"),
        times_per_day=_field(2, "2", "times"),
        days=_field(5, "5", "days"),
    )
    row = MedicationRow(
        name="비강분무제",
        dose_quantity=str(field_value or ""),
        times_per_day=2,
        days=5,
        confidence=0.95,
        bbox=AxisAlignedBBox(0, 0, 100, 20),
        fields=fields,
        issues=(),
    )
    review = build_project_review(MedicationRowsResult(None, (row,), ()))
    return review["medications"][0]


@pytest.mark.parametrize(
    ("source_text", "field_value", "expected_quantity"),
    [
        ("각1분무", "각1분무", "각1분무"),
        ("각 1분무", "각1분무", "각1분무"),
        ("각 비공 1분무", "각비공1분무", "각비공1분무"),
    ],
)
def test_each_side_spray_quantity_preserves_the_grounded_site_qualifier(
    source_text: str,
    field_value: str,
    expected_quantity: str,
) -> None:
    medication = _project_dose_quantity(source_text, field_value)

    assert medication["doseQuantity"] == expected_quantity


@pytest.mark.parametrize(
    ("source_text", "field_value"),
    [
        ("각 0분무", "각0분무"),
        ("각 분무", "각분무"),
        ("각 1분무메모", "각1분무메모"),
        ("각 비공 0분무", "각비공0분무"),
        ("각 1분무", "불일치"),
    ],
)
def test_nonpositive_malformed_or_ungrounded_each_side_spray_quantity_is_omitted(
    source_text: str,
    field_value: str,
) -> None:
    medication = _project_dose_quantity(source_text, field_value)

    assert "doseQuantity" not in medication


def test_standard_tablet_quantity_remains_projected() -> None:
    medication = _project_dose_quantity("1정", "1")

    assert medication["doseQuantity"] == "1정"

