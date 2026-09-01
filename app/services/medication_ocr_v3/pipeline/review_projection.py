"""Project validated OCR evidence into the public v3 medication review shape."""

from __future__ import annotations

import math
from datetime import date
from fractions import Fraction

from app.services.medication_ocr_v3.pipeline.grounding import GroundedField, GroundedMedication, GroundedResult
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationIssueCode,
    MedicationRow,
    MedicationRowsResult,
    dose_quantity_value_and_unit,
)

_FIELD_VALIDATION_ISSUES = frozenset(
    {
        MedicationIssueCode.INVALID_FIELD_VALUE,
        MedicationIssueCode.INVALID_POSITIVE_INTEGER,
        MedicationIssueCode.UNREPRESENTABLE_POSITIVE_INTEGER,
        MedicationIssueCode.INVALID_BLOCK_GEOMETRY,
    }
)


def build_project_review(
    result: MedicationRowsResult,
    grounded: GroundedResult | None = None,
) -> dict[str, object]:
    """Return one omission-based public medication result and no OCR provenance."""

    fields: dict[str, object] = {}
    low_confidence_count = 0
    if grounded is not None and _valid_grounded_date(grounded.dispensed_date):
        date_confidence = _grounded_confidence(grounded.dispensed_date)
        fields["dispensedDate"] = {
            "value": grounded.dispensed_date.value,
            "confidence": date_confidence,
        }
        low_confidence_count += int(date_confidence == "low")

    grounded_by_index = _map_grounded_medications(
        result.medications,
        grounded.medications if grounded is not None else (),
    )
    medications: list[dict[str, object]] = []
    for source_index, row in enumerate(result.medications, start=1):
        if not _displayable_name(row):
            continue
        projected = _project_medication(
            row,
            grounded_by_index.get(source_index),
            temp_id=f"med-{source_index}",
        )
        medications.append(projected)
        low_confidence_count += int(projected["confidence"] == "low")

    return {
        "fields": fields,
        "medications": medications,
        "lowConfidenceCount": low_confidence_count,
    }


def _map_grounded_medications(
    rows: tuple[MedicationRow, ...],
    grounded_medications: tuple[GroundedMedication, ...],
) -> dict[int, GroundedMedication]:
    mapped: dict[int, GroundedMedication] = {}
    consumed: set[str] = set()
    for index, row in enumerate(rows, start=1):
        name_ids = set(row.fields.name.block_ids)
        matches = tuple(
            medication
            for medication in grounded_medications
            if medication.row_id not in consumed
            and name_ids.intersection(medication.name.block_ids)
        )
        if len(matches) == 1:
            mapped[index] = matches[0]
            consumed.add(matches[0].row_id)
    for index in range(1, len(rows) + 1):
        if index in mapped:
            continue
        row_id = f"row-{index:04d}"
        matches = tuple(
            medication
            for medication in grounded_medications
            if medication.row_id == row_id and medication.row_id not in consumed
        )
        if len(matches) == 1:
            mapped[index] = matches[0]
            consumed.add(matches[0].row_id)
    return mapped


def _project_medication(
    row: MedicationRow,
    grounded: GroundedMedication | None,
    *,
    temp_id: str,
) -> dict[str, object]:
    medication: dict[str, object] = {
        "tempId": temp_id,
        "name": row.name,
    }
    strength = grounded.strength if grounded is not None else None
    if strength is not None and _valid_grounded_strength(strength):
        medication["strength"] = strength.value

    quantity = _public_dose_quantity(row.fields.dose_quantity)
    if quantity is not None:
        medication["doseQuantity"] = quantity
    if _valid_integer_field(row.fields.times_per_day, minimum=1, maximum=6):
        medication["timesPerDay"] = row.fields.times_per_day.value
    if _valid_integer_field(row.fields.days, minimum=1, maximum=365):
        medication["days"] = row.fields.days.value

    medication["confidence"] = _medication_confidence(row, strength, medication)
    return medication


def _structurally_valid_name(row: MedicationRow) -> bool:
    field = row.fields.name
    return bool(
        isinstance(row.name, str)
        and row.name.strip()
        and any(character.isalpha() for character in row.name)
        and field.value == row.name
        and field.block_ids
        and field.bbox is not None
        and MedicationIssueCode.INVALID_BLOCK_GEOMETRY not in field.issues
    )


def _displayable_name(row: MedicationRow) -> bool:
    field = row.fields.name
    return bool(
        isinstance(row.name, str)
        and row.name.strip()
        and field.value == row.name
        and field.block_ids
    )


def _public_dose_quantity(field: MedicationField) -> str | None:
    if field.value in (None, "") or _has_validation_issue(field):
        return None
    printed_value, unit = dose_quantity_value_and_unit(field.source_text)
    numeric_value = _positive_number(printed_value)
    if numeric_value is None:
        return None
    return f"{printed_value}{_canonical_unit(unit)}" if unit else printed_value


def _positive_number(value: str) -> int | float | None:
    try:
        if "/" in value:
            parsed = Fraction(value)
            numeric: int | float = float(parsed)
        elif "." in value:
            numeric = float(value)
        else:
            numeric = int(value)
    except (OverflowError, ValueError, ZeroDivisionError):
        return None
    if isinstance(numeric, bool) or not math.isfinite(float(numeric)) or numeric <= 0:
        return None
    return numeric


def _canonical_unit(unit: str) -> str:
    lowered = unit.lower()
    if lowered == "ml":
        return "mL"
    return unit


def _valid_integer_field(
    field: MedicationField,
    *,
    minimum: int,
    maximum: int,
) -> bool:
    return bool(
        isinstance(field.value, int)
        and not isinstance(field.value, bool)
        and minimum <= field.value <= maximum
        and not _has_validation_issue(field)
    )


def _has_validation_issue(field: MedicationField) -> bool:
    return bool(_FIELD_VALIDATION_ISSUES.intersection(field.issues))


def _medication_confidence(
    row: MedicationRow,
    strength: GroundedField | None,
    medication: dict[str, object],
) -> str:
    if not _structurally_valid_name(row):
        return "low"
    required_medical_keys = {
        "strength",
        "doseQuantity",
        "timesPerDay",
        "days",
    }
    if not required_medical_keys <= medication.keys():
        return "low"
    deterministic_fields = (
        row.fields.name,
        row.fields.dose_quantity,
        row.fields.times_per_day,
        row.fields.days,
    )
    if any(_has_validation_issue(field) for field in deterministic_fields):
        return "low"
    if strength is None or strength.issues:
        return "low"
    confidences = [field.confidence for field in deterministic_fields]
    confidences.append(strength.confidence)
    if any(confidence is None for confidence in confidences):
        return "low"
    return _confidence_tier(
        min(confidence for confidence in confidences if confidence is not None)
    )


def _valid_grounded_field(field: GroundedField) -> bool:
    return field.value not in (None, "") and not field.issues


def _valid_grounded_date(field: GroundedField) -> bool:
    if not _valid_grounded_field(field) or not isinstance(field.value, str):
        return False
    try:
        return date.fromisoformat(field.value).isoformat() == field.value
    except ValueError:
        return False


def _valid_grounded_strength(field: GroundedField) -> bool:
    return bool(
        _valid_grounded_field(field)
        and isinstance(field.value, str)
        and field.value.strip()
    )


def _grounded_confidence(field: GroundedField) -> str:
    if field.confidence is None:
        return "low"
    return _confidence_tier(field.confidence)


def _confidence_tier(confidence: float) -> str:
    if confidence >= 0.90:
        return "high"
    if confidence >= 0.70:
        return "medium"
    return "low"
