"""Conservative medication-row selection and grounded field materialization."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from enum import StrEnum

from app.services.medication_ocr_v3.domain.models import OcrBlockIssueCode
from app.services.medication_ocr_v3.pipeline.ocr_layout import (
    AxisAlignedBBox,
    LayoutCell,
    LayoutIssue,
    LayoutIssueCode,
    LayoutRow,
    OcrLayoutResult,
    TableCandidate,
)
from app.services.medication_ocr_v3.pipeline.ocr_normalization import normalize_dose_unit_ocr

_LOW_CONFIDENCE_THRESHOLD = 0.70
_MAX_JSON_SAFE_INTEGER = 2**53 - 1
_MAX_JSON_SAFE_DIGITS = str(_MAX_JSON_SAFE_INTEGER)
_TIMES_PATTERN = re.compile(r"([1-9][0-9]*)(?:회)?[,，]?")
_DAYS_PATTERN = re.compile(r"([1-9][0-9]*)(?:일분|일)?")
_POSITIVE_DOSE_QUANTITY_PATTERN = re.compile(
    r"^(?P<value>(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]*[1-9][0-9]*|[1-9][0-9]*/[1-9][0-9]*))"
    r"(?P<unit>정|캡슐|포|m[lℓ])?(?:씩)?$",
    re.IGNORECASE,
)
_ZERO_DOSE_QUANTITY_PATTERN = re.compile(
    r"^0(?:\.0+)?(?:정|캡슐|포|m[lℓ])?(?:씩)?$",
    re.IGNORECASE,
)
_COMBINED_SCHEDULE_SUFFIX_PATTERN = re.compile(r"[1-9][0-9]*회[,，]?[1-9][0-9]*일분")
_TRAILING_STRENGTH_PATTERN = re.compile(
    r"(?:\(?[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?"
    r"(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램|마이크로그램|%)\)?)"
)
_TRAILING_NAME_STRENGTH_TOKEN_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?:\(?[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?"
    r"(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램|마이크로그램)\)?)$",
    re.IGNORECASE,
)
_TRAILING_NAME_DOSE_TOKEN_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+)(?:정|캡슐|포|m[lℓ])$",
    re.IGNORECASE,
)
_TRAILING_PARENTHETICAL_PATTERN = re.compile(r"^(?P<base>.+)\((?P<content>[^()]*)\)$")
_PACKAGE_WITH_TRAILING_LABELS_PATTERN = re.compile(r"^(?P<base>.+)\((?P<content>[^()]*)\)(?:\s*\[[^\[\]]+\])+$")
_PACKAGE_SIZE_PARENTHETICAL_PATTERN = re.compile(
    r"[0-9]+(?:\.[0-9]+)?\s*m[lℓ]",
    re.IGNORECASE,
)
_PRODUCT_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9가-힣/%]+"
    r"(?:정|캡슐|시럽|크림|연고|현탁액|내복액|외용액|점안액|주사액|액|산|과립|패취|패치|겔)"
    r"(?:[0-9]+(?:\.[0-9]+)?(?:mg|g|ml|mℓ|밀리그램|그램)?)?(?:\.{3})?$",
    re.IGNORECASE,
)
_NON_MEDICATION_TABLE_VOCABULARY_PATTERN = re.compile(
    r"(?:급여|수납|청구|보험|부담금|진료비|조제료|처방료|소계|합계|총액|금액|"
    r"잔액|단가|수가|정산|산정|조정|행정|비용|내역|접수|운영|평가|검사|"
    r"테스트|항목|목록|구분|분류|번호|일련|업무|대상|상태|결과|기록|표|자료|문서|서비스|관리)"
)
_DUPLICATE_NAME_SIMILARITY = 0.75
_DUPLICATE_NAME_MEAN_SIMILARITY = 0.85
_MIN_TRUNCATED_NAME_PREFIX_LENGTH = 4


class MedicationIssueCode(StrEnum):
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    AMBIGUOUS_MEDICATION_TABLE = "AMBIGUOUS_MEDICATION_TABLE"
    INCOMPLETE_MEDICATION_ROW = "INCOMPLETE_MEDICATION_ROW"
    INCOMPLETE_MEDICATION_FIELD = "INCOMPLETE_MEDICATION_FIELD"
    INVALID_POSITIVE_INTEGER = "INVALID_POSITIVE_INTEGER"
    UNREPRESENTABLE_POSITIVE_INTEGER = "UNREPRESENTABLE_POSITIVE_INTEGER"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INVALID_BLOCK_GEOMETRY = "INVALID_BLOCK_GEOMETRY"
    INVALID_BLOCK_CONFIDENCE = "INVALID_BLOCK_CONFIDENCE"
    AMBIGUOUS_COLUMN_ASSIGNMENT = "AMBIGUOUS_COLUMN_ASSIGNMENT"
    CONFLICTING_GUIDANCE_EVIDENCE = "CONFLICTING_GUIDANCE_EVIDENCE"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"


@dataclass(frozen=True, slots=True)
class MedicationIssue:
    code: MedicationIssueCode
    block_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "blockIds": list(self.block_ids)}


@dataclass(frozen=True, slots=True)
class MedicationField:
    value: str | int | None
    source_text: str
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox | None
    confidence: float | None
    issues: tuple[MedicationIssueCode, ...]

    def as_dict(self) -> dict[str, object]:
        if self.confidence is not None and not math.isfinite(self.confidence):
            raise ValueError("Medication field contains non-finite values.")
        return {
            "value": self.value,
            "sourceText": self.source_text,
            "blockIds": list(self.block_ids),
            "bbox": self.bbox.as_dict() if self.bbox is not None else None,
            "confidence": self.confidence,
            "issues": [issue.value for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class MedicationFields:
    name: MedicationField
    dose_quantity: MedicationField
    times_per_day: MedicationField
    days: MedicationField

    @property
    def dose(self) -> MedicationField:
        """Compatibility alias for layout-only callers; v3 serializes doseQuantity."""

        return self.dose_quantity

    def as_tuple(
        self,
    ) -> tuple[MedicationField, MedicationField, MedicationField, MedicationField]:
        return self.name, self.dose_quantity, self.times_per_day, self.days

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name.as_dict(),
            "doseQuantity": self.dose_quantity.as_dict(),
            "timesPerDay": self.times_per_day.as_dict(),
            "days": self.days.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class MedicationRow:
    name: str
    dose_quantity: str
    times_per_day: int | None
    days: int | None
    confidence: float | None
    bbox: AxisAlignedBBox
    fields: MedicationFields
    issues: tuple[MedicationIssueCode, ...]

    @property
    def dose(self) -> str:
        """Compatibility alias for layout tests; v3 uses dose_quantity internally."""

        return self.dose_quantity

    def as_dict(self) -> dict[str, object]:
        if self.confidence is not None and not math.isfinite(self.confidence):
            raise ValueError("Medication row contains non-finite values.")
        return {
            "name": self.name,
            "doseQuantity": self.dose_quantity,
            "timesPerDay": self.times_per_day,
            "days": self.days,
            "confidence": self.confidence,
            "bbox": self.bbox.as_dict(),
            "fields": self.fields.as_dict(),
            "issues": [issue.value for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class MedicationRowsResult:
    selected_table: TableCandidate | None
    medications: tuple[MedicationRow, ...]
    issues: tuple[MedicationIssue, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "table": self.selected_table.as_dict() if self.selected_table is not None else None,
            "medications": [medication.as_dict() for medication in self.medications],
            "issues": [issue.as_dict() for issue in self.issues],
        }


def parse_times_per_day(text: str) -> int | None:
    """Parse one explicit positive integer, optionally followed by ``회``."""

    value, _ = _parse_json_safe_positive_integer(text, _TIMES_PATTERN)
    return value


def parse_days(text: str) -> int | None:
    """Parse one explicit positive integer, optionally followed by a day suffix."""

    value, _ = _parse_json_safe_positive_integer(text, _DAYS_PATTERN)
    return value


def _parse_json_safe_positive_integer(
    text: str,
    pattern: re.Pattern[str],
) -> tuple[int | None, bool]:
    match = pattern.fullmatch(text)
    if match is None:
        return None, False
    digits = match.group(1)
    if len(digits) > len(_MAX_JSON_SAFE_DIGITS) or (
        len(digits) == len(_MAX_JSON_SAFE_DIGITS) and digits > _MAX_JSON_SAFE_DIGITS
    ):
        return None, True
    return int(digits), False


def materialize_medication_rows(layout: OcrLayoutResult) -> MedicationRowsResult:
    """Select only an unambiguous structural candidate and ground every field."""

    candidates_with_body_evidence = tuple(
        candidate for candidate in layout.table_candidates if candidate.rows or candidate.ambiguous_column_evidence
    )
    if not candidates_with_body_evidence:
        table_not_found = MedicationIssue(MedicationIssueCode.TABLE_NOT_FOUND)
        return MedicationRowsResult(
            selected_table=None,
            medications=(),
            issues=(*_layout_issues(layout.issues), table_not_found),
        )
    semantically_ineligible = any(
        not _is_semantically_eligible_medication_candidate(candidate) for candidate in candidates_with_body_evidence
    )
    conflicting_near_duplicate = (
        semantically_ineligible
        or _has_conflicting_near_duplicate_names(candidates_with_body_evidence)
        or _has_rejected_complete_duplicate_pair(candidates_with_body_evidence)
    )
    selected = None if conflicting_near_duplicate else _select_candidate(candidates_with_body_evidence)
    if selected is None and not conflicting_near_duplicate:
        selected = _select_complete_correlated_duplicate_candidate(candidates_with_body_evidence)
    if selected is None and not conflicting_near_duplicate:
        selected = _select_complete_candidate_with_trailing_partial_duplicate(candidates_with_body_evidence)
    if selected is None and not conflicting_near_duplicate:
        selected = _merge_correlated_duplicate_candidates(candidates_with_body_evidence)
    if selected is None and not conflicting_near_duplicate:
        selected = _select_correlated_truncated_name_candidate(candidates_with_body_evidence)
    if selected is None and not conflicting_near_duplicate:
        selected = _select_candidate_with_sparse_correlated_duplicate(candidates_with_body_evidence)
    if selected is None:
        issues = [
            *_layout_issues(layout.issues),
            MedicationIssue(MedicationIssueCode.AMBIGUOUS_MEDICATION_TABLE),
        ]
        return MedicationRowsResult(
            selected_table=None,
            medications=(),
            issues=_deduplicate_medication_issues(issues),
        )
    selected = _refine_correlated_receipt_names(
        selected,
        candidates_with_body_evidence,
    )
    summary_merged_rows = _merge_correlated_summary_rows(
        selected.rows,
        layout.summary_rows,
    )
    if summary_merged_rows != selected.rows:
        selected = replace(
            selected,
            rows=summary_merged_rows,
            bbox=_bbox_union((selected.bbox, *(row.bbox for row in summary_merged_rows))),
        )
    needs_guidance = any(cell is None or not cell.text for row in selected.rows for cell in row.cells[1:])
    merged_rows, guidance_conflict, observed_guidance_conflict = (
        _merge_grounded_guidance_rows(selected, layout.guidance_rows)
        if needs_guidance
        else (selected.rows, False, False)
    )
    if guidance_conflict:
        issues = [
            *_layout_issues(layout.issues),
            MedicationIssue(MedicationIssueCode.AMBIGUOUS_MEDICATION_TABLE),
        ]
        return MedicationRowsResult(
            selected_table=None,
            medications=(),
            issues=_deduplicate_medication_issues(issues),
        )
    if merged_rows != selected.rows:
        selected = replace(
            selected,
            rows=merged_rows,
            bbox=_bbox_union((selected.bbox, *(row.bbox for row in merged_rows))),
        )
    medications: list[MedicationRow] = []
    result_issues = list(_layout_issues(layout.issues))
    if observed_guidance_conflict:
        result_issues.append(MedicationIssue(MedicationIssueCode.CONFLICTING_GUIDANCE_EVIDENCE))
    for row in selected.rows:
        name_cell = row.cells[0]
        if name_cell is None or not name_cell.text:
            result_issues.append(
                MedicationIssue(
                    MedicationIssueCode.INCOMPLETE_MEDICATION_ROW,
                    row.source_block_ids,
                )
            )
            continue
        medications.append(_medication_row(row))
    return MedicationRowsResult(
        selected_table=selected,
        medications=tuple(medications),
        issues=_deduplicate_medication_issues(result_issues),
    )


def _select_candidate(candidates: tuple[TableCandidate, ...]) -> TableCandidate | None:
    signatures = tuple(_candidate_signature(candidate) for candidate in candidates)
    if all(signature == signatures[0] for signature in signatures[1:]):
        return min(candidates, key=_representative_key)
    dominators = [
        candidate
        for candidate in candidates
        if all(other is candidate or _candidate_dominates(candidate, other) for other in candidates)
    ]
    return dominators[0] if len(dominators) == 1 else None


def _merge_correlated_duplicate_candidates(
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate | None:
    if len(candidates) != 2:
        return None
    merged: list[TableCandidate] = []
    for donor, base in (candidates, tuple(reversed(candidates))):
        candidate = _merge_correlated_duplicate(donor, base)
        if candidate is not None:
            merged.append(candidate)
    return merged[0] if len(merged) == 1 else None


def _select_complete_correlated_duplicate_candidate(
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate | None:
    """Choose a structural primary when two complete tables corroborate exactly."""

    if len(candidates) != 2:
        return None
    first, second = candidates
    if not _is_complete_correlated_duplicate_pair(first, second):
        return None
    primary, donor = sorted((first, second), key=_complete_duplicate_primary_key)
    return _complete_correlated_duplicate_with_name_donor(primary, donor)


def _select_complete_candidate_with_trailing_partial_duplicate(
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate | None:
    """Prefer a complete table corroborated by the matching prefix of a shorter copy."""

    if len(candidates) != 2:
        return None
    primary, partial = sorted(candidates, key=lambda candidate: len(candidate.rows), reverse=True)
    if (
        len(primary.rows) != len(partial.rows) + 1
        or len(partial.rows) < 3
        or primary.ambiguous_column_evidence
        or partial.ambiguous_column_evidence
        or not all(_is_complete_authoritative_row(row) for row in primary.rows)
        or not all(_is_complete_authoritative_row(row) for row in partial.rows)
    ):
        return None

    exact_names = 0
    compatible_names = 0
    for primary_row, partial_row in zip(primary.rows, partial.rows, strict=False):
        primary_name = primary_row.cells[0]
        partial_name = partial_row.cells[0]
        if primary_name is None or partial_name is None:
            return None
        exact_names += _canonical_candidate_name(primary_name.text) == _canonical_candidate_name(partial_name.text)
        compatible_names += _compatible_duplicate_name(
            primary_name.text,
            partial_name.text,
        )
        if any(
            primary_cell is None
            or partial_cell is None
            or (column == 1 and not _is_explicit_dose_quantity(primary_cell))
            or (column == 1 and not _is_explicit_dose_quantity(partial_cell))
            or not _same_grounded_field(column, primary_cell, partial_cell)
            for column, (primary_cell, partial_cell) in enumerate(
                zip(primary_row.cells[1:], partial_row.cells[1:], strict=True),
                start=1,
            )
        ):
            return None
    if exact_names < 2 or compatible_names < len(partial.rows) - 1:
        return None
    if partial.bbox.width * partial.bbox.height <= primary.bbox.width * primary.bbox.height:
        return primary

    rows = (
        tuple(
            replace(primary_row, cells=(partial_name, *primary_row.cells[1:]))
            if (
                (primary_name := primary_row.cells[0]) is not None
                and (partial_name := partial_row.cells[0]) is not None
                and _canonical_candidate_name(primary_name.text) != _canonical_candidate_name(partial_name.text)
                and _compatible_duplicate_name(primary_name.text, partial_name.text)
            )
            else primary_row
            for primary_row, partial_row in zip(primary.rows, partial.rows, strict=False)
        )
        + primary.rows[len(partial.rows) :]
    )
    return replace(
        primary,
        rows=rows,
        bbox=_bbox_union((primary.bbox, *(row.bbox for row in rows))),
    )


def _is_complete_correlated_duplicate_pair(
    first: TableCandidate,
    second: TableCandidate,
) -> bool:
    if not _has_complete_duplicate_structure(first, second):
        return False
    first_names = _normalized_row_names(first.rows)
    second_names = _normalized_row_names(second.rows)
    if not (
        _unique_nonempty_names(first_names) and _unique_nonempty_names(second_names)
    ) or not _has_strong_medication_name_majority(first, second):
        return False

    name_similarities: list[float] = []
    for first_row, second_row in zip(first.rows, second.rows, strict=True):
        first_name = first_row.cells[0]
        second_name = second_row.cells[0]
        if (
            first_name is None
            or second_name is None
            or not _strict_complete_duplicate_name_pair(
                first_name,
                second_name,
                first.rows,
                second.rows,
            )
        ):
            return False
        first_normalized = _canonical_candidate_name(first_name.text)
        second_normalized = _canonical_candidate_name(second_name.text)
        name_similarities.append(
            SequenceMatcher(
                None,
                first_normalized,
                second_normalized,
                autojunk=False,
            ).ratio()
        )
        for column, (first_cell, second_cell) in enumerate(
            zip(first_row.cells[1:], second_row.cells[1:], strict=True),
            start=1,
        ):
            if (
                first_cell is None
                or second_cell is None
                or (column == 1 and not _is_explicit_dose_quantity(first_cell))
                or (column == 1 and not _is_explicit_dose_quantity(second_cell))
                or not _same_grounded_field(column, first_cell, second_cell)
            ):
                return False
    return (
        min(name_similarities) >= _DUPLICATE_NAME_SIMILARITY
        and sum(name_similarities) / len(name_similarities) >= _DUPLICATE_NAME_MEAN_SIMILARITY
    )


def _has_complete_duplicate_structure(
    first: TableCandidate,
    second: TableCandidate,
) -> bool:
    if (
        first.ambiguous_column_evidence
        or second.ambiguous_column_evidence
        or first.header_inferred
        or second.header_inferred
        or first.observed_header_coverage < 4
        or second.observed_header_coverage < 4
        or len(first.rows) != len(second.rows)
        or len(first.rows) < 3
        or not _bboxes_are_disjoint(first.bbox, second.bbox)
        or not all(_is_complete_authoritative_row(row) for row in first.rows)
        or not all(_is_complete_authoritative_row(row) for row in second.rows)
    ):
        return False
    return True


def _has_rejected_complete_duplicate_pair(
    candidates: tuple[TableCandidate, ...],
) -> bool:
    if len(candidates) != 2:
        return False
    first, second = candidates
    if not _has_complete_duplicate_structure(first, second) or not _has_same_complete_duplicate_schedules(
        first, second
    ):
        return False
    return (
        _has_non_medication_table_vocabulary(first.rows)
        or _has_non_medication_table_vocabulary(second.rows)
        or not _has_strong_medication_name_majority(first, second)
    )


def _has_same_complete_duplicate_schedules(
    first: TableCandidate,
    second: TableCandidate,
) -> bool:
    return all(
        first_cell is not None
        and second_cell is not None
        and (column != 1 or _is_explicit_dose_quantity(first_cell))
        and (column != 1 or _is_explicit_dose_quantity(second_cell))
        and _same_grounded_field(column, first_cell, second_cell)
        for first_row, second_row in zip(first.rows, second.rows, strict=True)
        for column, (first_cell, second_cell) in enumerate(
            zip(first_row.cells[1:], second_row.cells[1:], strict=True), start=1
        )
    )


def _has_strong_medication_name_majority(
    first: TableCandidate,
    second: TableCandidate,
) -> bool:
    if _has_non_medication_table_vocabulary(first.rows) or _has_non_medication_table_vocabulary(second.rows):
        return False
    strong_rows = 0
    for first_row, second_row in zip(first.rows, second.rows, strict=True):
        first_name = first_row.cells[0]
        second_name = second_row.cells[0]
        if first_name is None or second_name is None:
            return False
        first_plausible = _is_plausible_product_name(first_name.text)
        second_plausible = _is_plausible_product_name(second_name.text)
        if first_plausible or second_plausible:
            strong_rows += 1
            continue
        if _canonical_candidate_name(first_name.text) != _canonical_candidate_name(second_name.text):
            return False
    return strong_rows >= math.ceil(2 * len(first.rows) / 3)


def _bboxes_are_disjoint(first: AxisAlignedBBox, second: AxisAlignedBBox) -> bool:
    return (
        first.x_max <= second.x_min
        or second.x_max <= first.x_min
        or first.y_max <= second.y_min
        or second.y_max <= first.y_min
    )


def _strict_complete_duplicate_name_pair(
    first: LayoutCell,
    second: LayoutCell,
    first_rows: tuple[LayoutRow, ...],
    second_rows: tuple[LayoutRow, ...],
) -> bool:
    if _canonical_candidate_name(first.text) == _canonical_candidate_name(second.text):
        return True
    return _is_unique_strict_truncated_name_extension(
        first,
        second,
        second_rows,
    ) or _is_unique_strict_truncated_name_extension(second, first, first_rows)


def _complete_duplicate_primary_key(candidate: TableCandidate) -> tuple[object, ...]:
    area = candidate.bbox.width * candidate.bbox.height
    mean_confidence = candidate.mean_confidence if candidate.mean_confidence is not None else -1.0
    return (
        -candidate.observed_header_coverage,
        candidate.header_inferred,
        -area,
        -candidate.bbox.width,
        -candidate.column_consistency,
        -candidate.confidence_coverage,
        -mean_confidence,
        candidate.bbox.y_min,
        candidate.bbox.x_min,
        candidate.source_block_ids,
    )


def _complete_correlated_duplicate_with_name_donor(
    primary: TableCandidate,
    donor: TableCandidate,
) -> TableCandidate:
    rows: list[LayoutRow] = []
    changed = False
    for primary_row, donor_row in zip(primary.rows, donor.rows, strict=True):
        primary_name = primary_row.cells[0]
        donor_name = donor_row.cells[0]
        if (
            primary_name is not None
            and donor_name is not None
            and _is_unique_strict_truncated_name_extension(
                primary_name,
                donor_name,
                donor.rows,
            )
        ):
            cells = (
                donor_name,
                primary_row.cells[1],
                primary_row.cells[2],
                primary_row.cells[3],
            )
            rows.append(
                LayoutRow(
                    row_id=primary_row.row_id,
                    cells=cells,
                    bbox=_bbox_union(cell.bbox for cell in cells if cell is not None),
                )
            )
            changed = True
        else:
            rows.append(primary_row)
    if not changed:
        return primary
    return replace(
        primary,
        rows=tuple(rows),
        bbox=_bbox_union((primary.bbox, *(row.bbox for row in rows))),
    )


def _select_correlated_truncated_name_candidate(
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate | None:
    if len(candidates) != 2:
        return None
    completed = tuple(
        candidate
        for selected, donor in (candidates, tuple(reversed(candidates)))
        if (candidate := _complete_truncated_names_from_lower_receipt(selected, donor)) is not None
    )
    return completed[0] if len(completed) == 1 else None


def _select_candidate_with_sparse_correlated_duplicate(
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate | None:
    if len(candidates) != 2:
        return None
    selected = tuple(
        primary
        for primary, duplicate in (candidates, tuple(reversed(candidates)))
        if _corroborated_sparse_duplicate(primary, duplicate)
    )
    return selected[0] if len(selected) == 1 else None


def _has_conflicting_near_duplicate_names(
    candidates: tuple[TableCandidate, ...],
) -> bool:
    if len(candidates) != 2:
        return False
    return any(
        _is_nearly_complete_correlated_duplicate(primary, duplicate)
        and sum(
            duplicate_row.cells[0] is not None
            and (
                primary_row.cells[0] is None
                or not _compatible_duplicate_name(
                    primary_row.cells[0].text,
                    duplicate_row.cells[0].text,
                )
            )
            and (primary_row.cells[0] is None or not _has_imprint_name_contamination(primary_row.cells[0].text))
            for primary_row, duplicate_row in zip(
                primary.rows,
                duplicate.rows,
                strict=True,
            )
        )
        >= 1
        for primary, duplicate in (candidates, tuple(reversed(candidates)))
    )


def _corroborated_sparse_duplicate(
    primary: TableCandidate,
    duplicate: TableCandidate,
) -> bool:
    if not _is_nearly_complete_correlated_duplicate(primary, duplicate):
        return False

    observed_names: list[str] = []
    for primary_row, duplicate_row in zip(primary.rows, duplicate.rows, strict=True):
        primary_name = primary_row.cells[0]
        duplicate_name = duplicate_row.cells[0]
        if primary_name is None:
            return False
        if duplicate_name is None:
            continue
        if not _compatible_duplicate_name(primary_name.text, duplicate_name.text):
            return False
        observed_names.append(_canonical_candidate_name(duplicate_name.text))
    return len(observed_names) >= 2 and _unique_nonempty_names(tuple(observed_names))


def _is_nearly_complete_correlated_duplicate(
    primary: TableCandidate,
    duplicate: TableCandidate,
) -> bool:
    if (
        primary.ambiguous_column_evidence
        or duplicate.ambiguous_column_evidence
        or len(primary.rows) != len(duplicate.rows)
        or len(primary.rows) < 3
        or not all(_is_complete_authoritative_row(row) for row in primary.rows)
        or not (primary.bbox.x_max < duplicate.bbox.x_min or duplicate.bbox.x_max < primary.bbox.x_min)
    ):
        return False
    primary_names = tuple(
        _canonical_candidate_name(row.cells[0].text) for row in primary.rows if row.cells[0] is not None
    )
    if len(primary_names) != len(primary.rows) or not _unique_nonempty_names(primary_names):
        return False

    invalid_duplicate_doses = 0
    for primary_row, duplicate_row in zip(primary.rows, duplicate.rows, strict=True):
        primary_dose, primary_times, primary_days = primary_row.cells[1:]
        duplicate_dose, duplicate_times, duplicate_days = duplicate_row.cells[1:]
        if (
            primary_dose is None
            or not _is_explicit_dose_quantity(primary_dose)
            or primary_times is None
            or duplicate_times is None
            or primary_days is None
            or duplicate_days is None
            or not _same_grounded_field(2, primary_times, duplicate_times)
            or not _same_grounded_field(3, primary_days, duplicate_days)
        ):
            return False
        if not _is_explicit_dose_quantity(duplicate_dose):
            invalid_duplicate_doses += 1
            if invalid_duplicate_doses > 1:
                return False
        elif duplicate_dose is None or not _same_grounded_field(
            1,
            primary_dose,
            duplicate_dose,
        ):
            return False
    return True


def _is_explicit_dose_quantity(cell: LayoutCell | None) -> bool:
    if cell is None:
        return False
    normalized = normalize_dose_unit_ocr(cell.parsed_text or cell.text)
    return _POSITIVE_DOSE_QUANTITY_PATTERN.fullmatch(normalized) is not None


def _complete_truncated_names_from_lower_receipt(
    selected: TableCandidate,
    donor: TableCandidate,
) -> TableCandidate | None:
    if (
        selected.ambiguous_column_evidence
        or donor.ambiguous_column_evidence
        or donor.bbox.y_min <= selected.bbox.y_min
        or len(selected.rows) != len(donor.rows)
        or len(selected.rows) < 3
        or not all(_is_complete_authoritative_row(row) for row in selected.rows)
        or not all(_is_complete_authoritative_row(row) for row in donor.rows)
    ):
        return None
    selected_names = _normalized_row_names(selected.rows)
    donor_names = _normalized_row_names(donor.rows)
    if (
        len(selected_names) != len(selected.rows)
        or len(donor_names) != len(donor.rows)
        or not _unique_nonempty_names(selected_names)
        or not _unique_nonempty_names(donor_names)
        or not _has_strong_medication_name_majority(selected, donor)
    ):
        return None
    exact_name_anchors = sum(
        selected_name == donor_name for selected_name, donor_name in zip(selected_names, donor_names, strict=True)
    )
    if exact_name_anchors < 2:
        return None
    rows: list[LayoutRow] = []
    changed = False
    for selected_row, donor_row in zip(selected.rows, donor.rows, strict=True):
        if any(
            not _same_grounded_field(column, selected_cell, donor_cell)
            for column, (selected_cell, donor_cell) in enumerate(
                zip(selected_row.cells[1:], donor_row.cells[1:], strict=True), start=1
            )
            if selected_cell is not None and donor_cell is not None
        ):
            return None
        selected_name = selected_row.cells[0]
        donor_name = donor_row.cells[0]
        if selected_name is None or donor_name is None:
            return None
        if _canonical_candidate_name(selected_name.text) == _canonical_candidate_name(donor_name.text):
            rows.append(selected_row)
            continue
        if not _is_unique_strict_truncated_name_extension(selected_name, donor_name, donor.rows):
            return None
        cells = (
            donor_name,
            selected_row.cells[1],
            selected_row.cells[2],
            selected_row.cells[3],
        )
        rows.append(
            LayoutRow(
                row_id=selected_row.row_id,
                cells=cells,
                bbox=_bbox_union(cell.bbox for cell in cells if cell is not None),
            )
        )
        changed = True
    if not changed:
        return None
    return replace(
        selected,
        rows=tuple(rows),
        bbox=_bbox_union((selected.bbox, *(row.bbox for row in rows))),
    )


def _merge_correlated_duplicate(
    donor: TableCandidate,
    base: TableCandidate,
) -> TableCandidate | None:
    if (
        donor.ambiguous_column_evidence
        or base.ambiguous_column_evidence
        or len(donor.rows) != len(base.rows)
        or len(donor.rows) < 2
        or not all(_is_complete_authoritative_row(row) for row in donor.rows)
        or not any(cell is None or not cell.text for row in base.rows for cell in row.cells[1:])
    ):
        return None
    exact_names = tuple(
        _canonical_candidate_name(donor_row.cells[0].text) == _canonical_candidate_name(base_row.cells[0].text)
        if donor_row.cells[0] is not None and base_row.cells[0] is not None
        else False
        for donor_row, base_row in zip(donor.rows, base.rows, strict=True)
    )
    if sum(exact_names) < 2:
        return None
    rows: list[LayoutRow] = []
    for exact_name, donor_row, base_row in zip(
        exact_names,
        donor.rows,
        base.rows,
        strict=True,
    ):
        if base_row.cells[0] is None:
            return None
        merged_cells: list[LayoutCell | None] = [base_row.cells[0]]
        for column, (donor_cell, base_cell) in enumerate(
            zip(donor_row.cells[1:], base_row.cells[1:], strict=True),
            start=1,
        ):
            if donor_cell is None:
                return None
            if base_cell is not None and not _same_grounded_field(
                column,
                donor_cell,
                base_cell,
            ):
                return None
            if base_cell is None and not exact_name:
                return None
            merged_cells.append(base_cell or donor_cell)
        present = tuple(cell for cell in merged_cells if cell is not None)
        rows.append(
            LayoutRow(
                row_id=f"row-{len(rows) + 1:04d}",
                cells=(
                    merged_cells[0],
                    merged_cells[1],
                    merged_cells[2],
                    merged_cells[3],
                ),
                bbox=_bbox_union(cell.bbox for cell in present),
            )
        )
    if (donor.bbox.y_min, donor.bbox.x_min) < (base.bbox.y_min, base.bbox.x_min):
        return donor
    return replace(
        base,
        rows=tuple(rows),
        bbox=_bbox_union((base.bbox, *(row.bbox for row in rows))),
    )


def _merge_correlated_summary_rows(
    main_rows: tuple[LayoutRow, ...],
    summary_rows: tuple[LayoutRow, ...],
) -> tuple[LayoutRow, ...]:
    if (
        len(main_rows) < 3
        or len(summary_rows) != len(main_rows)
        or any(row.cells[3] is not None for row in summary_rows)
    ):
        return main_rows
    main_names = tuple(_canonical_candidate_name(row.cells[0].text) for row in main_rows if row.cells[0] is not None)
    summary_names = tuple(
        _canonical_candidate_name(row.cells[0].text) for row in summary_rows if row.cells[0] is not None
    )
    if (
        len(main_names) != len(main_rows)
        or len(summary_names) != len(summary_rows)
        or not _unique_nonempty_names(main_names)
        or not _unique_nonempty_names(summary_names)
    ):
        return main_rows

    repair_indices = tuple(
        index
        for index, row in enumerate(main_rows)
        if row.cells[3] is not None
        and (row.cells[1] is None or not row.cells[1].text or row.cells[2] is None or not row.cells[2].text)
    )
    if len(repair_indices) != 1:
        return main_rows
    supporting_indices = tuple(index for index in range(len(main_rows)) if index not in repair_indices)
    if len(supporting_indices) < 2:
        return main_rows
    if not all(
        _compatible_duplicate_name(main_names[index], summary_names[index]) for index in supporting_indices
    ) or not any(main_names[index] == summary_names[index] for index in supporting_indices):
        return main_rows
    for index, (main, summary) in enumerate(zip(main_rows, summary_rows, strict=True)):
        summary_dose = summary.cells[1]
        summary_times = summary.cells[2]
        if (
            summary_dose is None
            or not summary_dose.text
            or summary_times is None
            or parse_times_per_day(summary_times.text) is None
        ):
            return main_rows
        if index in repair_indices:
            continue
        main_dose = main.cells[1]
        main_times = main.cells[2]
        if (
            main_dose is None
            or main_times is None
            or not _same_grounded_field(1, main_dose, summary_dose)
            or not _same_grounded_field(2, main_times, summary_times)
        ):
            return main_rows

    repaired: list[LayoutRow] = []
    for index, (main, summary) in enumerate(zip(main_rows, summary_rows, strict=True)):
        if index not in repair_indices:
            repaired.append(main)
            continue
        cells: tuple[
            LayoutCell | None,
            LayoutCell | None,
            LayoutCell | None,
            LayoutCell | None,
        ] = (
            summary.cells[0],
            summary.cells[1],
            summary.cells[2],
            main.cells[3],
        )
        present = tuple(cell for cell in cells if cell is not None)
        repaired.append(
            LayoutRow(
                row_id=main.row_id,
                cells=cells,
                bbox=_bbox_union(cell.bbox for cell in present),
            )
        )
    return tuple(repaired)


def _merge_grounded_guidance_rows(
    selected: TableCandidate,
    guidance_rows: tuple[LayoutRow, ...],
) -> tuple[tuple[LayoutRow, ...], bool, bool]:
    receipt_rows = selected.rows
    if selected.ambiguous_column_evidence or len(receipt_rows) < 2 or len(guidance_rows) != len(receipt_rows):
        return receipt_rows, False, False
    receipt_names = _normalized_row_names(receipt_rows)
    guidance_names = _normalized_row_names(guidance_rows)
    if (
        len(receipt_names) != len(receipt_rows)
        or len(guidance_names) != len(guidance_rows)
        or not _unique_nonempty_names(receipt_names)
        or not _unique_nonempty_names(guidance_names)
    ):
        return receipt_rows, False, False
    if not all(
        _grounded_name_contains(guidance.cells[0], receipt.cells[0])
        for receipt, guidance in zip(receipt_rows, guidance_rows, strict=True)
    ):
        return receipt_rows, False, False
    exact_name_matches = sum(
        _normalized_candidate_name(guidance.cells[0].text) == _normalized_candidate_name(receipt.cells[0].text)
        for receipt, guidance in zip(receipt_rows, guidance_rows, strict=True)
        if receipt.cells[0] is not None and guidance.cells[0] is not None
    )
    if exact_name_matches == 0:
        return receipt_rows, False, False

    merged: list[LayoutRow] = []
    observed_guidance_conflict = False
    for receipt_row, guidance_row in zip(receipt_rows, guidance_rows, strict=True):
        receipt_name = receipt_row.cells[0]
        guidance_name = guidance_row.cells[0]
        exact_name = (
            receipt_name is not None
            and guidance_name is not None
            and _normalized_candidate_name(receipt_name.text) == _normalized_candidate_name(guidance_name.text)
        )
        observed_guidance_conflict = observed_guidance_conflict or (
            exact_name and _has_conflicting_grounded_fields(receipt_row, guidance_row)
        )
        cells = _merge_grounded_row(
            receipt_row,
            guidance_row,
            preserve_observed_conflicts=exact_name,
        )
        if cells is None:
            return receipt_rows, True, False
        present_cells = tuple(cell for cell in cells if cell is not None)
        merged.append(
            LayoutRow(
                row_id=f"row-{len(merged) + 1:04d}",
                cells=cells,
                bbox=_bbox_union(cell.bbox for cell in present_cells),
            )
        )
    return tuple(merged), False, observed_guidance_conflict


def _normalized_row_names(rows: tuple[LayoutRow, ...]) -> tuple[str, ...]:
    return tuple(_normalized_candidate_name(row.cells[0].text) for row in rows if row.cells[0] is not None)


def _unique_nonempty_names(names: tuple[str, ...]) -> bool:
    return bool(all(names)) and len(set(names)) == len(names)


def _has_conflicting_grounded_fields(receipt: LayoutRow, guidance: LayoutRow) -> bool:
    return any(
        receipt_cell is not None
        and guidance_cell is not None
        and not _same_grounded_field(column, receipt_cell, guidance_cell)
        for column, (receipt_cell, guidance_cell) in enumerate(
            zip(receipt.cells[1:], guidance.cells[1:], strict=True),
            start=1,
        )
    )


def _grounded_name_contains(
    guidance: LayoutCell | None,
    receipt: LayoutCell | None,
) -> bool:
    if guidance is None or receipt is None:
        return False
    guidance_name = _normalized_candidate_name(guidance.text)
    receipt_name = _normalized_candidate_name(receipt.text)
    if not guidance_name or not receipt_name:
        return False
    if guidance_name == receipt_name:
        return True
    if len(receipt_name) >= 3 and guidance_name.startswith(receipt_name):
        if _TRAILING_STRENGTH_PATTERN.fullmatch(guidance_name[len(receipt_name) :]) is not None:
            return True
    return _is_unique_whitespace_token_match(guidance.text, receipt.text)


def _is_unique_whitespace_token_match(guidance_text: str, receipt_text: str) -> bool:
    guidance_tokens = _normalized_name_tokens(guidance_text)
    receipt_tokens = _normalized_name_tokens(receipt_text)
    return (
        len(guidance_tokens) == 1
        and len(guidance_tokens[0]) >= 4
        and len(receipt_tokens) >= 2
        and receipt_tokens.count(guidance_tokens[0]) == 1
    )


def _normalized_name_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for token in unicodedata.normalize("NFKC", text).split()
        if (normalized := _normalized_candidate_name(token))
    )


def _merge_grounded_row(
    receipt: LayoutRow,
    guidance: LayoutRow,
    *,
    preserve_observed_conflicts: bool,
) -> (
    tuple[
        LayoutCell | None,
        LayoutCell | None,
        LayoutCell | None,
        LayoutCell | None,
    ]
    | None
):
    if not _grounded_name_contains(guidance.cells[0], receipt.cells[0]):
        return None
    receipt_name = receipt.cells[0]
    guidance_name = guidance.cells[0]
    if receipt_name is None or guidance_name is None:
        return None
    merged_name = (
        guidance_name
        if len(_normalized_candidate_name(guidance_name.text)) > len(_normalized_candidate_name(receipt_name.text))
        else receipt_name
    )
    merged: list[LayoutCell | None] = [merged_name]
    for column, (receipt_cell, guidance_cell) in enumerate(
        zip(receipt.cells[1:], guidance.cells[1:], strict=True),
        start=1,
    ):
        if receipt_cell is not None and guidance_cell is not None:
            if not preserve_observed_conflicts and not _same_grounded_field(column, receipt_cell, guidance_cell):
                return None
            merged.append(receipt_cell)
        else:
            merged.append(receipt_cell or guidance_cell)
    return merged[0], merged[1], merged[2], merged[3]


def _same_grounded_field(
    column: int,
    receipt: LayoutCell,
    guidance: LayoutCell,
) -> bool:
    if column == 1:
        receipt_value, receipt_unit = dose_quantity_value_and_unit(receipt.text)
        guidance_value, guidance_unit = dose_quantity_value_and_unit(guidance.text)
        return receipt_value == guidance_value and (
            receipt_unit is None or guidance_unit is None or receipt_unit == guidance_unit
        )
    if column == 2:
        receipt_integer = parse_times_per_day(receipt.text)
        guidance_integer = parse_times_per_day(guidance.text)
    else:
        receipt_integer = parse_days(receipt.text)
        guidance_integer = parse_days(guidance.text)
    return receipt_integer is not None and guidance_integer is not None and receipt_integer == guidance_integer


def _candidate_dominates(primary: TableCandidate, partial: TableCandidate) -> bool:
    if primary.ambiguous_column_evidence or partial.ambiguous_column_evidence:
        return False
    if len(primary.rows) != len(partial.rows) or len(primary.rows) < 2:
        return False
    if not all(_is_complete_authoritative_row(row) for row in primary.rows):
        return False
    if not any(cell is None or not cell.text for row in partial.rows for cell in row.cells[1:]):
        return False
    primary_names = tuple(
        _canonical_candidate_name(row.cells[0].text) for row in primary.rows if row.cells[0] is not None
    )
    if len(primary_names) != len(primary.rows) or len(set(primary_names)) != len(primary_names):
        return False
    partial_names = tuple(
        _canonical_candidate_name(row.cells[0].text) for row in partial.rows if row.cells[0] is not None
    )
    if len(partial_names) != len(partial.rows) or len(set(partial_names)) != len(partial_names):
        return False
    name_similarities: list[float] = []
    exact_name_matches = 0
    all_names_compatible = True
    incompatible_name_count = 0
    for primary_row, partial_row in zip(primary.rows, partial.rows, strict=True):
        primary_name = primary_row.cells[0]
        partial_name = partial_row.cells[0]
        if primary_name is None or partial_name is None:
            return False
        recoverable_missing_prefix = not _canonical_name_value(primary_name.text) and _is_plausible_product_name(
            partial_name.text
        )
        compatible_name = recoverable_missing_prefix or _compatible_duplicate_name(
            primary_name.text,
            partial_name.text,
        )
        all_names_compatible = all_names_compatible and compatible_name
        incompatible_name_count += not compatible_name
        primary_normalized = _canonical_candidate_name(primary_name.text)
        partial_normalized = _canonical_candidate_name(partial_name.text)
        if primary_normalized == partial_normalized:
            exact_name_matches += 1
        name_similarities.append(
            1.0
            if recoverable_missing_prefix
            else SequenceMatcher(
                None,
                primary_normalized,
                partial_normalized,
                autojunk=False,
            ).ratio()
        )
        for column, (primary_cell, partial_cell) in enumerate(
            zip(primary_row.cells[1:], partial_row.cells[1:], strict=True),
            start=1,
        ):
            if partial_cell is not None and (
                primary_cell is None or not _same_grounded_field(column, primary_cell, partial_cell)
            ):
                return False
    standard_duplicate = (
        all_names_compatible
        and exact_name_matches >= 1
        and sum(name_similarities) / len(name_similarities) >= _DUPLICATE_NAME_MEAN_SIMILARITY
    )
    anchored_summary = (
        len(primary.rows) >= 3
        and exact_name_matches >= 2
        and incompatible_name_count >= 2
        and (primary.bbox.x_max < partial.bbox.x_min or partial.bbox.x_max < primary.bbox.x_min)
    )
    return standard_duplicate or anchored_summary


def _refine_correlated_receipt_names(
    selected: TableCandidate,
    candidates: tuple[TableCandidate, ...],
) -> TableCandidate:
    donors = tuple(
        candidate for candidate in candidates if candidate is not selected and _candidate_dominates(selected, candidate)
    )
    if len(donors) != 1:
        return selected
    donor = donors[0]
    can_complete_truncated_names = _has_unambiguous_truncated_name_alignment(
        selected,
        donor,
    )
    rows: list[LayoutRow] = []
    changed = False
    for selected_row, donor_row in zip(selected.rows, donor.rows, strict=True):
        selected_name = selected_row.cells[0]
        donor_name = donor_row.cells[0]
        if (
            selected_name is not None
            and donor_name is not None
            and _is_plausible_product_name(donor_name.text)
            and (
                _has_imprint_name_contamination(selected_name.text)
                or (not _canonical_name_value(selected_name.text) and bool(_canonical_name_value(donor_name.text)))
            )
        ):
            cells = (
                donor_name,
                selected_row.cells[1],
                selected_row.cells[2],
                selected_row.cells[3],
            )
            present = tuple(cell for cell in cells if cell is not None)
            rows.append(
                LayoutRow(
                    row_id=selected_row.row_id,
                    cells=cells,
                    bbox=_bbox_union(cell.bbox for cell in present),
                )
            )
            changed = True
        elif (
            can_complete_truncated_names
            and selected_name is not None
            and donor_name is not None
            and _is_unique_strict_truncated_name_extension(
                selected_name,
                donor_name,
                donor.rows,
            )
        ):
            cells = (
                donor_name,
                selected_row.cells[1],
                selected_row.cells[2],
                selected_row.cells[3],
            )
            present = tuple(cell for cell in cells if cell is not None)
            rows.append(
                LayoutRow(
                    row_id=selected_row.row_id,
                    cells=cells,
                    bbox=_bbox_union(cell.bbox for cell in present),
                )
            )
            changed = True
        else:
            rows.append(selected_row)
    if not changed:
        return selected
    return replace(
        selected,
        rows=tuple(rows),
        bbox=_bbox_union((selected.bbox, *(row.bbox for row in rows))),
    )


def _has_unambiguous_truncated_name_alignment(
    selected: TableCandidate,
    donor: TableCandidate,
) -> bool:
    if donor.bbox.y_min <= selected.bbox.y_min:
        return False
    exact_name_anchors = sum(
        _canonical_candidate_name(selected_row.cells[0].text) == _canonical_candidate_name(donor_row.cells[0].text)
        for selected_row, donor_row in zip(selected.rows, donor.rows, strict=True)
        if selected_row.cells[0] is not None and donor_row.cells[0] is not None
    )
    return exact_name_anchors >= 2


def _is_unique_strict_truncated_name_extension(
    selected_name: LayoutCell,
    donor_name: LayoutCell,
    donor_rows: tuple[LayoutRow, ...],
) -> bool:
    prefix = _explicit_truncation_prefix(selected_name.text)
    donor_normalized = _canonical_candidate_name(donor_name.text)
    if not prefix or not donor_normalized.startswith(prefix) or len(donor_normalized) <= len(prefix):
        return False
    return (
        sum(
            _canonical_candidate_name(candidate.cells[0].text).startswith(prefix)
            for candidate in donor_rows
            if candidate.cells[0] is not None
        )
        == 1
    )


def _explicit_truncation_prefix(text: str) -> str | None:
    normalized = "".join(unicodedata.normalize("NFKC", text).split())
    truncation = re.search(r"(?:\.{3,}|·{3,}|…|⋯)", normalized)
    if truncation is not None:
        prefix = normalized[: truncation.start()]
    elif normalized.endswith("-") and len(normalized) > 1:
        prefix = normalized[:-1]
    else:
        return None
    canonical_prefix = _canonical_candidate_name(prefix)
    return canonical_prefix if len(canonical_prefix) >= _MIN_TRUNCATED_NAME_PREFIX_LENGTH else None


def _has_imprint_name_contamination(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text)
    return "[앞]" in normalized and "[뒤]" in normalized


def _is_plausible_product_name(text: str) -> bool:
    normalized = _canonical_candidate_name(text)
    trailing_parenthetical = _TRAILING_PARENTHETICAL_PATTERN.fullmatch(normalized)
    if (
        trailing_parenthetical is not None
        and _PACKAGE_SIZE_PARENTHETICAL_PATTERN.fullmatch(trailing_parenthetical.group("content")) is not None
    ):
        normalized = trailing_parenthetical.group("base")
    return (
        bool(normalized)
        and not _has_imprint_name_contamination(text)
        and _PRODUCT_NAME_PATTERN.fullmatch(normalized) is not None
    )


def _has_non_medication_table_vocabulary(rows: tuple[LayoutRow, ...]) -> bool:
    return any(
        name is not None
        and (
            _canonical_candidate_name(name.text) == "품목"
            or _NON_MEDICATION_TABLE_VOCABULARY_PATTERN.search(_canonical_candidate_name(name.text)) is not None
        )
        for row in rows
        if (name := row.cells[0]) is not None
    )


def _is_semantically_eligible_medication_candidate(candidate: TableCandidate) -> bool:
    """Require dose-schedule evidence and reject known non-medical table language."""

    return not _has_non_medication_table_vocabulary(candidate.rows) and (
        _has_independent_medication_evidence(candidate.rows) or _has_unresolved_medication_evidence(candidate.rows)
    )


def _has_independent_medication_evidence(rows: tuple[LayoutRow, ...]) -> bool:
    return any(
        dose is not None
        and bool(dose.text)
        and times is not None
        and parse_times_per_day(times.text) is not None
        and days is not None
        and parse_days(days.text) is not None
        for _, dose, times, days in (row.cells for row in rows)
    )


def _has_unresolved_medication_evidence(rows: tuple[LayoutRow, ...]) -> bool:
    return any(
        dose is None
        or not dose.text
        or times is None
        or parse_times_per_day(times.text) is None
        or days is None
        or parse_days(days.text) is None
        for _, dose, times, days in (row.cells for row in rows)
    )


def _is_complete_authoritative_row(row: LayoutRow) -> bool:
    name, dose, times, days = row.cells
    return (
        name is not None
        and bool(name.text)
        and dose is not None
        and bool(dose.text)
        and times is not None
        and parse_times_per_day(times.text) is not None
        and days is not None
        and parse_days(days.text) is not None
    )


def _compatible_duplicate_name(first: str, second: str) -> bool:
    first_normalized = _canonical_candidate_name(first)
    second_normalized = _canonical_candidate_name(second)
    if not first_normalized or not second_normalized:
        return False
    if first_normalized == second_normalized:
        return True
    if min(len(first_normalized), len(second_normalized)) < 4:
        return False
    return (
        SequenceMatcher(None, first_normalized, second_normalized, autojunk=False).ratio() >= _DUPLICATE_NAME_SIMILARITY
    )


def _canonical_candidate_name(text: str) -> str:
    return _normalized_candidate_name(_canonical_name_value(text))


def _normalized_candidate_name(text: str) -> str:
    normalized = "".join(unicodedata.normalize("NFKC", text).split())
    return normalized.rstrip(".…⋯")


def _candidate_signature(
    candidate: TableCandidate,
) -> tuple[object, ...]:
    row_signature = tuple(
        (
            row.cells[0].text if row.cells[0] is not None else None,
            row.cells[1].text if row.cells[1] is not None else None,
            row.cells[2].text if row.cells[2] is not None else None,
            row.cells[3].text if row.cells[3] is not None else None,
        )
        for row in candidate.rows
    )
    ambiguous_signature = tuple(
        (
            evidence.nearest_row_index,
            evidence.overlapping_columns,
            evidence.source_text,
        )
        for evidence in candidate.ambiguous_column_evidence
    )
    return row_signature, ambiguous_signature


def _representative_key(candidate: TableCandidate) -> tuple[object, ...]:
    populated_fields = sum(cell is not None and bool(cell.text) for row in candidate.rows for cell in row.cells)
    complete_rows = sum(all(cell is not None and bool(cell.text) for cell in row.cells) for row in candidate.rows)
    mean_confidence = candidate.mean_confidence
    return (
        -4,
        -populated_fields,
        -complete_rows,
        -candidate.column_consistency,
        -candidate.confidence_coverage,
        -(mean_confidence if mean_confidence is not None else -1.0),
        candidate.bbox.y_min,
        candidate.bbox.x_min,
        candidate.source_block_ids,
    )


def _medication_row(row: LayoutRow) -> MedicationRow:
    name_cell = row.cells[0]
    if name_cell is None or not name_cell.text:
        raise ValueError("Medication rows require grounded name evidence.")
    name = _name_field(name_cell)
    dose = _dose_field(row.cells[1])
    times = _numeric_field(row.cells[2], _TIMES_PATTERN)
    days = _numeric_field(row.cells[3], _DAYS_PATTERN)
    fields = MedicationFields(
        name=name,
        dose_quantity=dose,
        times_per_day=times,
        days=days,
    )
    incomplete = dose.value == "" or times.value is None or days.value is None
    row_issues: list[MedicationIssueCode] = []
    if incomplete:
        row_issues.append(MedicationIssueCode.INCOMPLETE_MEDICATION_ROW)
    row_issues.extend(issue for field in fields.as_tuple() for issue in field.issues)
    confidence_sum = 0.0
    confidence_count = 0
    for cell in row.cells:
        if cell is None or cell.confidence is None:
            continue
        confidence_sum += cell.confidence * cell.valid_confidence_count
        confidence_count += cell.valid_confidence_count
    return MedicationRow(
        name=str(name.value),
        dose_quantity=dose.value if isinstance(dose.value, str) else "",
        times_per_day=times.value if isinstance(times.value, int) else None,
        days=days.value if isinstance(days.value, int) else None,
        confidence=confidence_sum / confidence_count if confidence_count else None,
        bbox=row.bbox,
        fields=fields,
        issues=tuple(dict.fromkeys(row_issues)),
    )


def _name_field(cell: LayoutCell) -> MedicationField:
    return MedicationField(
        value=_canonical_name_value(cell.text),
        source_text=cell.text,
        block_ids=cell.block_ids,
        bbox=cell.bbox,
        confidence=cell.confidence,
        issues=_cell_diagnostics(cell),
    )


def _canonical_name_value(text: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", text).split()).replace("_", "")
    normalized = re.sub(r"^[·*+•]+\s*", "", normalized)
    normalized = re.sub(r"^(?:[A-Z0-9]{1,3}\s+)+(?=[가-힣])", "", normalized)
    normalized = re.sub(r"^비\)\s*", "", normalized)
    normalized = re.sub(r"\s+(?=\()", "", normalized)
    truncation = re.search(r"(?:\.{3,}|·{3,}|…|⋯)", normalized)
    if truncation is not None:
        normalized = f"{normalized[: truncation.start()].rstrip()}..."
    elif normalized.endswith("-") and len(normalized) > 1:
        normalized = f"{normalized[:-1].rstrip()}..."
    opening = normalized.find("(")
    if opening < 0:
        return _strip_trailing_name_schedule_token(_strip_form_descriptor(normalized))
    package_with_labels = _PACKAGE_WITH_TRAILING_LABELS_PATTERN.fullmatch(normalized)
    if (
        package_with_labels is not None
        and _PACKAGE_SIZE_PARENTHETICAL_PATTERN.fullmatch(package_with_labels.group("content")) is not None
    ):
        return (
            f"{_strip_form_descriptor(package_with_labels.group('base').rstrip())}"
            f"({package_with_labels.group('content')})"
        )
    match = _TRAILING_PARENTHETICAL_PATTERN.fullmatch(normalized)
    if match is not None and _PACKAGE_SIZE_PARENTHETICAL_PATTERN.fullmatch(match.group("content")) is not None:
        return normalized
    return _strip_trailing_name_schedule_token(_strip_form_descriptor(normalized[:opening].rstrip()))


def _strip_trailing_name_schedule_token(value: str) -> str:
    match = _TRAILING_NAME_STRENGTH_TOKEN_PATTERN.fullmatch(value) or _TRAILING_NAME_DOSE_TOKEN_PATTERN.fullmatch(value)
    if match is None:
        return value
    name = match.group("name").rstrip()
    compact_name = "".join(unicodedata.normalize("NFKC", name).split())
    return name if _PRODUCT_NAME_PATTERN.fullmatch(compact_name) is not None else value


def _strip_form_descriptor(value: str) -> str:
    colors = "흰색|백색|적갈색|갈색|노란색|황색|녹색|분홍색|주황색|청색|회색|적색|연두색"
    return re.sub(
        rf"\s+(?:{colors})\s+(?:정제|캡슐)(?:\s.*)?$",
        "",
        value,
    ).rstrip()


def _dose_field(cell: LayoutCell | None) -> MedicationField:
    if cell is None or not cell.text:
        return _missing_field("")
    parsed_text = cell.parsed_text or cell.text
    normalized = normalize_dose_unit_ocr(parsed_text)
    issues = list(_cell_diagnostics(cell))
    value: str | None = _canonical_dose_value(parsed_text)
    if _ZERO_DOSE_QUANTITY_PATTERN.fullmatch(normalized) is not None:
        value = None
        issues.insert(0, MedicationIssueCode.INVALID_FIELD_VALUE)
    return MedicationField(
        value=value,
        source_text=cell.text,
        block_ids=cell.block_ids,
        bbox=cell.bbox,
        confidence=cell.confidence,
        issues=tuple(dict.fromkeys(issues)),
    )


def _canonical_dose_value(text: str) -> str:
    value, unit = dose_quantity_value_and_unit(text)
    return f"{value}{unit}" if unit in {"포", "mL", "mℓ"} else value


def dose_quantity_value_and_unit(text: str) -> tuple[str, str | None]:
    """Return the grounded one-time quantity and its explicit dosage-form unit."""

    normalized = normalize_dose_unit_ocr(text)
    match = _POSITIVE_DOSE_QUANTITY_PATTERN.fullmatch(normalized)
    if match is None:
        dose_text, separator, schedule = normalized.partition("씩")
        if separator and _COMBINED_SCHEDULE_SUFFIX_PATTERN.fullmatch(schedule):
            match = _POSITIVE_DOSE_QUANTITY_PATTERN.fullmatch(dose_text)
    if match is None:
        return normalized, None
    unit = match.group("unit")
    return match.group("value"), "mL" if unit and unit.lower() == "ml" else unit


def _numeric_field(
    cell: LayoutCell | None,
    pattern: re.Pattern[str],
) -> MedicationField:
    if cell is None or not cell.text:
        return _missing_field(None)
    value, unrepresentable = _parse_json_safe_positive_integer(
        cell.parsed_text or cell.text,
        pattern,
    )
    issues = list(_cell_diagnostics(cell))
    if value is None:
        issues.insert(
            0,
            MedicationIssueCode.UNREPRESENTABLE_POSITIVE_INTEGER
            if unrepresentable
            else MedicationIssueCode.INVALID_POSITIVE_INTEGER,
        )
    return MedicationField(
        value=value,
        source_text=cell.text,
        block_ids=cell.block_ids,
        bbox=cell.bbox,
        confidence=cell.confidence,
        issues=tuple(dict.fromkeys(issues)),
    )


def _missing_field(value: str | None) -> MedicationField:
    return MedicationField(
        value=value,
        source_text="",
        block_ids=(),
        bbox=None,
        confidence=None,
        issues=(MedicationIssueCode.INCOMPLETE_MEDICATION_FIELD,),
    )


def _cell_diagnostics(cell: LayoutCell) -> tuple[MedicationIssueCode, ...]:
    issues: list[MedicationIssueCode] = []
    for source_issue in cell.source_issues:
        if source_issue is OcrBlockIssueCode.INVALID_BLOCK_CONFIDENCE:
            issues.append(MedicationIssueCode.INVALID_BLOCK_CONFIDENCE)
        elif source_issue is OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY:
            issues.append(MedicationIssueCode.INVALID_BLOCK_GEOMETRY)
    if cell.confidence is not None and cell.confidence < _LOW_CONFIDENCE_THRESHOLD:
        issues.append(MedicationIssueCode.LOW_CONFIDENCE)
    return tuple(dict.fromkeys(issues))


def _layout_issues(issues: tuple[LayoutIssue, ...]) -> tuple[MedicationIssue, ...]:
    mapping = {
        LayoutIssueCode.INVALID_BLOCK_GEOMETRY: MedicationIssueCode.INVALID_BLOCK_GEOMETRY,
        LayoutIssueCode.INVALID_BLOCK_CONFIDENCE: MedicationIssueCode.INVALID_BLOCK_CONFIDENCE,
        LayoutIssueCode.AMBIGUOUS_COLUMN_ASSIGNMENT: (MedicationIssueCode.AMBIGUOUS_COLUMN_ASSIGNMENT),
    }
    return tuple(MedicationIssue(mapping[issue.code], issue.block_ids) for issue in issues)


def _deduplicate_medication_issues(
    issues: list[MedicationIssue],
) -> tuple[MedicationIssue, ...]:
    return tuple(dict.fromkeys(issues))


def _bbox_union(boxes: Iterable[AxisAlignedBBox]) -> AxisAlignedBBox:
    materialized = tuple(boxes)
    if not materialized:
        raise ValueError("Cannot union an empty bbox collection.")
    return AxisAlignedBBox(
        min(box.x_min for box in materialized),
        min(box.y_min for box in materialized),
        max(box.x_max for box in materialized),
        max(box.y_max for box in materialized),
    )
