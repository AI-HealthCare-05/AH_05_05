from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.medication_ocr_v3.pipeline.grounding import (
    GroundedField,
    GroundedMedication,
    GroundedResult,
    GroundingIssue,
    GroundingIssueCode,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationFields,
    MedicationIssueCode,
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


@pytest.mark.parametrize(
    "missing",
    [
        ("dose_quantity",),
        ("strength", "dose_quantity"),
        ("times_per_day", "days"),
        ("strength", "dose_quantity", "times_per_day", "days"),
    ],
)
def test_absent_optional_fields_do_not_lower_medication_confidence(missing: tuple[str, ...]) -> None:
    fields = MedicationFields(
        _field("외용제", "외용제", "name"),
        _field("1", "1", "dose"),
        _field(2, "2", "times"),
        _field(14, "14", "days"),
    )
    empty = MedicationField(None, "", (), None, None, (MedicationIssueCode.INCOMPLETE_MEDICATION_FIELD,))
    fields = replace(fields, **{key: empty for key in missing if key != "strength"})
    row = MedicationRow(
        "외용제", "", fields.times_per_day.value, fields.days.value, 0.95, AxisAlignedBBox(0, 0, 100, 20), fields, ()
    )
    strength = (
        GroundedField(None, "", (), (), None, None, ())
        if "strength" in missing
        else GroundedField("1%", "1%", ("strength",), (), AxisAlignedBBox(0, 0, 10, 10), 0.95, ())
    )
    grounded_fields = [
        GroundedField(f.value, f.source_text, f.block_ids, (), f.bbox, f.confidence, ())
        for f in (fields.name, fields.dose_quantity, fields.times_per_day, fields.days)
    ]
    grounded = GroundedResult(
        GroundedField(None, "", (), (), None, None, ()),
        (GroundedMedication("row-0001", grounded_fields[0], strength, *grounded_fields[1:]),),
        (),
    )

    review = build_project_review(MedicationRowsResult(None, (row,), ()), grounded)

    assert review["medications"][0]["confidence"] == "high"
    assert review["lowConfidenceCount"] == 0
    public_keys = {
        "strength": "strength",
        "dose_quantity": "doseQuantity",
        "times_per_day": "timesPerDay",
        "days": "days",
    }
    assert not any(public_keys[key] in review["medications"][0] for key in missing)


@pytest.mark.parametrize(
    "confidence,issues", [(0.60, ()), (None, ()), (0.95, (MedicationIssueCode.INVALID_FIELD_VALUE,))]
)
@pytest.mark.parametrize("field_name", ["name", "dose_quantity", "times_per_day", "days"])
def test_present_uncertain_or_invalid_fields_still_lower_confidence(
    field_name: str, confidence: float | None, issues: tuple
) -> None:
    name = _field("외용제", "외용제", "name")
    empty = MedicationField(None, "", (), None, None, ())
    fields = MedicationFields(name, empty, empty, empty)
    value = "외용제" if field_name == "name" else ("1" if field_name == "dose_quantity" else 1)
    uncertain = replace(_field(value, str(value), field_name), confidence=confidence, issues=issues)
    fields = replace(fields, **{field_name: uncertain})
    row = MedicationRow("외용제", "", None, None, 0.95, AxisAlignedBBox(0, 0, 100, 20), fields, ())

    review = build_project_review(MedicationRowsResult(None, (row,), ()))

    assert review["medications"][0]["confidence"] == "low"
    assert review["lowConfidenceCount"] == 1


@pytest.mark.parametrize("value,confidence,invalid", [("1%", 0.6, False), ("1%", None, False), (None, None, True)])
def test_uncertain_strength_or_invalid_empty_strength_remains_low(value, confidence, invalid) -> None:
    name = _field("외용제", "외용제", "name")
    empty = MedicationField(None, "", (), None, None, ())
    row = MedicationRow(
        "외용제", "", None, None, 0.95, AxisAlignedBBox(0, 0, 100, 20), MedicationFields(name, empty, empty, empty), ()
    )
    blank = GroundedField(None, "", (), (), None, None, ())
    issue = GroundingIssue(GroundingIssueCode.INVALID_FIELD_VALUE, "strength", (), "row-0001")
    strength = GroundedField(value, value or "", (), (), None, confidence, (issue,) if invalid else ())
    grounded = GroundedResult(blank, (GroundedMedication("row-0001", blank, strength, blank, blank, blank),), ())

    review = build_project_review(MedicationRowsResult(None, (row,), ()), grounded)

    assert review["medications"][0]["confidence"] == "low"
    assert review["lowConfidenceCount"] == 1


@pytest.mark.parametrize("field_name", ["dose_quantity", "times_per_day", "days"])
def test_invalid_empty_optional_field_is_not_treated_as_absent(field_name: str) -> None:
    name = _field("외용제", "외용제", "name")
    empty = MedicationField(None, "", (), None, None, ())
    fields = replace(
        MedicationFields(name, empty, empty, empty),
        **{field_name: replace(empty, issues=(MedicationIssueCode.INVALID_FIELD_VALUE,))},
    )
    row = MedicationRow("외용제", "", None, None, 0.95, AxisAlignedBBox(0, 0, 100, 20), fields, ())

    review = build_project_review(MedicationRowsResult(None, (row,), ()))

    assert review["medications"][0]["confidence"] == "low"
    assert review["lowConfidenceCount"] == 1
