"""Fail-closed validation and OCR-only materialization for v3 grounding IDs."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum

from app.services.medication_ocr_v3.domain.grounding import EvidenceBlock, EvidenceCatalog, GroundingSelection
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox, group_visual_lines
from app.services.medication_ocr_v3.pipeline.ocr_normalization import normalize_strength_ocr

_DATE_PATTERN = re.compile(
    r"^(?:(?:조제\s*일(?:\s*자)?)(?:\s|[:：,，·-])*)?"
    r"(?P<year>\d{2}|\d{4})"
    r"(?:(?P<separator>[./-])(?P<month>\d{1,2})(?P=separator)(?P<day>\d{1,2})|"
    r"(?P<compact_month>\d{2})(?P<compact_day>\d{2}))$"
)
_STRENGTH_PATTERN = re.compile(
    r"(?<![\d./])\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?"
    r"\s*(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램|마이크로그램|%)(?!\w)",
    re.IGNORECASE,
)
_LABEL_SEPARATOR = r"(?:\s|[:：,，·-])*"
_STRENGTH_LABEL_PATTERN = re.compile(
    r"^(?:함량|용량)" + _LABEL_SEPARATOR,
    re.IGNORECASE,
)


class GroundingIssueCode(StrEnum):
    UNKNOWN_BLOCK_ID = "UNKNOWN_BLOCK_ID"
    WRONG_FIELD = "WRONG_FIELD"
    DISALLOWED_FIELD = "WRONG_FIELD"
    BLOCK_NOT_ALLOWED_FOR_FIELD = "WRONG_FIELD"
    CROSS_ROW_BLOCK_ID = "CROSS_ROW_BLOCK_ID"
    DUPLICATE_BLOCK_ID = "DUPLICATE_BLOCK_ID"
    DUPLICATE_REFERENCE = "DUPLICATE_BLOCK_ID"
    UNKNOWN_ROW_ID = "UNKNOWN_ROW_ID"
    DUPLICATE_ROW_ID = "DUPLICATE_ROW_ID"
    MISSING_NAME_EVIDENCE = "MISSING_NAME_EVIDENCE"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"
    INVALID_VALUE = "INVALID_FIELD_VALUE"
    AMBIGUOUS_FIELD_VALUE = "AMBIGUOUS_FIELD_VALUE"
    DETERMINISTIC_EVIDENCE_OVERRIDE = "DETERMINISTIC_EVIDENCE_OVERRIDE"


@dataclass(frozen=True, slots=True)
class GroundingIssue:
    code: GroundingIssueCode
    field: str
    block_ids: tuple[str, ...]
    row_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "rowId": self.row_id,
            "field": self.field,
            "blockIds": list(self.block_ids),
        }


@dataclass(frozen=True, slots=True)
class GroundedField:
    value: str | int | None
    source_text: str
    block_ids: tuple[str, ...]
    rejected_block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox | None
    confidence: float | None
    issues: tuple[GroundingIssueCode, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "sourceText": self.source_text,
            "blockIds": list(self.block_ids),
            "rejectedBlockIds": list(self.rejected_block_ids),
            "bbox": self.bbox.as_dict() if self.bbox is not None else None,
            "confidence": self.confidence,
            "issues": [issue.value for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class GroundedMedication:
    row_id: str
    name: GroundedField
    strength: GroundedField
    dose_quantity: GroundedField
    times_per_day: GroundedField
    days: GroundedField

    def fields(self) -> tuple[GroundedField, ...]:
        return (
            self.name,
            self.strength,
            self.dose_quantity,
            self.times_per_day,
            self.days,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "rowId": self.row_id,
            "name": self.name.as_dict(),
            "strength": self.strength.as_dict(),
            "doseQuantity": self.dose_quantity.as_dict(),
            "timesPerDay": self.times_per_day.as_dict(),
            "days": self.days.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class GroundedResult:
    dispensed_date: GroundedField
    medications: tuple[GroundedMedication, ...]
    issues: tuple[GroundingIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dispensedDate": self.dispensed_date.as_dict(),
            "medications": [medication.as_dict() for medication in self.medications],
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class _SelectionValidation:
    blocks_by_id: dict[str, EvidenceBlock]
    row_block_ids: dict[str, frozenset[str]]
    date_candidate_ids: frozenset[str]
    invalid_reuse: dict[tuple[str, str], frozenset[str]]
    duplicate_row_ids: frozenset[str]


def materialize_grounded_selection(
    catalog: EvidenceCatalog,
    selection: GroundingSelection,
    *,
    today: date | None = None,
) -> GroundedResult:
    """Validate selected date/strength IDs before deriving any OCR value."""

    effective_today = today or seoul_today()
    validation = _selection_validation(catalog, selection)
    issues: list[GroundingIssue] = []
    dispensed_date = _materialize_field(
        validation,
        selection.dispensed_date_block_ids,
        field="dispensedDate",
        row_id=None,
        missing_value=None,
        parser=lambda text: parse_dispensed_date(text, today=effective_today),
        issues=issues,
    )
    medications: list[GroundedMedication] = []
    for medication_selection in selection.medications:
        row_id = medication_selection.row_id
        if row_id in validation.duplicate_row_ids:
            issues.append(
                GroundingIssue(
                    GroundingIssueCode.DUPLICATE_ROW_ID,
                    "strength",
                    tuple(dict.fromkeys(medication_selection.strength_block_ids)),
                    row_id,
                )
            )
            continue
        strength = _materialize_field(
            validation,
            medication_selection.strength_block_ids,
            field="strength",
            row_id=row_id,
            missing_value=None,
            parser=parse_strength,
            issues=issues,
        )
        medications.append(
            GroundedMedication(
                row_id=row_id,
                name=_missing_field(None),
                strength=strength,
                dose_quantity=_missing_field(None),
                times_per_day=_missing_field(None),
                days=_missing_field(None),
            )
        )
    return GroundedResult(
        dispensed_date=dispensed_date,
        medications=tuple(medications),
        issues=_deduplicate_issues(issues),
    )


def seoul_today() -> date:
    """Return the run date used by the two-digit-year safety policy."""

    return datetime.now(timezone(timedelta(hours=9))).date()


def parse_dispensed_date(text: str, *, today: date) -> str | None:
    """Normalize a printed date and enforce the two-digit future boundary."""

    match = _DATE_PATTERN.fullmatch(_normalize_text(text))
    if match is None:
        return None
    printed_year = match.group("year")
    month = match.group("month") or match.group("compact_month")
    day_value = match.group("day") or match.group("compact_day")
    year = int(printed_year)
    if len(printed_year) == 2:
        year += 2000
    try:
        parsed = date(year, int(month), int(day_value))
    except ValueError:
        return None
    if len(printed_year) == 2 and parsed > today + timedelta(days=31):
        return None
    return parsed.isoformat()


def parse_strength(text: str) -> str | None:
    """Return only a printed strength expression supported by OCR evidence."""

    normalized = _STRENGTH_LABEL_PATTERN.sub(
        "",
        normalize_strength_ocr(_normalize_text(text)).replace("_", " "),
        count=1,
    )
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    matches = tuple(_STRENGTH_PATTERN.finditer(normalized))
    if not 1 <= len(matches) <= 4:
        return None
    return " ".join(" ".join(match.group(0).split()) for match in matches)


def _selection_validation(
    catalog: EvidenceCatalog,
    selection: GroundingSelection,
) -> _SelectionValidation:
    block_counts = Counter(block.block_id for block in catalog.blocks)
    blocks_by_id = {
        block.block_id: block
        for block in catalog.blocks
        if block_counts[block.block_id] == 1
    }
    row_counts = Counter(row.row_id for row in catalog.rows)
    row_block_ids = {
        row.row_id: frozenset(row.block_ids)
        for row in catalog.rows
        if row_counts[row.row_id] == 1
    }
    row_selection_counts = Counter(
        medication.row_id for medication in selection.medications
    )
    invalid_reuse: dict[tuple[str, str], set[str]] = defaultdict(set)
    usages: dict[str, list[tuple[str, str]]] = defaultdict(list)

    date_key = ("", "dispensedDate")
    for block_id, count in Counter(selection.dispensed_date_block_ids).items():
        if count > 1:
            invalid_reuse[date_key].add(block_id)
        if block_id in blocks_by_id:
            usages[block_id].append(date_key)
    for medication in selection.medications:
        usage_key = (medication.row_id, "strength")
        for block_id, count in Counter(medication.strength_block_ids).items():
            if count > 1:
                invalid_reuse[usage_key].add(block_id)
            if block_id in blocks_by_id:
                usages[block_id].append(usage_key)
    for block_id, block_usages in usages.items():
        if len(block_usages) > 1:
            for usage in block_usages:
                invalid_reuse[usage].add(block_id)

    return _SelectionValidation(
        blocks_by_id=blocks_by_id,
        row_block_ids=row_block_ids,
        date_candidate_ids=frozenset(block.block_id for block in catalog.date_candidates),
        invalid_reuse={key: frozenset(value) for key, value in invalid_reuse.items()},
        duplicate_row_ids=frozenset(
            row_id for row_id, count in row_selection_counts.items() if count > 1
        ),
    )


def _materialize_field(
    validation: _SelectionValidation,
    selected_block_ids: list[str],
    *,
    field: str,
    row_id: str | None,
    missing_value: str | int | None,
    parser: Callable[[str], str | int | None],
    issues: list[GroundingIssue],
) -> GroundedField:
    if not selected_block_ids:
        return _missing_field(missing_value)

    rejected_by_code: dict[GroundingIssueCode, list[str]] = defaultdict(list)
    reuse_key = (row_id or "", field)
    invalid_reuse = validation.invalid_reuse.get(reuse_key, frozenset())
    if row_id is not None and row_id not in validation.row_block_ids:
        rejected_by_code[GroundingIssueCode.UNKNOWN_ROW_ID].extend(selected_block_ids)

    accepted: list[EvidenceBlock] = []
    for block_id in dict.fromkeys(selected_block_ids):
        block = validation.blocks_by_id.get(block_id)
        if block is None:
            rejected_by_code[GroundingIssueCode.UNKNOWN_BLOCK_ID].append(block_id)
            continue
        if block_id in invalid_reuse:
            rejected_by_code[GroundingIssueCode.DUPLICATE_BLOCK_ID].append(block_id)
        if field not in block.allowed_fields:
            rejected_by_code[GroundingIssueCode.WRONG_FIELD].append(block_id)
        if row_id is None:
            associated = block_id in validation.date_candidate_ids
        else:
            associated = (
                block.row_ids == (row_id,)
                and block_id in validation.row_block_ids.get(row_id, frozenset())
            )
        if not associated:
            rejected_by_code[GroundingIssueCode.CROSS_ROW_BLOCK_ID].append(block_id)
        accepted.append(block)

    if rejected_by_code:
        for code, block_ids in rejected_by_code.items():
            issues.append(
                GroundingIssue(
                    code,
                    field,
                    tuple(dict.fromkeys(block_ids)),
                    row_id,
                )
            )
        return _rejected_field(missing_value, selected_block_ids, rejected_by_code)

    ordered = _visual_reading_order(accepted)
    source_text = " ".join(_normalize_text(block.text) for block in ordered).strip()
    value = parser(source_text)
    if value is None:
        issues.append(
            GroundingIssue(
                GroundingIssueCode.INVALID_FIELD_VALUE,
                field,
                tuple(block.block_id for block in ordered),
                row_id,
            )
        )
        return _rejected_field(
            missing_value,
            selected_block_ids,
            (GroundingIssueCode.INVALID_FIELD_VALUE,),
        )
    return GroundedField(
        value=value,
        source_text=source_text,
        block_ids=tuple(block.block_id for block in ordered),
        rejected_block_ids=(),
        bbox=_bbox_union(block.bbox for block in ordered),
        confidence=_conservative_confidence(ordered),
        issues=(),
    )


def _visual_reading_order(blocks: list[EvidenceBlock]) -> tuple[EvidenceBlock, ...]:
    visual_lines = group_visual_lines(
        blocks,
        bbox_of=lambda item: item.bbox,
        sort_key=lambda item: (item.bbox.center_y, item.bbox.x_min, item.block_id),
    )
    return tuple(
        block
        for line in visual_lines
        for block in sorted(line, key=lambda item: (item.bbox.x_min, item.block_id))
    )


def _missing_field(value: str | int | None) -> GroundedField:
    return GroundedField(value, "", (), (), None, None, ())


def _rejected_field(
    value: str | int | None,
    selected_block_ids: list[str],
    issue_codes: Iterable[GroundingIssueCode],
) -> GroundedField:
    return GroundedField(
        value=value,
        source_text="",
        block_ids=(),
        rejected_block_ids=tuple(dict.fromkeys(selected_block_ids)),
        bbox=None,
        confidence=None,
        issues=tuple(dict.fromkeys(issue_codes)),
    )


def _normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _conservative_confidence(blocks: tuple[EvidenceBlock, ...]) -> float | None:
    if not blocks or any(block.confidence is None for block in blocks):
        return None
    return min(block.confidence for block in blocks if block.confidence is not None)


def _bbox_union(boxes: Iterable[AxisAlignedBBox]) -> AxisAlignedBBox:
    materialized = tuple(boxes)
    return AxisAlignedBBox(
        min(box.x_min for box in materialized),
        min(box.y_min for box in materialized),
        max(box.x_max for box in materialized),
        max(box.y_max for box in materialized),
    )


def _deduplicate_issues(issues: list[GroundingIssue]) -> tuple[GroundingIssue, ...]:
    return tuple(dict.fromkeys(issues))

