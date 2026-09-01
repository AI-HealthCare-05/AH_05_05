"""Build a deterministic, fail-closed evidence catalog for structured grounding."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services.medication_ocr_v3.domain.grounding import EvidenceBlock, EvidenceCatalog, EvidenceRow
from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline.medication_rows import MedicationRowsResult
from app.services.medication_ocr_v3.pipeline.ocr_layout import (
    AxisAlignedBBox,
    LayoutRow,
    OcrLayoutResult,
    OcrLine,
    group_visual_lines,
)
from app.services.medication_ocr_v3.pipeline.ocr_normalization import normalize_measurement_unit_ocr

_SENSITIVE_LABELS = (
    "환자",
    "성명",
    "주민",
    "전화",
    "연락처",
    "주소",
    "사업자",
    "승인번호",
    "영수증번호",
    "본인부담",
    "보험부담",
    "합계",
    "결제",
    "카드",
    "현금",
)
_PAYMENT_LABELS = ("금액", "소계", "총계", "총액", "청구")
_SECTION_LABELS = (*_SENSITIVE_LABELS, *_PAYMENT_LABELS)
_PHONE_PATTERN = re.compile(r"(?<!\d)0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
_BUSINESS_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{3}[-\s]?\d{2}[-\s]?\d{5}(?!\d)")
_WON_AMOUNT_PATTERN = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})*\s*원(?!\w)|(?<!\d)\d+\s*원(?!\w)")
_DATE_LABEL_GRAMMAR = r"조제\s*일(?:\s*자)?"
_DATE_LABEL_PATTERN = re.compile(_DATE_LABEL_GRAMMAR)
_DATE_LABEL_ONLY_PATTERN = re.compile(r"^" + _DATE_LABEL_GRAMMAR + r"$")
_DATE_VALUE_ONLY_PATTERN = re.compile(r"^\d{2,4}[./-]\d{1,2}[./-]\d{1,2}$")
_DATE_LABEL_AND_VALUE_PATTERN = re.compile(
    r"^" + _DATE_LABEL_GRAMMAR + r"[\s:：,·-]+\d{2,4}[./-]\d{1,2}[./-]\d{1,2}$"
)
_SUMMARY_DOSE_PATTERN = re.compile(
    r"(?:적량|(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+)(?:정|캡슐|포|m[lℓ]))",
    re.IGNORECASE,
)
_SUMMARY_TIMES_PATTERN = re.compile(r"[1-9][0-9]*회")
_SUMMARY_DAYS_PATTERN = re.compile(r"[1-9][0-9]*(?:일|일분)")
_FIELD_ORDER = (
    "name",
    "strength",
    "doseQuantity",
    "timesPerDay",
    "days",
    "dispensedDate",
)
_STRUCTURAL_FIELDS = frozenset(("name", "doseQuantity", "timesPerDay", "days"))
_STRENGTH_PATTERN = re.compile(
    r"[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?"
    r"\s*(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램|마이크로그램|%)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class _BlockAssignment:
    fields: set[str] = field(default_factory=set)
    row_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class _RowSeed:
    row_id: str
    row: LayoutRow
    source: str


@dataclass(frozen=True, slots=True)
class _SourceRow:
    row: LayoutRow
    source: str


def build_evidence_catalog(
    ocr_result: OcrResult,
    layout: OcrLayoutResult,
    medication_rows: MedicationRowsResult,
) -> EvidenceCatalog:
    """Return only structurally anchored, non-sensitive OCR evidence.

    The builder deliberately treats missing geometry, duplicate block identifiers, and
    ambiguous association as absent evidence rather than guessing about them.
    """

    source_by_id, duplicate_ids = _unique_geometry_sources(ocr_result.blocks)
    line_by_block_id, sensitive_block_ids, line_segments = _line_indexes(
        layout, source_by_id
    )
    seeds, supplements = _row_seeds(layout, medication_rows)
    structural_schedule_block_ids = _structural_schedule_block_ids(layout, seeds)
    assignments: dict[str, _BlockAssignment] = defaultdict(_BlockAssignment)

    for seed in seeds:
        _assign_row_cells(
            seed,
            source_by_id,
            duplicate_ids,
            line_by_block_id,
            sensitive_block_ids,
            structural_schedule_block_ids,
            assignments,
        )
    for supplemental in supplements:
        target = _matching_seed(supplemental.row, seeds)
        if target is not None:
            _assign_row_cells(
                target,
                source_by_id,
                duplicate_ids,
                line_by_block_id,
                sensitive_block_ids,
                structural_schedule_block_ids,
                assignments,
                supplemental.row,
                supplemental.source,
            )

    _assign_table_alias_strengths(
        layout,
        seeds,
        source_by_id,
        duplicate_ids,
        line_by_block_id,
        sensitive_block_ids,
        structural_schedule_block_ids,
        assignments,
    )

    geometry_groups = _row_geometry_groups(layout, seeds)
    _assign_standalone_strength_evidence(
        geometry_groups,
        line_segments,
        source_by_id,
        duplicate_ids,
        line_by_block_id,
        sensitive_block_ids,
        structural_schedule_block_ids,
        assignments,
    )
    date_ids = _date_candidate_ids(
        line_segments,
        source_by_id,
        duplicate_ids,
        sensitive_block_ids=set(),
    )
    sensitive_block_ids.difference_update(date_ids)

    candidate_blocks = _evidence_blocks(
        source_by_id,
        duplicate_ids,
        line_by_block_id,
        sensitive_block_ids,
        assignments,
        date_ids,
    )
    evidence_rows = tuple(
        EvidenceRow(
            row_id=seed.row_id,
            bbox=seed.row.bbox,
            block_ids=tuple(
                block.block_id for block in candidate_blocks if seed.row_id in block.row_ids
            )[:96],
        )
        for seed in seeds[:100]
    )
    included_row_ids = {block_id for row in evidence_rows for block_id in row.block_ids}
    included_ids = included_row_ids | set(date_ids)
    blocks = tuple(block for block in candidate_blocks if block.block_id in included_ids)
    blocks_by_id = {block.block_id: block for block in blocks}
    date_candidates = tuple(
        blocks_by_id[block_id] for block_id in date_ids if block_id in blocks_by_id
    )
    return EvidenceCatalog(blocks=blocks, date_candidates=date_candidates, rows=evidence_rows)


def _unique_geometry_sources(
    blocks: tuple[OcrBlock, ...],
) -> tuple[dict[str, tuple[OcrBlock, AxisAlignedBBox]], set[str]]:
    grouped: dict[str, list[tuple[OcrBlock, AxisAlignedBBox]]] = defaultdict(list)
    for block in blocks:
        bbox = _bbox(block)
        if bbox is not None:
            grouped[block.block_id].append((block, bbox))
    duplicate_ids = {block_id for block_id, values in grouped.items() if len(values) != 1}
    return (
        {block_id: values[0] for block_id, values in grouped.items() if len(values) == 1},
        duplicate_ids,
    )


def _bbox(block: OcrBlock) -> AxisAlignedBBox | None:
    if block.bbox is None:
        return None
    values = tuple(value for point in block.bbox for value in (point.x, point.y))
    if not all(math.isfinite(value) for value in values):
        return None
    bbox = AxisAlignedBBox(min(values[::2]), min(values[1::2]), max(values[::2]), max(values[1::2]))
    return bbox if bbox.width > 0.0 and bbox.height > 0.0 else None


def _line_indexes(
    layout: OcrLayoutResult,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
) -> tuple[dict[str, str], set[str], tuple[OcrLine, ...]]:
    line_by_block_id: dict[str, str] = {}
    ambiguous_ids: set[str] = set()
    for line in layout.lines:
        for block_id in line.block_ids:
            if block_id in line_by_block_id:
                ambiguous_ids.add(block_id)
            else:
                line_by_block_id[block_id] = line.line_id
    for block_id in ambiguous_ids:
        line_by_block_id.pop(block_id, None)
    segments = _line_segments(layout.lines, source_by_id)
    sensitive_block_ids = {
        block_id
        for segment in segments
        if _is_sensitive_text(segment.text)
        for block_id in segment.block_ids
    }
    sensitive_block_ids.update(_sensitive_continuation_block_ids(segments))
    return line_by_block_id, sensitive_block_ids, segments


def _line_segments(
    lines: tuple[OcrLine, ...],
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
) -> tuple[OcrLine, ...]:
    segments: list[OcrLine] = []
    for line in lines:
        sources = tuple(
            (block_id, source_by_id[block_id])
            for block_id in line.block_ids
            if block_id in source_by_id
        )
        for visual_line in _visual_line_groups(sources):
            horizontal_groups: list[
                list[tuple[str, tuple[OcrBlock, AxisAlignedBBox]]]
            ] = []
            for item in sorted(
                visual_line,
                key=lambda value: (value[1][1].x_min, _block_key(value[1])),
            ):
                if not horizontal_groups or _starts_new_line_segment(
                    horizontal_groups[-1][-1][1][1], item[1][1]
                ):
                    horizontal_groups.append([item])
                else:
                    horizontal_groups[-1].append(item)
            for group in horizontal_groups:
                boxes = tuple(source[1] for _, source in group)
                segments.append(
                    OcrLine(
                        line_id=line.line_id,
                        block_ids=tuple(block_id for block_id, _ in group),
                        text=" ".join(_normalized(source[0].text) for _, source in group),
                        bbox=AxisAlignedBBox(
                            min(box.x_min for box in boxes),
                            min(box.y_min for box in boxes),
                            max(box.x_max for box in boxes),
                            max(box.y_max for box in boxes),
                        ),
                    )
                )
    return tuple(segments)


def _visual_line_groups(
    sources: tuple[tuple[str, tuple[OcrBlock, AxisAlignedBBox]], ...],
) -> tuple[tuple[tuple[str, tuple[OcrBlock, AxisAlignedBBox]], ...], ...]:
    return group_visual_lines(
        sources,
        bbox_of=lambda value: value[1][1],
        sort_key=lambda value: _block_key(value[1]),
    )


def _starts_new_line_segment(first: AxisAlignedBBox, second: AxisAlignedBBox) -> bool:
    horizontal_gap = max(second.x_min - first.x_max, 0.0)
    return horizontal_gap > max(first.height, second.height) * 1.5


def _sensitive_continuation_block_ids(segments: tuple[OcrLine, ...]) -> set[str]:
    ordered = tuple(
        sorted(segments, key=lambda line: (line.bbox.y_min, line.bbox.x_min, line.line_id))
    )
    sensitive: set[str] = set()
    for index, line in enumerate(ordered):
        if not any(label in _normalized(line.text) for label in _SECTION_LABELS):
            continue
        previous = line
        for continuation in ordered[index + 1 :]:
            vertical_gap = max(continuation.bbox.y_min - previous.bbox.y_max, 0.0)
            if vertical_gap > max(previous.bbox.height, continuation.bbox.height) * 0.5:
                break
            if not _is_section_continuation(previous.bbox, continuation.bbox):
                continue
            sensitive.update(continuation.block_ids)
            previous = continuation
    return sensitive


def _is_section_continuation(first: AxisAlignedBBox, second: AxisAlignedBBox) -> bool:
    vertical_gap = max(second.y_min - first.y_max, first.y_min - second.y_max, 0.0)
    size = max(first.height, second.height)
    horizontal_overlap = min(first.x_max, second.x_max) - max(first.x_min, second.x_min)
    minimum_width = min(first.width, second.width)
    return vertical_gap <= size * 0.5 and (
        horizontal_overlap >= minimum_width * 0.5
        or _is_bounded_directional_same_line_continuation(first, second)
    )


def _is_bounded_directional_same_line_continuation(
    first: AxisAlignedBBox, second: AxisAlignedBBox
) -> bool:
    vertical_overlap = min(first.y_max, second.y_max) - max(first.y_min, second.y_min)
    horizontal_gap = second.x_min - first.x_max
    minimum_height = min(first.height, second.height)
    maximum_height = max(first.height, second.height)
    maximum_gap = max(first.width, second.width, maximum_height * 12.0) * 1.25
    return (
        horizontal_gap >= 0.0
        and vertical_overlap >= minimum_height * 0.5
        and horizontal_gap <= maximum_gap
    )


def _row_seeds(
    layout: OcrLayoutResult, medication_rows: MedicationRowsResult
) -> tuple[tuple[_RowSeed, ...], tuple[_SourceRow, ...]]:
    if medication_rows.selected_table is not None:
        primary = medication_rows.selected_table.rows
        supplements = (
            *(_SourceRow(row, "guidance") for row in layout.guidance_rows),
            *(_SourceRow(row, "summary") for row in layout.summary_rows),
        )
        return tuple(_RowSeed(row.row_id, row, "table") for row in primary[:100]), supplements
    if layout.guidance_rows:
        primary = _sort_rows(layout.guidance_rows)
        return (
            tuple(
                _RowSeed(f"row-{index:04d}", row, "guidance")
                for index, row in enumerate(primary[:100], 1)
            ),
            tuple(_SourceRow(row, "summary") for row in layout.summary_rows),
        )
    primary = _sort_rows(layout.summary_rows)
    return (
        tuple(
            _RowSeed(f"row-{index:04d}", row, "summary")
            for index, row in enumerate(primary[:100], 1)
        ),
        (),
    )


def _sort_rows(rows: Iterable[LayoutRow]) -> tuple[LayoutRow, ...]:
    return tuple(sorted(rows, key=lambda row: (row.bbox.center_y, row.bbox.x_min, row.row_id)))


def _assign_row_cells(
    seed: _RowSeed,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
    strength_excluded_block_ids: set[str],
    assignments: dict[str, _BlockAssignment],
    row: LayoutRow | None = None,
    source: str | None = None,
) -> None:
    source_row = row or seed.row
    source_kind = source or seed.source
    for column, cell in enumerate(source_row.cells):
        if cell is None:
            continue
        fields = _cell_fields(column, cell.text, source_kind)
        if not fields:
            continue
        assign_strength = "strength" in fields
        fields = tuple(field for field in fields if field != "strength")
        for block_id in cell.block_ids:
            if _eligible(
                block_id, source_by_id, duplicate_ids, line_by_block_id, sensitive_block_ids
            ):
                assignment = assignments[block_id]
                assignment.fields.update(fields)
                assignment.row_ids.add(seed.row_id)
        if assign_strength:
            _assign_atomic_strength_groups(
                OcrLine(
                    line_id="row-cell-strength",
                    block_ids=cell.block_ids,
                    text=cell.text,
                    bbox=cell.bbox,
                ),
                seed.row_id,
                source_by_id,
                duplicate_ids,
                line_by_block_id,
                sensitive_block_ids,
                strength_excluded_block_ids,
                assignments,
            )


def _cell_fields(column: int, text: str, source: str) -> tuple[str, ...]:
    fields_by_column = (
        ("name", "strength"),
        ("doseQuantity",),
        ("timesPerDay",),
        ("days",),
    )
    fields = fields_by_column[column]
    if source != "summary" or column == 0:
        return fields
    normalized = _normalized(text)
    if column == 1 and _SUMMARY_DOSE_PATTERN.fullmatch(normalized):
        return fields
    if column == 2 and _SUMMARY_TIMES_PATTERN.fullmatch(normalized):
        return fields
    if column == 3 and _SUMMARY_DAYS_PATTERN.fullmatch(normalized):
        return fields
    return ()


def _assign_atomic_strength_groups(
    line: OcrLine,
    target_row_id: str,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
    excluded_block_ids: set[str],
    assignments: dict[str, _BlockAssignment],
) -> None:
    for strength_group in _strength_block_id_groups(line, source_by_id):
        if any(
            block_id in excluded_block_ids
            or not _eligible(
                block_id,
                source_by_id,
                duplicate_ids,
                line_by_block_id,
                sensitive_block_ids,
            )
            or (
                (assignment := assignments.get(block_id)) is not None
                and assignment.row_ids
                and assignment.row_ids != {target_row_id}
            )
            for block_id in strength_group
        ):
            continue
        for block_id in strength_group:
            assignment = assignments[block_id]
            assignment.fields.add("strength")
            assignment.row_ids.add(target_row_id)


def _assign_table_alias_strengths(
    layout: OcrLayoutResult,
    seeds: tuple[_RowSeed, ...],
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
    strength_excluded_block_ids: set[str],
    assignments: dict[str, _BlockAssignment],
) -> None:
    for candidate in layout.table_candidates:
        for row in candidate.rows:
            target = _matching_seed(row, seeds)
            name_cell = row.cells[0]
            if target is None or name_cell is None:
                continue
            source_line = OcrLine(
                line_id="table-alias-strength",
                block_ids=name_cell.block_ids,
                text=name_cell.text,
                bbox=name_cell.bbox,
            )
            _assign_atomic_strength_groups(
                source_line,
                target.row_id,
                source_by_id,
                duplicate_ids,
                line_by_block_id,
                sensitive_block_ids,
                strength_excluded_block_ids,
                assignments,
            )


def _assign_standalone_strength_evidence(
    geometry_groups: tuple[tuple[_RowSeed, ...], ...],
    line_segments: tuple[OcrLine, ...],
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
    excluded_block_ids: set[str],
    assignments: dict[str, _BlockAssignment],
) -> None:
    for line in line_segments:
        for strength_group in _strength_block_id_groups(line, source_by_id):
            ordered_ids = tuple(
                sorted(
                    strength_group,
                    key=lambda block_id: _block_key(source_by_id[block_id]),
                )
            )
            boxes = tuple(source_by_id[block_id][1] for block_id in ordered_ids)
            bbox = AxisAlignedBBox(
                min(box.x_min for box in boxes),
                min(box.y_min for box in boxes),
                max(box.x_max for box in boxes),
                max(box.y_max for box in boxes),
            )
            target = _standalone_strength_row_seed(bbox, geometry_groups)
            if target is None:
                continue
            _assign_atomic_strength_groups(
                OcrLine(
                    line_id=line.line_id,
                    block_ids=ordered_ids,
                    text=" ".join(source_by_id[block_id][0].text for block_id in ordered_ids),
                    bbox=bbox,
                ),
                target.row_id,
                source_by_id,
                duplicate_ids,
                line_by_block_id,
                sensitive_block_ids,
                excluded_block_ids,
                assignments,
            )


def _structural_schedule_block_ids(
    layout: OcrLayoutResult,
    seeds: tuple[_RowSeed, ...],
) -> set[str]:
    rows = (
        *(seed.row for seed in seeds),
        *layout.guidance_rows,
        *layout.summary_rows,
        *(row for candidate in layout.table_candidates for row in candidate.rows),
    )
    return {
        block_id
        for row in rows
        for cell in row.cells[1:]
        if cell is not None
        for block_id in cell.block_ids
    }


def _matching_seed(row: LayoutRow, seeds: tuple[_RowSeed, ...]) -> _RowSeed | None:
    name_cell = row.cells[0]
    if name_cell is not None:
        name = _canonical_name(name_cell.text)
        candidates = [
            seed
            for seed in seeds
            if seed.row.cells[0] is not None
            and _names_match(name, _canonical_name(seed.row.cells[0].text))
        ]
        if len(candidates) == 1:
            return candidates[0]

    schedule_provenance = _schedule_provenance(row)
    if schedule_provenance is None:
        return None
    candidates = [
        seed
        for seed in seeds
        if _schedule_provenance(seed.row) == schedule_provenance
    ]
    return candidates[0] if len(candidates) == 1 else None


def _schedule_provenance(
    row: LayoutRow,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    dose, times, days = row.cells[1:]
    if any(cell is None or not cell.block_ids for cell in (dose, times, days)):
        return None
    assert dose is not None and times is not None and days is not None
    return dose.block_ids, times.block_ids, days.block_ids


def _row_geometry_groups(
    layout: OcrLayoutResult,
    seeds: tuple[_RowSeed, ...],
) -> tuple[tuple[_RowSeed, ...], ...]:
    source_groups = (
        ("guidance", layout.guidance_rows),
        ("summary", layout.summary_rows),
        *(("table", candidate.rows) for candidate in layout.table_candidates),
    )
    resolved_seeds = _sort_seeds(
        _schedule_provenance_geometry_group(seeds, source_groups)
    )
    groups: list[tuple[_RowSeed, ...]] = [resolved_seeds]
    signatures = {_geometry_group_signature(resolved_seeds)}
    for source, rows in source_groups:
        matched = _sort_seeds(
            tuple(
                _RowSeed(target.row_id, row, source)
                for row in rows
                if (target := _matching_seed(row, seeds)) is not None
            )
        )
        if not matched:
            continue
        signature = _geometry_group_signature(matched)
        if signature in signatures:
            continue
        signatures.add(signature)
        groups.append(matched)
    return tuple(groups)


def _schedule_provenance_geometry_group(
    seeds: tuple[_RowSeed, ...],
    source_groups: tuple[tuple[str, tuple[LayoutRow, ...]], ...],
) -> tuple[_RowSeed, ...]:
    resolved: list[_RowSeed] = []
    for seed in seeds:
        provenance = _schedule_provenance(seed.row)
        if provenance is None or sum(
            _schedule_provenance(candidate.row) == provenance for candidate in seeds
        ) != 1:
            resolved.append(seed)
            continue
        candidates = {
            (
                row.bbox.x_min,
                row.bbox.y_min,
                row.bbox.x_max,
                row.bbox.y_max,
            ): _RowSeed(seed.row_id, row, source)
            for source, rows in source_groups
            for row in rows
            if _schedule_provenance(row) == provenance
        }
        resolved.append(next(iter(candidates.values())) if len(candidates) == 1 else seed)
    return tuple(resolved)


def _geometry_group_signature(seeds: tuple[_RowSeed, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            seed.row_id,
            seed.row.bbox.x_min,
            seed.row.bbox.y_min,
            seed.row.bbox.x_max,
            seed.row.bbox.y_max,
        )
        for seed in _sort_seeds(seeds)
    )


def _sort_seeds(seeds: tuple[_RowSeed, ...]) -> tuple[_RowSeed, ...]:
    return tuple(
        sorted(seeds, key=lambda seed: (seed.row.bbox.center_y, seed.row.bbox.x_min, seed.row_id))
    )


def _row_band_seed(
    bbox: AxisAlignedBBox,
    groups: tuple[tuple[_RowSeed, ...], ...],
) -> _RowSeed | None:
    candidates_by_row_id: dict[str, tuple[float, _RowSeed]] = {}
    for group in groups:
        candidate = _row_band_group_seed(bbox, group)
        if candidate is None:
            continue
        distance = abs(bbox.center_y - candidate.row.bbox.center_y) / max(
            bbox.height, candidate.row.bbox.height
        )
        current = candidates_by_row_id.get(candidate.row_id)
        if current is None or distance < current[0]:
            candidates_by_row_id[candidate.row_id] = (distance, candidate)
    ordered_candidates = sorted(
        candidates_by_row_id.values(),
        key=lambda item: (item[0], item[1].row.bbox.x_min, item[1].row_id),
    )
    if not ordered_candidates:
        return None
    if len(ordered_candidates) > 1 and ordered_candidates[1][0] - ordered_candidates[0][0] < 0.25:
        return None
    return ordered_candidates[0][1]


def _standalone_strength_row_seed(
    bbox: AxisAlignedBBox,
    groups: tuple[tuple[_RowSeed, ...], ...],
) -> _RowSeed | None:
    target = _row_band_seed(bbox, groups)
    if target is not None:
        return target

    candidates_by_row_id: dict[str, list[_RowSeed]] = defaultdict(list)
    for group in groups:
        candidate = _row_band_group_seed(bbox, group)
        if candidate is None:
            candidate = _standalone_strength_continuation_group_seed(bbox, group)
        if candidate is not None:
            candidates_by_row_id[candidate.row_id].append(candidate)
    if len(candidates_by_row_id) != 1:
        return None
    return _sort_seeds(tuple(next(iter(candidates_by_row_id.values()))))[0]


def _standalone_strength_continuation_group_seed(
    bbox: AxisAlignedBBox,
    seeds: tuple[_RowSeed, ...],
) -> _RowSeed | None:
    candidates: list[_RowSeed] = []
    for preceding, following in zip(seeds, seeds[1:], strict=False):
        preceding_bbox = preceding.row.bbox
        following_bbox = following.row.bbox
        horizontal_overlap = min(bbox.x_max, preceding_bbox.x_max) - max(
            bbox.x_min, preceding_bbox.x_min
        )
        minimum_width = min(bbox.width, preceding_bbox.width)
        vertical_gap = bbox.y_min - preceding_bbox.y_max
        if (
            following_bbox.y_min <= preceding_bbox.y_max
            or bbox.center_y >= following_bbox.y_min
            or horizontal_overlap < minimum_width * 0.5
            or vertical_gap < -bbox.height * 0.5
            or vertical_gap > bbox.height
        ):
            continue
        candidates.append(preceding)
    return candidates[0] if len(candidates) == 1 else None


def _row_band_group_seed(
    bbox: AxisAlignedBBox,
    seeds: tuple[_RowSeed, ...],
) -> _RowSeed | None:
    candidates: list[_RowSeed] = []
    for index, seed in enumerate(seeds):
        center = seed.row.bbox.center_y
        if index > 0:
            lower = (seeds[index - 1].row.bbox.center_y + center) / 2.0
        elif len(seeds) > 1:
            lower = center - (seeds[1].row.bbox.center_y - center) / 2.0
        else:
            lower = center - max(seed.row.bbox.height, bbox.height) * 3.0
        if index + 1 < len(seeds):
            upper = (center + seeds[index + 1].row.bbox.center_y) / 2.0
        elif len(seeds) > 1:
            upper = (
                center
                + (center - seeds[index - 1].row.bbox.center_y) / 2.0
                + seed.row.bbox.height * 0.25
            )
        else:
            upper = center + max(seed.row.bbox.height, bbox.height) * 3.0
        horizontal_overlap = min(bbox.x_max, seed.row.bbox.x_max) - max(
            bbox.x_min, seed.row.bbox.x_min
        )
        if lower <= bbox.center_y <= upper and horizontal_overlap > 0.0:
            candidates.append(seed)
    if len(candidates) != 1:
        return None
    distances = sorted(
        abs(bbox.center_y - seed.row.bbox.center_y) / max(bbox.height, seed.row.bbox.height)
        for seed in seeds
        if min(bbox.x_max, seed.row.bbox.x_max) - max(bbox.x_min, seed.row.bbox.x_min)
        > 0.0
    )
    if len(distances) > 1 and distances[1] - distances[0] < 0.25:
        return None
    return candidates[0]


def _strength_block_ids(
    line: OcrLine,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
) -> frozenset[str]:
    return frozenset(
        block_id for group in _strength_block_id_groups(line, source_by_id) for block_id in group
    )


def _strength_block_id_groups(
    line: OcrLine,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
) -> tuple[frozenset[str], ...]:
    ordered = tuple(
        sorted(
            (
                (block_id, source_by_id[block_id])
                for block_id in line.block_ids
                if block_id in source_by_id
            ),
            key=lambda item: _block_key(item[1]),
        )
    )
    combined_parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    position = 0
    previous_fragment = ""
    for block_id, (source, _) in ordered:
        fragment = _normalized(source.text)
        if not fragment:
            continue
        separator = (
            ""
            if not combined_parts
            or previous_fragment.endswith("/")
            or fragment.startswith("/")
            else " "
        )
        combined_parts.append(separator)
        position += len(separator)
        start = position
        combined_parts.append(fragment)
        position += len(fragment)
        spans.append((start, position, block_id))
        previous_fragment = fragment
    combined = normalize_measurement_unit_ocr("".join(combined_parts))
    return tuple(
        frozenset(
            block_id
            for start, end, block_id in spans
            if start < match.end() and end > match.start()
        )
        for match in _STRENGTH_PATTERN.finditer(combined)
    )


def _date_candidate_ids(
    line_segments: tuple[OcrLine, ...],
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    sensitive_block_ids: set[str],
) -> tuple[str, ...]:
    ordered_lines = tuple(
        sorted(line_segments, key=lambda line: (line.bbox.y_min, line.bbox.x_min, line.line_id))
    )
    anchors = [line for line in ordered_lines if _DATE_LABEL_PATTERN.search(_normalized(line.text))]
    candidate_ids: set[str] = set()
    for line in anchors:
        if all(block_id in sensitive_block_ids for block_id in line.block_ids):
            continue
        for block_id in line.block_ids:
            source = source_by_id.get(block_id)
            if (
                source is not None
                and _is_date_evidence_text(source[0].text)
                and _eligible(
                    block_id,
                    source_by_id,
                    duplicate_ids,
                    {block_id: line.line_id},
                    sensitive_block_ids,
                )
            ):
                candidate_ids.add(block_id)
        anchor_index = ordered_lines.index(line)
        for adjacent_index in (anchor_index - 1, anchor_index + 1):
            if adjacent_index < 0 or adjacent_index >= len(ordered_lines):
                continue
            adjacent = ordered_lines[adjacent_index]
            if (
                not all(block_id in sensitive_block_ids for block_id in adjacent.block_ids)
                and _is_explicit_date_value(adjacent.text)
                and _are_adjacent_date_lines(line.bbox, adjacent.bbox)
            ):
                for block_id in adjacent.block_ids:
                    source = source_by_id.get(block_id)
                    if source is not None and _is_explicit_date_value(source[0].text):
                        candidate_ids.add(block_id)
    return tuple(sorted(candidate_ids, key=lambda block_id: _block_key(source_by_id[block_id])))


def _is_date_evidence_text(text: str) -> bool:
    normalized = _normalized(text)
    return (
        _DATE_LABEL_ONLY_PATTERN.fullmatch(normalized) is not None
        or _is_explicit_date_value(normalized)
        or _DATE_LABEL_AND_VALUE_PATTERN.fullmatch(normalized) is not None
    )


def _is_explicit_date_value(text: str) -> bool:
    return _DATE_VALUE_ONLY_PATTERN.fullmatch(_normalized(text)) is not None


def _are_adjacent_date_lines(first: AxisAlignedBBox, second: AxisAlignedBBox) -> bool:
    height = max(first.height, second.height)
    horizontal_gap = max(second.x_min - first.x_max, first.x_min - second.x_max, 0.0)
    return (
        abs(first.height - second.height) <= height * 0.35
        and abs(first.center_y - second.center_y) <= height * 1.25
        and horizontal_gap <= max(first.width, second.width) * 2.0
    )


def _evidence_blocks(
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
    assignments: dict[str, _BlockAssignment],
    date_ids: tuple[str, ...],
) -> tuple[EvidenceBlock, ...]:
    evidence: list[EvidenceBlock] = []
    date_id_set = set(date_ids)
    for block_id, (source, bbox) in source_by_id.items():
        if not _eligible(
            block_id, source_by_id, duplicate_ids, line_by_block_id, sensitive_block_ids
        ):
            continue
        assignment = assignments.get(block_id)
        fields = set(assignment.fields) if assignment is not None else set()
        if block_id in date_id_set:
            fields.add("dispensedDate")
        if not fields:
            continue
        evidence.append(
            EvidenceBlock(
                block_id=block_id,
                text=_normalized(source.text),
                confidence=source.confidence,
                bbox=bbox,
                line_id=line_by_block_id[block_id],
                row_ids=tuple(sorted(assignment.row_ids)) if assignment is not None else (),
                allowed_fields=tuple(field for field in _FIELD_ORDER if field in fields),
            )
        )
    return tuple(sorted(evidence, key=lambda block: _evidence_key(block)))


def _eligible(
    block_id: str,
    source_by_id: dict[str, tuple[OcrBlock, AxisAlignedBBox]],
    duplicate_ids: set[str],
    line_by_block_id: dict[str, str],
    sensitive_block_ids: set[str],
) -> bool:
    line_id = line_by_block_id.get(block_id)
    source = source_by_id.get(block_id)
    return (
        block_id not in duplicate_ids
        and source is not None
        and line_id is not None
        and block_id not in sensitive_block_ids
        and not _is_sensitive_text(source[0].text)
    )


def _is_sensitive_text(text: str) -> bool:
    normalized = _normalized(text)
    return (
        any(label in normalized for label in _SENSITIVE_LABELS)
        or any(label in normalized for label in _PAYMENT_LABELS)
        or _PHONE_PATTERN.search(normalized) is not None
        or _BUSINESS_NUMBER_PATTERN.search(normalized) is not None
        or _WON_AMOUNT_PATTERN.search(normalized) is not None
    )


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def _canonical_name(text: str) -> str:
    compact = "".join(_normalized(text).lower().split())
    strength = _STRENGTH_PATTERN.search(compact)
    if strength is not None:
        compact = compact[: strength.start()]
    return "".join(character for character in compact if character.isalnum())


def _names_match(first: str, second: str) -> bool:
    minimum = min(len(first), len(second))
    return minimum >= 4 and (first.startswith(second) or second.startswith(first))


def _block_key(source: tuple[OcrBlock, AxisAlignedBBox]) -> tuple[float, float, str]:
    return source[1].center_y, source[1].x_min, source[0].block_id


def _evidence_key(block: EvidenceBlock) -> tuple[float, float, str]:
    return block.bbox.center_y, block.bbox.x_min, block.block_id

