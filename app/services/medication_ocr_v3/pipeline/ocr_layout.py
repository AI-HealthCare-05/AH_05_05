"""Deterministic geometry reconstruction for normalized OCR blocks."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from itertools import combinations
from statistics import median

from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrBlockIssueCode, OcrResult
from app.services.medication_ocr_v3.pipeline.ocr_normalization import normalize_measurement_unit_ocr

_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "name": frozenset(
        {"약품명", "약품명·성분", "약품명및용량", "약품명및용법", "품목명"}
    ),
    "dose": frozenset({"투약량", "복약량", "1회량"}),
    "times": frozenset({"횟수", "1일횟수", "투어횟수"}),
    "days": frozenset({"일수", "투약일수"}),
}
_HEADER_ORDER = ("name", "dose", "times", "days")
_TRAILING_AMOUNT_ALIASES = frozenset({"금액", "금액(원)", "금액원"})
_LINE_CENTER_DISTANCE = 0.75
_LINE_VERTICAL_OVERLAP = 0.35
_COLUMN_MIN_OVERLAP = 0.55
_COLUMN_MAX_SECONDARY_OVERLAP = 0.40
_MAX_BODY_LINE_GAP = 4.0
_MAX_STRONG_BODY_LINE_GAP = 5.0
_MAX_GUIDANCE_NAME_TO_INSTRUCTION_GAP = 10.0
_MAX_WRAPPED_NAME_DISTANCE = 2.25
_MAX_WRAPPED_NAME_JOIN_DISTANCE = 1.25
_MIN_WRAPPED_NAME_HORIZONTAL_OVERLAP = 0.80
_MAX_NAME_BLOCK_HEIGHT_RATIO = 4.0
_MAX_NAME_FRAGMENT_HORIZONTAL_GAP = 2.5
_MAX_NAME_FRAGMENT_CENTER_DISTANCE = 0.35
_MAX_NUMERIC_LANE_OFFSET_GAP = 3.0
_MAX_SPLIT_HEADER_VERTICAL_GAP = 1.25
_INLINE_NAME_CONFIDENCE_MARGIN = 0.05
_MIN_TRUNCATED_NAME_PREFIX_LENGTH = 4
_HEADER_SEPARATOR_TRANSLATION = str.maketrans(
    {
        "/": "·",
        "ㆍ": "·",
        "ᆞ": "·",
        "•": "·",
        "・": "·",
        "･": "·",
        ".": "·",
    }
)
_STRUCTURAL_NUMERIC_PATTERN = re.compile(
    r"[0-9]+(?:[./][0-9]+)?(?:회|일분|일)?",
)
_GUIDANCE_DAILY_MARKER_PATTERN = re.compile(r"1일")
_GUIDANCE_TIMES_PATTERN = re.compile(r"[1-9][0-9]*회")
_GUIDANCE_DAYS_PATTERN = re.compile(r"[1-9][0-9]*일분")
_GUIDANCE_DOSE_PATTERN = re.compile(
    r"(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+)(?:정|캡슐|포|ml)(?:씩)?",
    re.IGNORECASE,
)
_COMBINED_GUIDANCE_SCHEDULE_PATTERN = re.compile(
    r"(?P<dose>(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+)"
    r"(?:정|캡슐|포|m[lℓ])?)씩"
    r"(?P<times>[1-9][0-9]*)회[,，]?"
    r"(?P<days>[1-9][0-9]*)일분",
    re.IGNORECASE,
)
_FUZZY_COMBINED_GUIDANCE_SCHEDULE_PATTERN = re.compile(
    r"(?P<dose>(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+)"
    r"(?:정|캡슐|포|m[lℓ])?)씩"
    r"(?P<times>[1-9][0-9]*)(?:[,，]|[가-힣][,，]?)"
    r"(?P<days>[1-9][0-9]*)일분",
    re.IGNORECASE,
)
_INLINE_TIMES_PATTERN = re.compile(r"([1-9][0-9]*)회[,，]?")
_INLINE_RECEIPT_NUMBER_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_SUMMARY_ROW_MARKER_PATTERN = re.compile(
    r"(?:소계|합계|총계|총합|합산|요약|금액|총액|총금액|합계금액|"
    r"청구금액|결제금액|본인부담(?:금|액)?|보험부담(?:금|액)?)(?:\(원\))?"
)
_HEADERLESS_DOSE_PATTERN = re.compile(
    r"(?:[1-9][0-9]*(?:\.[0-9]+)?|0\.[0-9]+|[1-9][0-9]*/[1-9][0-9]*)"
)
_HEADERLESS_TIMES_PATTERN = re.compile(r"([1-9][0-9]*)(?:회)?")
_HEADERLESS_DAYS_PATTERN = re.compile(r"([1-9][0-9]*)(?:일분|일)?")
_HEADERLESS_NAME_STRENGTH_PATTERN = re.compile(
    r"\(?[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?"
    r"(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램|마이크로그램|밀리리터|%)\)?",
    re.IGNORECASE,
)
_MEDICATION_NAME_FORM_PATTERN = re.compile(
    r"(?:정|캡슐|시럽|크림|연고|현탁액|내복액|외용액|점안액|주사액|"
    r"과립|패취|패치|겔)(?=$|[_\s(0-9./·…⋯-])",
    re.IGNORECASE,
)
_OCR_STRENGTH_LIKE_PATTERN = re.compile(
    r"[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)?"
    r"(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그[램람랑]|그램|마이크로그램|%)",
    re.IGNORECASE,
)
_WEAK_MEDICATION_CONTEXT_PATTERN = re.compile(
    r"(?:약|전문의약품|일반의약품|의약품|약품|약제|내복약|외용약|"
    r"복약|복용|투약|투여|용법|용량|성분|효능|처방|조제)"
)
_WEAK_MEDICATION_PRODUCT_PATTERN = re.compile(
    r"(?:정|캡슐|시럽|크림|연고|액|산|과립|패취|패치|겔|주|스프레이|로션)"
    r"(?:[0-9]+(?:\.[0-9]+)?(?:mg|g|mcg|ug|μg|ml|mℓ|밀리그램|그램)?)?$",
    re.IGNORECASE,
)
_HEADERLESS_NON_MEDICATION_VOCABULARY_PATTERN = re.compile(
    r"(?:급여|비급여|수납|청구|보험|부담금|진료비|진찰료|조제료|처방료|"
    r"수수료|소계|합계|총액|금액|잔액|단가|수가|정산|산정|조정|행정|"
    r"비용|내역|접수|운영|평가|검사|환불|면제|예약|고객|서비스|상담)"
)
_MIN_HEADERLESS_RECEIPT_ROWS = 2
_MAX_HEADERLESS_RECEIPT_ROWS = 12
_MAX_HEADERLESS_NUMERIC_LENGTH = 32
_MAX_JSON_SAFE_INTEGER_TEXT = str(2**53 - 1)


class LayoutIssueCode(StrEnum):
    INVALID_BLOCK_GEOMETRY = "INVALID_BLOCK_GEOMETRY"
    INVALID_BLOCK_CONFIDENCE = "INVALID_BLOCK_CONFIDENCE"
    AMBIGUOUS_COLUMN_ASSIGNMENT = "AMBIGUOUS_COLUMN_ASSIGNMENT"


@dataclass(frozen=True, slots=True)
class LayoutIssue:
    code: LayoutIssueCode
    block_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "blockIds": list(self.block_ids)}


@dataclass(frozen=True, slots=True)
class AxisAlignedBBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    def as_dict(self) -> dict[str, object]:
        values = (self.x_min, self.y_min, self.x_max, self.y_max)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Layout bbox contains non-finite values.")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("Layout bbox is not a positive envelope.")
        return {
            "coordinateSpace": "processed",
            "xMin": self.x_min,
            "yMin": self.y_min,
            "xMax": self.x_max,
            "yMax": self.y_max,
        }


def group_visual_lines[VisualLineItem](
    items: Iterable[VisualLineItem],
    *,
    bbox_of: Callable[[VisualLineItem], AxisAlignedBBox],
    sort_key: Callable[[VisualLineItem], tuple[float, float, str]],
) -> tuple[tuple[VisualLineItem, ...], ...]:
    """Sort OCR items once, then group them into visual lines in one pass."""

    groups: list[list[VisualLineItem]] = []
    center_sums: list[float] = []
    height_sums: list[float] = []
    for item in sorted(items, key=sort_key):
        candidate = bbox_of(item)
        if not groups or _starts_new_visual_line(
            center_sums[-1],
            height_sums[-1],
            len(groups[-1]),
            candidate,
        ):
            groups.append([item])
            center_sums.append(candidate.center_y)
            height_sums.append(candidate.height)
            continue
        groups[-1].append(item)
        center_sums[-1] += candidate.center_y
        height_sums[-1] += candidate.height
    return tuple(tuple(group) for group in groups)


def _starts_new_visual_line(
    center_sum: float,
    height_sum: float,
    count: int,
    candidate: AxisAlignedBBox,
) -> bool:
    center = center_sum / count
    height = height_sum / count
    reference_y_min = center - height / 2.0
    reference_y_max = center + height / 2.0
    vertical_overlap = min(reference_y_max, candidate.y_max) - max(
        reference_y_min,
        candidate.y_min,
    )
    maximum_height = max(height, candidate.height)
    minimum_height = min(height, candidate.height)
    return (
        abs(center - candidate.center_y) > maximum_height * 0.75
        and vertical_overlap < minimum_height * 0.25
    )


@dataclass(frozen=True, slots=True)
class OcrLine:
    line_id: str
    block_ids: tuple[str, ...]
    text: str
    bbox: AxisAlignedBBox

    def as_dict(self) -> dict[str, object]:
        return {
            "lineId": self.line_id,
            "blockIds": list(self.block_ids),
            "text": self.text,
            "bbox": self.bbox.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class HeaderColumn:
    key: str
    source_text: str
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox
    band_min: float
    band_max: float

    def as_dict(self) -> dict[str, object]:
        if not math.isfinite(self.band_min) or not math.isfinite(self.band_max):
            raise ValueError("Header column contains non-finite values.")
        return {
            "key": self.key,
            "sourceText": self.source_text,
            "blockIds": list(self.block_ids),
            "bbox": self.bbox.as_dict(),
            "band": {"xMin": self.band_min, "xMax": self.band_max},
        }


@dataclass(frozen=True, slots=True)
class LayoutCell:
    text: str
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox
    confidence: float | None
    valid_confidence_count: int
    source_issues: tuple[OcrBlockIssueCode, ...]
    parsed_text: str | None = None

    def as_dict(self) -> dict[str, object]:
        if self.confidence is not None and not math.isfinite(self.confidence):
            raise ValueError("Layout cell contains non-finite values.")
        return {
            "text": self.text,
            "blockIds": list(self.block_ids),
            "bbox": self.bbox.as_dict(),
            "confidence": self.confidence,
            "issues": [issue.value for issue in self.source_issues],
        }


type LayoutCells = tuple[
    LayoutCell | None,
    LayoutCell | None,
    LayoutCell | None,
    LayoutCell | None,
]


@dataclass(frozen=True, slots=True)
class LayoutRow:
    row_id: str
    cells: LayoutCells
    bbox: AxisAlignedBBox

    @property
    def source_block_ids(self) -> tuple[str, ...]:
        return tuple(
            block_id
            for cell in self.cells
            if cell is not None
            for block_id in cell.block_ids
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "rowId": self.row_id,
            "sourceBlockIds": list(self.source_block_ids),
            "bbox": self.bbox.as_dict(),
            "cells": {
                key: cell.as_dict() if cell is not None else None
                for key, cell in zip(_HEADER_ORDER, self.cells, strict=True)
            },
        }


@dataclass(frozen=True, slots=True)
class AmbiguousColumnEvidence:
    source_text: str
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox
    nearest_row_index: int | None
    overlapping_columns: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "sourceText": self.source_text,
            "blockIds": list(self.block_ids),
            "bbox": self.bbox.as_dict(),
            "nearestRowIndex": self.nearest_row_index,
            "overlappingColumns": list(self.overlapping_columns),
        }


@dataclass(frozen=True, slots=True)
class TableCandidate:
    candidate_id: str
    bbox: AxisAlignedBBox
    header_columns: tuple[HeaderColumn, HeaderColumn, HeaderColumn, HeaderColumn]
    rows: tuple[LayoutRow, ...]
    ambiguous_column_evidence: tuple[AmbiguousColumnEvidence, ...]
    column_consistency: float
    confidence_coverage: float
    mean_confidence: float | None
    approval_block_ids: tuple[str, ...] = ()
    observed_header_coverage: int = 4
    header_inferred: bool = False

    @property
    def header_block_ids(self) -> tuple[str, ...]:
        return tuple(
            block_id for column in self.header_columns for block_id in column.block_ids
        )

    @property
    def source_block_ids(self) -> tuple[str, ...]:
        return self.header_block_ids + tuple(
            block_id for row in self.rows for block_id in row.source_block_ids
        ) + tuple(
            block_id
            for evidence in self.ambiguous_column_evidence
            for block_id in evidence.block_ids
        )

    def as_dict(self) -> dict[str, object]:
        metrics = (self.column_consistency, self.confidence_coverage)
        if not all(math.isfinite(value) for value in metrics):
            raise ValueError("Table candidate contains non-finite values.")
        if self.mean_confidence is not None and not math.isfinite(self.mean_confidence):
            raise ValueError("Table candidate contains non-finite values.")
        return {
            "candidateId": self.candidate_id,
            "bbox": self.bbox.as_dict(),
            "headerMapping": [column.as_dict() for column in self.header_columns],
            "rows": [row.as_dict() for row in self.rows],
            "ambiguousColumnEvidence": [
                evidence.as_dict() for evidence in self.ambiguous_column_evidence
            ],
            "approvalBlockIds": list(self.approval_block_ids),
            "sourceBlockIds": list(self.source_block_ids),
            "metrics": {
                "headerCoverage": self.observed_header_coverage,
                "headerInferred": self.header_inferred,
                "columnConsistency": self.column_consistency,
                "confidenceCoverage": self.confidence_coverage,
                "meanConfidence": self.mean_confidence,
            },
        }


@dataclass(frozen=True, slots=True)
class OcrLayoutResult:
    lines: tuple[OcrLine, ...]
    table_candidates: tuple[TableCandidate, ...]
    issues: tuple[LayoutIssue, ...]
    guidance_rows: tuple[LayoutRow, ...] = ()
    summary_rows: tuple[LayoutRow, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "lines": [line.as_dict() for line in self.lines],
            "tableCandidates": [candidate.as_dict() for candidate in self.table_candidates],
            "issues": [issue.as_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class _GeometryBlock:
    source: OcrBlock
    bbox: AxisAlignedBBox
    provider_order: tuple[int, str]
    source_issues: tuple[OcrBlockIssueCode, ...]
    source_block_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _LineGroup:
    blocks: tuple[_GeometryBlock, ...]
    bbox: AxisAlignedBBox


@dataclass(frozen=True, slots=True)
class _HeaderSeed:
    blocks: tuple[_GeometryBlock, _GeometryBlock, _GeometryBlock, _GeometryBlock]
    bands: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]
    bbox: AxisAlignedBBox
    numeric_right_bound: float | None


@dataclass(frozen=True, slots=True)
class _GuidanceHeader:
    name_band: tuple[float, float]
    instruction_band: tuple[float, float]
    bbox: AxisAlignedBBox


@dataclass(frozen=True, slots=True)
class _HeaderMatch:
    key: str
    fuzzy: bool


@dataclass(frozen=True, slots=True)
class _BodyFragment:
    blocks_by_column: tuple[
        tuple[_GeometryBlock, ...],
        tuple[_GeometryBlock, ...],
        tuple[_GeometryBlock, ...],
        tuple[_GeometryBlock, ...],
    ]
    bbox: AxisAlignedBBox


@dataclass(frozen=True, slots=True)
class _NumericRowSeed:
    blocks: tuple[_GeometryBlock, ...]
    center_y: float


@dataclass(frozen=True, slots=True)
class _InlineGuidanceRow:
    name_blocks: tuple[_GeometryBlock, ...]
    dose_block: _GeometryBlock
    times_block: _GeometryBlock
    anchor_y: float


@dataclass(frozen=True, slots=True)
class _InlineGuidanceHeader:
    name_block: _GeometryBlock
    guidance_block: _GeometryBlock
    name_band: tuple[float, float]
    schedule_band: tuple[float, float]


@dataclass(frozen=True, slots=True)
class _InlineReceiptMatch:
    day_cell: LayoutCell
    preferred_name_cell: LayoutCell | None


@dataclass(frozen=True, slots=True)
class _HeaderlessReceiptRow:
    name_blocks: tuple[_GeometryBlock, ...]
    name_evidence_blocks: tuple[_GeometryBlock, ...]
    numeric_blocks: tuple[_GeometryBlock, _GeometryBlock, _GeometryBlock]
    derived_total_block: _GeometryBlock | None
    parsed_values: tuple[str, str, str]
    center_y: float
    bbox: AxisAlignedBBox


@dataclass(frozen=True, slots=True)
class _HeaderlessSemantics:
    header_blocks: tuple[
        _GeometryBlock,
        _GeometryBlock,
        _GeometryBlock,
        _GeometryBlock,
    ]
    header_matches: tuple[_HeaderMatch, _HeaderMatch, _HeaderMatch, _HeaderMatch]
    guidance_block: _GeometryBlock


@dataclass(frozen=True, slots=True)
class _HeaderlessPeerEvidence:
    peer_blocks: tuple[_GeometryBlock, ...]
    recovered_name_block: _GeometryBlock | None
    output_name_blocks: tuple[tuple[_GeometryBlock, ...], ...]


@dataclass(frozen=True, slots=True)
class _WeakMedicationEvidence:
    blocks: tuple[_GeometryBlock, ...]
    bbox: AxisAlignedBBox
    lexical: bool
    explicit: bool


@dataclass(frozen=True, slots=True)
class _HeaderlessContextEvidence:
    name_blocks: tuple[_GeometryBlock, ...]
    approval_block_ids: tuple[str, ...]
    bboxes: tuple[AxisAlignedBBox, ...]
    context_line_block_ids: frozenset[str]
    weak: bool
    row_evidence: tuple[tuple[_WeakMedicationEvidence, ...], ...] = ()


def build_ocr_layout(result: OcrResult) -> OcrLayoutResult:
    """Build immutable diagnostic lines and medication table candidates."""

    geometry_blocks, source_issues = _geometry_blocks(result.blocks)
    line_groups = _cluster_lines(geometry_blocks)
    lines = tuple(
        OcrLine(
            line_id=f"line-{index:04d}",
            block_ids=tuple(block.source.block_id for block in group.blocks),
            text=" ".join(block.source.text for block in group.blocks),
            bbox=group.bbox,
        )
        for index, group in enumerate(line_groups, start=1)
    )
    seeds = _header_seeds(line_groups)
    candidates, candidate_issues = _table_candidates(seeds, line_groups)
    if not candidates:
        candidates = _combined_guidance_candidates(line_groups)
    if not candidates:
        candidates = _inline_composite_candidates(line_groups)
    if not candidates:
        candidates = _headerless_correlated_receipt_candidates(line_groups)
    issues = _deduplicate_issues((*source_issues, *candidate_issues))
    return OcrLayoutResult(
        lines=lines,
        table_candidates=candidates,
        issues=issues,
        guidance_rows=_guidance_layout_rows(line_groups),
        summary_rows=_three_column_summary_rows(line_groups),
    )


def _geometry_blocks(
    blocks: tuple[OcrBlock, ...],
) -> tuple[tuple[_GeometryBlock, ...], tuple[LayoutIssue, ...]]:
    valid: list[_GeometryBlock] = []
    issues: list[LayoutIssue] = []
    for block in blocks:
        source_issues = list(block.issues)
        bbox = _bbox_from_block(block)
        if bbox is None:
            if OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY not in source_issues:
                source_issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
            issues.append(
                LayoutIssue(LayoutIssueCode.INVALID_BLOCK_GEOMETRY, (block.block_id,))
            )
            continue
        if block.confidence is None or not math.isfinite(block.confidence):
            if OcrBlockIssueCode.INVALID_BLOCK_CONFIDENCE not in source_issues:
                source_issues.append(OcrBlockIssueCode.INVALID_BLOCK_CONFIDENCE)
        for issue in source_issues:
            if issue is OcrBlockIssueCode.INVALID_BLOCK_CONFIDENCE:
                issues.append(
                    LayoutIssue(LayoutIssueCode.INVALID_BLOCK_CONFIDENCE, (block.block_id,))
                )
        valid.append(
            _GeometryBlock(
                source=block,
                bbox=bbox,
                provider_order=_provider_order(block.block_id),
                source_issues=tuple(dict.fromkeys(source_issues)),
                source_block_ids=(block.block_id,),
            )
        )
    return tuple(valid), _deduplicate_issues(issues)


def _bbox_from_block(block: OcrBlock) -> AxisAlignedBBox | None:
    if block.bbox is None:
        return None
    xs = tuple(point.x for point in block.bbox)
    ys = tuple(point.y for point in block.bbox)
    if not all(math.isfinite(value) for value in (*xs, *ys)):
        return None
    bbox = AxisAlignedBBox(min(xs), min(ys), max(xs), max(ys))
    if bbox.width <= 0.0 or bbox.height <= 0.0:
        return None
    return bbox


def _provider_order(block_id: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", block_id)
    return (int(match.group(1)) if match is not None else 2**63 - 1, block_id)


def _cluster_lines(blocks: tuple[_GeometryBlock, ...]) -> tuple[_LineGroup, ...]:
    ordered = sorted(
        blocks,
        key=lambda block: (
            block.bbox.center_y,
            block.bbox.x_min,
            block.provider_order,
        ),
    )
    mutable_groups: list[list[_GeometryBlock]] = []
    for block in ordered:
        compatible: list[tuple[float, int]] = []
        for index, group in enumerate(mutable_groups):
            group_center = median(member.bbox.center_y for member in group)
            group_height = median(member.bbox.height for member in group)
            center_distance = abs(block.bbox.center_y - group_center) / median(
                (block.bbox.height, group_height)
            )
            representative_band = AxisAlignedBBox(
                0.0,
                group_center - group_height / 2.0,
                1.0,
                group_center + group_height / 2.0,
            )
            overlap = _vertical_overlap(block.bbox, representative_band)
            overlap_ratio = overlap / min(block.bbox.height, group_height)
            if (
                overlap_ratio >= _LINE_VERTICAL_OVERLAP
                or center_distance <= _LINE_CENTER_DISTANCE
            ):
                compatible.append((center_distance, index))
        if compatible:
            _, best_index = min(compatible)
            mutable_groups[best_index].append(block)
        else:
            mutable_groups.append([block])
    groups = [
        _LineGroup(
            blocks=tuple(
                sorted(
                    group,
                    key=lambda block: (block.bbox.x_min, block.provider_order),
                )
            ),
            bbox=_union(block.bbox for block in group),
        )
        for group in mutable_groups
    ]
    groups.sort(
        key=lambda group: (
            group.bbox.center_y,
            group.bbox.y_min,
            group.bbox.x_min,
            tuple(block.provider_order for block in group.blocks),
        )
    )
    return tuple(groups)


def _vertical_overlap(first: AxisAlignedBBox, second: AxisAlignedBBox) -> float:
    return max(0.0, min(first.y_max, second.y_max) - max(first.y_min, second.y_min))


def _normalized_header_text(text: str) -> str:
    normalized = unicodedata.normalize(
        "NFKC", text.translate(_HEADER_SEPARATOR_TRANSLATION)
    )
    return "".join(normalized.split()).translate(_HEADER_SEPARATOR_TRANSLATION)


def _within_one_edit(first: str, second: str) -> bool:
    if abs(len(first) - len(second)) > 1:
        return False
    if len(first) == len(second):
        return sum(left != right for left, right in zip(first, second, strict=True)) <= 1
    shorter, longer = (first, second) if len(first) < len(second) else (second, first)
    short_index = 0
    long_index = 0
    skipped = False
    while short_index < len(shorter) and long_index < len(longer):
        if shorter[short_index] == longer[long_index]:
            short_index += 1
            long_index += 1
            continue
        if skipped:
            return False
        skipped = True
        long_index += 1
    return True


def _header_match(text: str) -> _HeaderMatch | None:
    comparison = _normalized_header_text(text)
    exact_keys = {
        key
        for key, aliases in _HEADER_ALIASES.items()
        if comparison in {_normalized_header_text(alias) for alias in aliases}
    }
    if len(exact_keys) == 1:
        return _HeaderMatch(next(iter(exact_keys)), False)
    if exact_keys or len(comparison) < 3:
        return None
    fuzzy_keys = {
        key
        for key, aliases in _HEADER_ALIASES.items()
        if any(
            len(normalized_alias) >= 3
            and _within_one_edit(comparison, normalized_alias)
            for alias in aliases
            if (normalized_alias := _normalized_header_text(alias))
        )
    }
    if len(fuzzy_keys) != 1:
        return None
    return _HeaderMatch(next(iter(fuzzy_keys)), True)


def _header_seeds(line_groups: tuple[_LineGroup, ...]) -> tuple[_HeaderSeed, ...]:
    seeds: list[_HeaderSeed] = []
    for line in line_groups:
        headers = [
            (block, match)
            for block in line.blocks
            if (match := _header_match(block.source.text)) is not None
        ]
        for start in range(max(0, len(headers) - 3)):
            sequence = headers[start : start + 4]
            if tuple(match.key for _, match in sequence) != _HEADER_ORDER:
                continue
            if sum(match.fuzzy for _, match in sequence) > 1:
                continue
            header_blocks = (
                sequence[0][0],
                sequence[1][0],
                sequence[2][0],
                sequence[3][0],
            )
            seed = _header_seed(header_blocks, line.blocks)
            if seed is not None:
                seeds.append(seed)

    for upper, lower in zip(line_groups, line_groups[1:], strict=False):
        upper_headers = tuple(
            (block, match)
            for block in upper.blocks
            if (match := _header_match(block.source.text)) is not None
        )
        lower_headers = tuple(
            (block, match)
            for block in lower.blocks
            if (match := _header_match(block.source.text)) is not None
        )
        if (
            tuple(match.key for _, match in upper_headers) != ("name",)
            or tuple(match.key for _, match in lower_headers) != ("dose", "times", "days")
            or sum(match.fuzzy for _, match in (*upper_headers, *lower_headers)) > 1
        ):
            continue
        upper_header_bbox = upper_headers[0][0].bbox
        lower_header_bbox = _union(block.bbox for block, _ in lower_headers)
        vertical_gap = lower_header_bbox.y_min - upper_header_bbox.y_max
        typical_height = median(
            (
                upper_headers[0][0].bbox.height,
                *(block.bbox.height for block, _ in lower_headers),
            )
        )
        if (
            vertical_gap < -typical_height * 0.25
            or vertical_gap > typical_height * _MAX_SPLIT_HEADER_VERTICAL_GAP
        ):
            continue
        header_blocks = (
            upper_headers[0][0],
            lower_headers[0][0],
            lower_headers[1][0],
            lower_headers[2][0],
        )
        seed = _header_seed(header_blocks, lower.blocks)
        if seed is not None:
            seeds.append(seed)
    seeds.extend(_diagonal_header_seeds(line_groups))
    seeds = list(
        {
            tuple(block_id for block in seed.blocks for block_id in block.source_block_ids): seed
            for seed in seeds
        }.values()
    )
    seeds.sort(
        key=lambda seed: (
            seed.bbox.center_y,
            seed.bbox.x_min,
            tuple(block.provider_order for block in seed.blocks),
        )
    )
    return tuple(seeds)


def _diagonal_header_seeds(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_HeaderSeed, ...]:
    original = tuple(block for line in line_groups for block in line.blocks)
    tokens = (*original, *_joined_header_fragments(original))
    matched = tuple(
        (block, match)
        for block in tokens
        if (match := _header_match(block.source.text)) is not None
    )
    seeds: list[_HeaderSeed] = []
    for name, name_match in matched:
        if name_match.key != "name":
            continue
        sequence = [(name, name_match)]
        for key in _HEADER_ORDER[1:]:
            previous = sequence[-1][0]
            choices = tuple(
                (block, match)
                for block, match in matched
                if match.key == key
                and block.bbox.center_x > previous.bbox.center_x
                and abs(block.bbox.center_y - name.bbox.center_y)
                <= max(block.bbox.height, name.bbox.height) * 2.5
            )
            if not choices:
                break
            sequence.append(
                min(
                    choices,
                    key=lambda item: (
                        item[0].bbox.center_x,
                        abs(item[0].bbox.center_y - name.bbox.center_y),
                        item[0].provider_order,
                    ),
                )
            )
        if (
            len(sequence) != 4
            or sum(match.fuzzy for _, match in sequence) > 1
        ):
            continue
        blocks = tuple(block for block, _ in sequence)
        heights = tuple(block.bbox.height for block in blocks)
        centers_y = tuple(block.bbox.center_y for block in blocks)
        if max(centers_y) - min(centers_y) > median(heights) * 2.5:
            continue
        seed = _header_seed(
            (blocks[0], blocks[1], blocks[2], blocks[3]),
            original,
        )
        if seed is not None:
            seeds.append(seed)
    return tuple(seeds)


def _joined_header_fragments(
    blocks: tuple[_GeometryBlock, ...],
) -> tuple[_GeometryBlock, ...]:
    aliases = tuple(
        normalized
        for aliases in _HEADER_ALIASES.values()
        for alias in aliases
        if len(normalized := _normalized_header_text(alias)) >= 5
        and all("가" <= character <= "힣" for character in normalized)
    )
    singles = tuple(
        block
        for block in blocks
        if len(text := _normalized_header_text(block.source.text)) == 1
        and "가" <= text <= "힣"
    )
    joined: list[_GeometryBlock] = []
    for alias in aliases:
        for first in singles:
            if _normalized_header_text(first.source.text) != alias[0]:
                continue
            sequence = [first]
            for character in alias[1:]:
                previous = sequence[-1]
                choices = tuple(
                    candidate
                    for candidate in singles
                    if candidate not in sequence
                    and _normalized_header_text(candidate.source.text) == character
                    and candidate.bbox.center_x > previous.bbox.center_x
                    and candidate.bbox.x_min - previous.bbox.x_max
                    <= max(candidate.bbox.height, previous.bbox.height) * 1.5
                    and abs(candidate.bbox.center_y - previous.bbox.center_y)
                    <= max(candidate.bbox.height, previous.bbox.height) * 1.25
                )
                if not choices:
                    break
                sequence.append(
                    min(
                        choices,
                        key=lambda candidate: (
                            candidate.bbox.center_x,
                            abs(candidate.bbox.center_y - previous.bbox.center_y),
                            candidate.provider_order,
                        ),
                    )
                )
            if len(sequence) != len(alias):
                continue
            confidences = tuple(
                block.source.confidence
                for block in sequence
                if block.source.confidence is not None
                and math.isfinite(block.source.confidence)
            )
            source_issues = tuple(
                dict.fromkeys(
                    issue for block in sequence for issue in block.source_issues
                )
            )
            joined.append(
                _GeometryBlock(
                    source=replace(
                        first.source,
                        text=alias,
                        confidence=(
                            sum(confidences) / len(confidences)
                            if confidences
                            else None
                        ),
                        issues=source_issues,
                    ),
                    bbox=_union(block.bbox for block in sequence),
                    provider_order=first.provider_order,
                    source_issues=source_issues,
                    source_block_ids=tuple(
                        block_id
                        for block in sequence
                        for block_id in block.source_block_ids
                    ),
                )
            )
    return tuple(joined)


def _header_seed(
    header_blocks: tuple[
        _GeometryBlock,
        _GeometryBlock,
        _GeometryBlock,
        _GeometryBlock,
    ],
    trailing_blocks: tuple[_GeometryBlock, ...],
) -> _HeaderSeed | None:
    centers = tuple(block.bbox.center_x for block in header_blocks)
    if not all(centers[index] < centers[index + 1] for index in range(3)):
        return None
    boundaries = tuple(
        (centers[index] + centers[index + 1]) / 2.0 for index in range(3)
    )
    left_edge = centers[0] - (centers[1] - centers[0]) / 2.0
    trailing_amount_centers = tuple(
        block.bbox.center_x
        for block in trailing_blocks
        if block.bbox.center_x > centers[3]
        and _normalized_header_text(block.source.text) in _TRAILING_AMOUNT_ALIASES
    )
    numeric_right_bound = (
        (centers[3] + min(trailing_amount_centers)) / 2.0
        if trailing_amount_centers
        else None
    )
    right_edge = (
        numeric_right_bound
        if numeric_right_bound is not None
        else centers[3] + (centers[3] - centers[2]) / 2.0
    )
    bands = (
        (left_edge, boundaries[0]),
        (boundaries[0], boundaries[1]),
        (boundaries[1], boundaries[2]),
        (boundaries[2], right_edge),
    )
    header_bbox = _union(block.bbox for block in header_blocks)
    return _HeaderSeed(
        blocks=header_blocks,
        bands=bands,
        bbox=AxisAlignedBBox(
            left_edge,
            header_bbox.y_min,
            right_edge,
            header_bbox.y_max,
        ),
        numeric_right_bound=numeric_right_bound,
    )


def _guidance_layout_rows(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[LayoutRow, ...]:
    headers = _guidance_headers(line_groups)
    if len(headers) != 1:
        return ()
    header = headers[0]
    rows: list[LayoutRow] = []
    for line in line_groups:
        if line.bbox.center_y <= header.bbox.center_y:
            continue
        instruction_blocks = tuple(
            block
            for block in line.blocks
            if header.instruction_band[0]
            <= block.bbox.center_x
            <= header.instruction_band[1]
        )
        name_blocks = [
            block
            for block in line.blocks
            if header.name_band[0] <= block.bbox.center_x <= header.name_band[1]
        ]
        name_cell = _layout_cell(name_blocks)
        if name_cell is None:
            continue
        if not _guidance_prefix_starts_near_name(
            header,
            name_cell,
            instruction_blocks,
        ):
            continue
        parsed = _guidance_instruction_cells(instruction_blocks)
        if parsed is None:
            continue
        dose_cell, times_cell, days_cell = parsed
        cells: LayoutCells = (name_cell, dose_cell, times_cell, days_cell)
        rows.append(
            LayoutRow(
                row_id=f"guidance-row-{len(rows) + 1:04d}",
                cells=cells,
                bbox=_union(cell.bbox for cell in cells if cell is not None),
            )
        )
    return tuple(rows)


def _combined_guidance_candidates(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[TableCandidate, ...]:
    """Build a grounded table when one OCR block contains a full row schedule."""

    headers = _guidance_headers(line_groups)
    if not headers:
        headers = _compact_schedule_headers(line_groups)
    if len(headers) != 1:
        return ()
    header = headers[0]
    efficacy_lane_left = _repeated_bracket_label_lane_left(line_groups, header)
    rows: list[LayoutRow] = []
    normalized_names: set[str] = set()
    strict_schedule_count = 0
    fuzzy_schedule_count = 0
    for line in line_groups:
        if line.bbox.center_y <= header.bbox.center_y:
            continue
        schedules = tuple(
            (block, match, strict)
            for block in line.blocks
            if header.instruction_band[0]
            <= block.bbox.center_x
            <= header.instruction_band[1]
            and (
                parsed := _combined_guidance_schedule_match(
                    _compact_text(block.source.text)
                )
            )
            is not None
            for match, strict in (parsed,)
        )
        if len(schedules) != 1:
            continue
        schedule_block, schedule_match, schedule_is_strict = schedules[0]
        name_blocks = tuple(
            block
            for block in line.blocks
            if header.name_band[0]
            <= block.bbox.center_x
            <= header.name_band[1]
            and _contains_hangul(block.source.text)
            and _header_match(block.source.text) is None
            and _SUMMARY_ROW_MARKER_PATTERN.search(block.source.text) is None
            and (
                efficacy_lane_left is None
                or block.bbox.x_min < efficacy_lane_left
            )
        )
        if not name_blocks or not _looks_like_medication_name(name_blocks):
            continue
        name_cell = _layout_cell(list(name_blocks))
        schedule_cell = _layout_cell([schedule_block])
        if name_cell is None or schedule_cell is None:
            continue
        normalized_name = _compact_text(name_cell.text)
        if normalized_name in normalized_names:
            return ()
        normalized_names.add(normalized_name)
        strict_schedule_count += int(schedule_is_strict)
        fuzzy_schedule_count += int(not schedule_is_strict)
        dose_cell = replace(
            schedule_cell,
            parsed_text=schedule_match.group("dose"),
        )
        times_cell = replace(
            schedule_cell,
            parsed_text=schedule_match.group("times"),
        )
        days_cell = replace(
            schedule_cell,
            parsed_text=schedule_match.group("days"),
        )
        cells: LayoutCells = (name_cell, dose_cell, times_cell, days_cell)
        rows.append(
            LayoutRow(
                row_id=f"row-{len(rows) + 1:04d}",
                cells=cells,
                bbox=_union(
                    (
                        name_cell.bbox,
                        dose_cell.bbox,
                        times_cell.bbox,
                        days_cell.bbox,
                    )
                ),
            )
        )
    if len(rows) < 2 or fuzzy_schedule_count > strict_schedule_count:
        return ()

    observed_cells = [cell for row in rows for cell in row.cells if cell is not None]
    confidence_count = sum(cell.valid_confidence_count for cell in observed_cells)
    confidence_sum = sum(
        (cell.confidence or 0.0) * cell.valid_confidence_count
        for cell in observed_cells
    )
    first_cells = tuple(cell for cell in rows[0].cells if cell is not None)
    if len(first_cells) != 4:
        return ()
    header_columns = tuple(
        HeaderColumn(
            key=key,
            source_text="",
            block_ids=(),
            bbox=cell.bbox,
            band_min=cell.bbox.x_min,
            band_max=cell.bbox.x_max,
        )
        for key, cell in zip(_HEADER_ORDER, first_cells, strict=True)
    )
    return (
        TableCandidate(
            candidate_id="table-guidance-combined-0001",
            bbox=_union((header.bbox, *(row.bbox for row in rows))),
            header_columns=(
                header_columns[0],
                header_columns[1],
                header_columns[2],
                header_columns[3],
            ),
            rows=tuple(rows),
            ambiguous_column_evidence=(),
            column_consistency=1.0,
            confidence_coverage=1.0 if confidence_count else 0.0,
            mean_confidence=(
                confidence_sum / confidence_count if confidence_count else None
            ),
        ),
    )


def _repeated_bracket_label_lane_left(
    line_groups: tuple[_LineGroup, ...],
    header: _GuidanceHeader,
) -> float | None:
    candidates = tuple(
        (line_index, block)
        for line_index, line in enumerate(line_groups)
        if line.bbox.center_y > header.bbox.center_y
        for block in line.blocks
        if header.name_band[0]
        <= block.bbox.x_min
        < header.instruction_band[0]
        and _compact_text(block.source.text).startswith("[")
    )
    if len(candidates) < 2:
        return None

    tolerance = max(4.0, median(block.bbox.height for _, block in candidates))
    clusters = tuple(
        tuple(
            candidate
            for candidate in candidates
            if abs(candidate[1].bbox.x_min - anchor.bbox.x_min) <= tolerance
        )
        for _, anchor in candidates
    )
    lane = max(
        clusters,
        key=lambda cluster: (
            len({line_index for line_index, _ in cluster}),
            -max(block.bbox.x_min for _, block in cluster)
            + min(block.bbox.x_min for _, block in cluster),
        ),
    )
    if len({line_index for line_index, _ in lane}) < 2:
        return None
    return min(block.bbox.x_min for _, block in lane)


def _combined_guidance_schedule_match(
    text: str,
) -> tuple[re.Match[str], bool] | None:
    strict = _COMBINED_GUIDANCE_SCHEDULE_PATTERN.fullmatch(text)
    if strict is not None:
        return strict, True
    fuzzy = _FUZZY_COMBINED_GUIDANCE_SCHEDULE_PATTERN.fullmatch(text)
    return (fuzzy, False) if fuzzy is not None else None


def _headerless_correlated_receipt_candidates(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[TableCandidate, ...]:
    """Recover one strict numeric medication grid using cross-document semantics."""

    semantics = _unique_headerless_medication_semantics(line_groups)
    row_seeds: list[_HeaderlessReceiptRow] = []
    invalid_row_lines: list[_LineGroup] = []
    for line in line_groups:
        row_seed, row_like = _headerless_receipt_row(line)
        if row_seed is not None:
            row_seeds.append(row_seed)
        elif row_like:
            invalid_row_lines.append(line)
    rows = tuple(sorted(row_seeds, key=lambda row: row.center_y))
    if not (
        _MIN_HEADERLESS_RECEIPT_ROWS
        <= len(rows)
        <= _MAX_HEADERLESS_RECEIPT_ROWS
    ):
        return ()
    missing_name_indexes = tuple(
        index for index, row in enumerate(rows) if not row.name_blocks
    )
    if len(missing_name_indexes) > 1:
        return ()
    named_rows = tuple(row for row in rows if row.name_blocks)
    if len(named_rows) < 2 or not _headerless_name_lane_is_stable(named_rows):
        return ()
    normalized_names = tuple(
        _compact_text(" ".join(block.source.text for block in row.name_blocks))
        for row in named_rows
    )
    if len(set(normalized_names)) != len(normalized_names):
        return ()
    if missing_name_indexes:
        if not _headerless_split_row_is_adjacent(rows, missing_name_indexes[0]):
            return ()
        if not _headerless_row_spacing_is_stable(named_rows):
            return ()
    elif not _headerless_row_spacing_is_stable(rows):
        return ()
    derived_total_blocks = _validated_headerless_derived_totals(rows)
    if derived_total_blocks is None:
        return ()
    local_numeric_headers = _local_headerless_numeric_headers(rows, line_groups)
    consistency = _headerless_numeric_track_consistency(
        rows,
        bbox_margin_factor=0.10 if local_numeric_headers is not None else 0.15,
    )
    if consistency is None:
        return ()
    context: _HeaderlessContextEvidence | None = None
    if local_numeric_headers is not None:
        if missing_name_indexes or not all(
            _looks_like_headerless_medication_name(row.name_blocks) for row in rows
        ):
            return ()
        output_name_blocks = tuple(row.name_blocks for row in rows)
        context_approval_ids: tuple[str, ...] = ()
        approval_evidence_blocks: tuple[_GeometryBlock, ...] = local_numeric_headers
        invalid_row_centers = [line.bbox.center_y for line in invalid_row_lines]
    else:
        if semantics is None:
            return ()
        strict_contexts = _headerless_strict_contexts(line_groups)
        weak_contexts = _headerless_weak_contexts(
            line_groups,
            rows,
            semantics,
        )
        if len(strict_contexts) > 1 or (strict_contexts and weak_contexts):
            return ()
        if strict_contexts:
            context = strict_contexts[0]
        elif len(weak_contexts) == 1:
            context = weak_contexts[0]
        else:
            return ()
        invalid_row_centers = [
            line.bbox.center_y
            for line in invalid_row_lines
            if not _headerless_line_belongs_to_context(line, context)
        ]
        peer_evidence = _headerless_peer_name_evidence(
            line_groups,
            rows,
            semantics,
            context,
        )
        if peer_evidence is None or not _headerless_approval_is_spatially_local(
            rows,
            semantics,
            peer_evidence.peer_blocks,
            context,
        ):
            return ()
        if not _headerless_final_names_are_valid(
            rows,
            peer_evidence,
            context,
        ):
            return ()
        output_name_blocks = peer_evidence.output_name_blocks
        context_approval_ids = context.approval_block_ids
        approval_evidence_blocks = (
            *semantics.header_blocks,
            semantics.guidance_block,
            *peer_evidence.peer_blocks,
        )
    if _invalid_headerless_row_is_near_cluster(rows, invalid_row_centers):
        return ()

    layout_rows: list[LayoutRow] = []
    for index, (row, name_blocks) in enumerate(
        zip(rows, output_name_blocks, strict=True),
        start=1,
    ):
        name_cell = _layout_cell(list(name_blocks))
        numeric_cells = tuple(
            replace(cell, parsed_text=parsed)
            for block, parsed in zip(
                row.numeric_blocks,
                row.parsed_values,
                strict=True,
            )
            if (cell := _layout_cell([block])) is not None
        )
        if name_cell is None or len(numeric_cells) != 3:
            return ()
        cells: LayoutCells = (
            name_cell,
            numeric_cells[0],
            numeric_cells[1],
            numeric_cells[2],
        )
        layout_rows.append(
            LayoutRow(
                row_id=f"row-{index:04d}",
                cells=cells,
                bbox=_union(cell.bbox for cell in cells if cell is not None),
            )
        )

    columns: list[HeaderColumn] = []
    for column_index, key in enumerate(_HEADER_ORDER):
        column_cells: list[LayoutCell] = []
        for layout_row in layout_rows:
            cell = layout_row.cells[column_index]
            if cell is None:
                return ()
            column_cells.append(cell)
        if len(column_cells) != len(layout_rows) or not column_cells:
            return ()
        column_bbox = _union(cell.bbox for cell in column_cells)
        columns.append(
            HeaderColumn(
                key=key,
                source_text="",
                block_ids=(),
                bbox=column_bbox,
                band_min=min(cell.bbox.x_min for cell in column_cells),
                band_max=max(cell.bbox.x_max for cell in column_cells),
            )
        )

    observed_cells = tuple(
        cell for row in layout_rows for cell in row.cells if cell is not None
    )
    confidence_count = sum(cell.valid_confidence_count for cell in observed_cells)
    confidence_total = sum(len(cell.block_ids) for cell in observed_cells)
    confidence_sum = sum(
        (cell.confidence or 0.0) * cell.valid_confidence_count
        for cell in observed_cells
    )
    approval_blocks = (
        *approval_evidence_blocks,
        *(block for row in rows for block in row.name_evidence_blocks),
        *derived_total_blocks,
    )
    approval_block_ids = tuple(
        dict.fromkeys(
            (
                *(block.source.block_id for block in approval_blocks),
                *context_approval_ids,
            )
        )
    )
    return (
        TableCandidate(
            candidate_id="table-headerless-correlated-0001",
            bbox=_union(row.bbox for row in layout_rows),
            header_columns=(columns[0], columns[1], columns[2], columns[3]),
            rows=tuple(layout_rows),
            ambiguous_column_evidence=(),
            column_consistency=consistency,
            confidence_coverage=(
                confidence_count / confidence_total if confidence_total else 0.0
            ),
            mean_confidence=(
                confidence_sum / confidence_count if confidence_count else None
            ),
            approval_block_ids=approval_block_ids,
            observed_header_coverage=0,
            header_inferred=True,
        ),
    )


def _unique_headerless_medication_semantics(
    line_groups: tuple[_LineGroup, ...],
) -> _HeaderlessSemantics | None:
    blocks = tuple(block for line in line_groups for block in line.blocks)
    matches = tuple(
        (block, match)
        for block in blocks
        if (match := _header_match(block.source.text)) is not None
    )
    if any(
        sum(match.key == key for _, match in matches) != 1
        for key in _HEADER_ORDER
    ):
        return None
    if sum(match.fuzzy for _, match in matches) > 1:
        return None
    guidance_anchors = tuple(
        block
        for block in blocks
        if "복약안내" in _normalized_header_text(block.source.text)
    )
    if (
        len(guidance_anchors) != 1
        or _normalized_header_text(
            guidance_anchors[0].source.text
        ).count("복약안내")
        != 1
    ):
        return None
    ordered = tuple(
        next((block, match) for block, match in matches if match.key == key)
        for key in _HEADER_ORDER
    )
    return _HeaderlessSemantics(
        header_blocks=(ordered[0][0], ordered[1][0], ordered[2][0], ordered[3][0]),
        header_matches=(ordered[0][1], ordered[1][1], ordered[2][1], ordered[3][1]),
        guidance_block=guidance_anchors[0],
    )


def _local_headerless_numeric_headers(
    rows: tuple[_HeaderlessReceiptRow, ...],
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_GeometryBlock, _GeometryBlock, _GeometryBlock] | None:
    """Return exact numeric headers only when they sit directly above the row grid."""

    numeric_matches = tuple(
        (block, match)
        for line in line_groups
        for block in line.blocks
        if (match := _header_match(block.source.text)) is not None
        and match.key in _HEADER_ORDER[1:]
        and not match.fuzzy
    )
    if any(
        sum(match.key == key for _, match in numeric_matches) != 1
        for key in _HEADER_ORDER[1:]
    ):
        return None
    ordered = tuple(
        next(block for block, match in numeric_matches if match.key == key)
        for key in _HEADER_ORDER[1:]
    )
    headers = (ordered[0], ordered[1], ordered[2])
    header_ids = {block.source.block_id for block in headers}
    if not any(
        header_ids <= {block.source.block_id for block in line.blocks}
        for line in line_groups
    ):
        return None
    if not rows or any(not row.name_blocks for row in rows):
        return None

    typical_row_height = median(row.bbox.height for row in rows)
    typical_header_height = median(block.bbox.height for block in headers)
    if max(block.bbox.center_y for block in headers) - min(
        block.bbox.center_y for block in headers
    ) > max(typical_row_height, typical_header_height):
        return None

    header_bbox = _union(block.bbox for block in headers)
    vertical_gap = rows[0].bbox.y_min - header_bbox.y_max
    if not -typical_row_height * 0.35 <= vertical_gap <= typical_row_height * 1.5:
        return None

    track_centers = tuple(
        median(row.numeric_blocks[index].bbox.center_x for row in rows)
        for index in range(3)
    )
    if not all(
        _axis_gap(
            center,
            center,
            header.bbox.x_min,
            header.bbox.x_max,
        )
        <= max(typical_row_height, header.bbox.width * 0.25)
        for center, header in zip(track_centers, headers, strict=True)
    ):
        return None
    return headers


def _headerless_receipt_row(
    line: _LineGroup,
) -> tuple[_HeaderlessReceiptRow | None, bool]:
    structural = tuple(
        sorted(
            (
                block
                for block in line.blocks
                if _is_structural_numeric(block.source.text)
            ),
            key=lambda block: (block.bbox.center_x, block.provider_order),
        )
    )
    if not structural:
        return None, False
    name_blocks = _headerless_receipt_name_blocks(line.blocks, structural[0])
    name_evidence_blocks = tuple(
        block
        for block in line.blocks
        if block.bbox.center_x < structural[0].bbox.x_min
        and _HEADERLESS_NAME_STRENGTH_PATTERN.fullmatch(
            _compact_text(block.source.text)
        )
        is not None
    )
    has_plausible_name = _looks_like_headerless_medication_name(name_blocks)
    if (name_blocks and not has_plausible_name) or len(name_evidence_blocks) > 1:
        return None, False
    digit_blocks = tuple(
        block for block in line.blocks if _contains_digit(block.source.text)
    )
    allowed_digit_ids = {
        *(block.source.block_id for block in name_blocks),
        *(block.source.block_id for block in name_evidence_blocks),
        *(block.source.block_id for block in structural),
    }
    if (
        len(structural) not in {3, 4}
        or any(
            block.source.block_id not in allowed_digit_ids for block in digit_blocks
        )
    ):
        return None, has_plausible_name or len(structural) >= 3
    parsed_values = _headerless_numeric_values(
        (structural[0], structural[1], structural[2])
    )
    if parsed_values is None:
        return None, True
    name_bbox = _union(block.bbox for block in name_blocks) if name_blocks else None
    if name_bbox is not None and name_bbox.x_max >= structural[0].bbox.center_x:
        return None, True
    member_boxes = (
        *((name_bbox,) if name_bbox is not None else ()),
        *(block.bbox for block in name_evidence_blocks),
        *(block.bbox for block in structural),
    )
    typical_height = median(box.height for box in member_boxes)
    if (
        max(box.center_y for box in member_boxes)
        - min(box.center_y for box in member_boxes)
        > typical_height * 0.90
    ):
        return None, True
    return (
        _HeaderlessReceiptRow(
            name_blocks=name_blocks,
            name_evidence_blocks=name_evidence_blocks,
            numeric_blocks=(structural[0], structural[1], structural[2]),
            derived_total_block=structural[3] if len(structural) == 4 else None,
            parsed_values=parsed_values,
            center_y=median(block.bbox.center_y for block in structural),
            bbox=_union(member_boxes),
        ),
        True,
    )


def _headerless_receipt_name_blocks(
    blocks: tuple[_GeometryBlock, ...],
    first_numeric: _GeometryBlock,
) -> tuple[_GeometryBlock, ...]:
    eligible = tuple(
        block
        for block in blocks
        if block.bbox.center_x < first_numeric.bbox.x_min
        and _header_match(block.source.text) is None
        and not _is_structural_numeric(block.source.text)
        and _HEADERLESS_NAME_STRENGTH_PATTERN.fullmatch(
            _compact_text(block.source.text)
        )
        is None
        and (
            not _contains_digit(block.source.text)
            or _contains_hangul(block.source.text)
        )
    )
    if not eligible:
        return ()
    ordered = tuple(
        sorted(eligible, key=lambda block: (block.bbox.x_min, block.provider_order))
    )
    typical_height = median(block.bbox.height for block in ordered)
    groups: list[list[_GeometryBlock]] = []
    for block in ordered:
        if (
            groups
            and block.bbox.x_min - groups[-1][-1].bbox.x_max
            <= typical_height * 2.5
        ):
            groups[-1].append(block)
        else:
            groups.append([block])
    return tuple(max(groups, key=lambda group: max(block.bbox.x_max for block in group)))


def _looks_like_headerless_medication_name(
    blocks: tuple[_GeometryBlock, ...],
) -> bool:
    if not blocks:
        return False
    normalized = _compact_text(" ".join(block.source.text for block in blocks))
    return (
        sum("가" <= character <= "힣" for character in normalized) >= 2
        and _SUMMARY_ROW_MARKER_PATTERN.search(normalized) is None
        and _HEADERLESS_NON_MEDICATION_VOCABULARY_PATTERN.search(normalized) is None
        and "복약안내" not in normalized
        and "주의사항" not in normalized
    )


def _contains_digit(text: str) -> bool:
    return any(character.isdigit() for character in unicodedata.normalize("NFKC", text))


def _headerless_numeric_values(
    blocks: tuple[_GeometryBlock, ...],
) -> tuple[str, str, str] | None:
    dose = _compact_text(blocks[0].source.text)
    times = _compact_text(blocks[1].source.text)
    days = _compact_text(blocks[2].source.text)
    if _headerless_quantity_fraction(dose) is None:
        return None
    times_match = _HEADERLESS_TIMES_PATTERN.fullmatch(times)
    days_match = _HEADERLESS_DAYS_PATTERN.fullmatch(days)
    if times_match is None or days_match is None:
        return None
    times_value = _bounded_positive_integer(times_match.group(1))
    days_value = _bounded_positive_integer(days_match.group(1))
    if (
        times_value is None
        or days_value is None
        or not 1 <= times_value <= 6
        or not 1 <= days_value <= 365
    ):
        return None
    return dose, str(times_value), str(days_value)


def _headerless_quantity_fraction(text: str) -> Fraction | None:
    if (
        not text
        or len(text) > _MAX_HEADERLESS_NUMERIC_LENGTH
        or _HEADERLESS_DOSE_PATTERN.fullmatch(text) is None
    ):
        return None
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        if (
            _bounded_positive_integer(numerator) is None
            or _bounded_positive_integer(denominator) is None
        ):
            return None
    else:
        integer_part = text.split(".", 1)[0]
        if _bounded_nonnegative_integer(integer_part) is None:
            return None
    value = Fraction(text)
    return value if value > 0 else None


def _bounded_positive_integer(text: str) -> int | None:
    value = _bounded_nonnegative_integer(text)
    return value if value is not None and value > 0 else None


def _bounded_nonnegative_integer(text: str) -> int | None:
    if not text.isdigit() or len(text) > len(_MAX_JSON_SAFE_INTEGER_TEXT):
        return None
    normalized = text.lstrip("0") or "0"
    if (
        len(normalized) > len(_MAX_JSON_SAFE_INTEGER_TEXT)
        or len(normalized) == len(_MAX_JSON_SAFE_INTEGER_TEXT)
        and normalized > _MAX_JSON_SAFE_INTEGER_TEXT
    ):
        return None
    return int(normalized)


def _validated_headerless_derived_totals(
    rows: tuple[_HeaderlessReceiptRow, ...],
) -> tuple[_GeometryBlock, ...] | None:
    totals = tuple(row.derived_total_block for row in rows)
    if all(block is None for block in totals):
        return ()
    if len(rows) < 3 or any(block is None for block in totals):
        return None
    validated: list[_GeometryBlock] = []
    for row, total_block in zip(rows, totals, strict=True):
        if total_block is None:
            return None
        dose = _headerless_quantity_fraction(row.parsed_values[0])
        times = _bounded_positive_integer(row.parsed_values[1])
        days = _bounded_positive_integer(row.parsed_values[2])
        total = _headerless_quantity_fraction(_compact_text(total_block.source.text))
        if (
            dose is None
            or times is None
            or days is None
            or total is None
            or dose * times * days != total
        ):
            return None
        validated.append(total_block)
    return tuple(validated)


def _headerless_name_lane_is_stable(
    rows: tuple[_HeaderlessReceiptRow, ...],
) -> bool:
    left_bounds = tuple(
        _union(block.bbox for block in row.name_blocks).x_min for row in rows
    )
    typical_height = median(row.bbox.height for row in rows)
    first_track_gap = median(
        row.numeric_blocks[1].bbox.center_x - row.numeric_blocks[0].bbox.center_x
        for row in rows
    )
    return max(left_bounds) - min(left_bounds) <= max(
        typical_height,
        first_track_gap * 0.15,
    )


def _headerless_strict_contexts(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_HeaderlessContextEvidence, ...]:
    geometry_by_id = {
        block.source.block_id: block for line in line_groups for block in line.blocks
    }
    contexts: list[_HeaderlessContextEvidence] = []
    for context_rows in (
        _guidance_layout_rows(line_groups),
        _three_column_summary_rows(line_groups),
    ):
        if not context_rows:
            continue
        name_ids = tuple(
            cell.block_ids[0]
            for row in context_rows
            if (cell := row.cells[0]) is not None and len(cell.block_ids) == 1
        )
        if len(name_ids) != len(context_rows) or len(set(name_ids)) != len(name_ids):
            continue
        approval_ids = tuple(
            dict.fromkeys(
                block_id
                for row in context_rows
                for block_id in row.source_block_ids
            )
        )
        context_name_ids = set(name_ids)
        context_line_ids = frozenset(
            block.source.block_id
            for line in line_groups
            if context_name_ids.intersection(
                block.source.block_id for block in line.blocks
            )
            for block in line.blocks
        )
        contexts.append(
            _HeaderlessContextEvidence(
                name_blocks=tuple(geometry_by_id[block_id] for block_id in name_ids),
                approval_block_ids=approval_ids,
                bboxes=tuple(row.bbox for row in context_rows),
                context_line_block_ids=context_line_ids,
                weak=False,
            )
        )
    return tuple(contexts)


def _headerless_weak_contexts(
    line_groups: tuple[_LineGroup, ...],
    rows: tuple[_HeaderlessReceiptRow, ...],
    semantics: _HeaderlessSemantics,
) -> tuple[_HeaderlessContextEvidence, ...]:
    fuzzy_matches = tuple(match for match in semantics.header_matches if match.fuzzy)
    if (
        any(match.key != "name" for match in fuzzy_matches)
        or (len(rows) == 2 and fuzzy_matches)
    ):
        return ()
    primary_bbox, horizontal_budget, vertical_budget = _headerless_primary_geometry(rows)
    typical_height = median(row.bbox.height for row in rows)
    upper_limit = primary_bbox.y_min - typical_height * 1.5
    semantic_ids = {
        *(block.source.block_id for block in semantics.header_blocks),
        semantics.guidance_block.source.block_id,
    }
    upper_blocks = tuple(
        block
        for line in line_groups
        for block in line.blocks
        if block.bbox.y_max <= upper_limit
        and block.source.block_id not in semantic_ids
    )
    name_candidates = tuple(
        block
        for block in upper_blocks
        if _looks_like_headerless_medication_name((block,))
        and _header_match(block.source.text) is None
        and "복약안내" not in _normalized_header_text(block.source.text)
        and "주의사항" not in _normalized_header_text(block.source.text)
        and (
            not _weak_medication_signal(block)[0]
            or _weak_name_has_product_cue(block)
        )
    )
    if len(name_candidates) < len(rows):
        return ()
    anchor_candidates = tuple(
        block
        for row in rows
        if row.name_blocks
        for block in name_candidates
        if _compatible_inline_name(
            _inline_name_key(
                " ".join(item.source.text for item in row.name_blocks)
            ),
            _inline_name_key(block.source.text),
        )
    )
    if len({block.source.block_id for block in anchor_candidates}) < 2:
        return ()
    numeric_span = median(
        row.numeric_blocks[2].bbox.center_x
        - row.numeric_blocks[0].bbox.center_x
        for row in rows
    )
    lane_tolerance = max(2.0, typical_height * 0.60, numeric_span * 0.02)
    sequences: dict[tuple[str, ...], tuple[_GeometryBlock, ...]] = {}
    row_evidence_by_sequence: dict[
        tuple[str, ...], tuple[tuple[_WeakMedicationEvidence, ...], ...]
    ] = {}
    evaluated_pools: set[tuple[str, ...]] = set()
    for seed in anchor_candidates:
        pool = tuple(
            sorted(
                (
                    block
                    for block in name_candidates
                    if abs(block.bbox.x_min - seed.bbox.x_min) <= lane_tolerance
                ),
                key=lambda block: (block.bbox.center_y, block.provider_order),
            )
        )
        pool_ids = tuple(block.source.block_id for block in pool)
        if pool_ids in evaluated_pools:
            continue
        evaluated_pools.add(pool_ids)
        if (
            not len(rows) <= len(pool) <= len(rows) * 3
            or math.comb(len(pool), len(rows)) > 50_000
        ):
            continue
        for lane_items in combinations(pool, len(rows)):
            lane = tuple(lane_items)
            if (
                max(block.bbox.x_min for block in lane)
                - min(block.bbox.x_min for block in lane)
                > lane_tolerance
                or not _weak_name_sequence_spacing_is_stable(lane)
                or not _weak_name_sequence_is_separate(
                    lane,
                    primary_bbox,
                    typical_height,
                    horizontal_budget,
                    vertical_budget,
                )
            ):
                continue
            canonical_names = tuple(
                _inline_name_key(block.source.text) for block in lane
            )
            if not all(canonical_names) or len(set(canonical_names)) != len(lane):
                continue
            compatible_rows = tuple(
                bool(row.name_blocks)
                and _compatible_inline_name(
                    _inline_name_key(
                        " ".join(item.source.text for item in row.name_blocks)
                    ),
                    _inline_name_key(block.source.text),
                )
                for row, block in zip(rows, lane, strict=True)
            )
            anchors = tuple(
                index for index, compatible in enumerate(compatible_rows) if compatible
            )
            if len(rows) == 2:
                if anchors != (0, 1) or any(
                    _inline_name_key(
                        " ".join(item.source.text for item in row.name_blocks)
                    )
                    != _inline_name_key(block.source.text)
                    for row, block in zip(rows, lane, strict=True)
                ):
                    continue
            elif len(anchors) < 2:
                continue
            evidence_candidates = _weak_medication_line_evidence(
                line_groups,
                upper_limit,
                semantic_ids
                | {block.source.block_id for block in lane},
            )
            evidence_by_row = _weak_description_evidence(
                lane,
                evidence_candidates,
            )
            rich_row_count = sum(bool(evidence) for evidence in evidence_by_row)
            lexical_row_count = sum(
                any(evidence.lexical for evidence in row_evidence)
                for row_evidence in evidence_by_row
            )
            if (
                rich_row_count < math.ceil(len(rows) * 2 / 3)
                or lexical_row_count < min(2, len(rows))
                or any(
                    not compatible and not evidence
                    for compatible, evidence in zip(
                        compatible_rows,
                        evidence_by_row,
                        strict=True,
                    )
                )
            ):
                continue
            product_cues = tuple(_weak_name_has_product_cue(block) for block in lane)
            if (
                sum(product_cues) < min(2, len(rows))
                or not any(
                    _HEADERLESS_NAME_STRENGTH_PATTERN.search(
                        _compact_text(block.source.text)
                    )
                    is not None
                    for block in lane
                )
            ):
                continue
            sequence_ids = tuple(block.source.block_id for block in lane)
            sequences[sequence_ids] = lane
            row_evidence_by_sequence[sequence_ids] = evidence_by_row
    contexts: list[_HeaderlessContextEvidence] = []
    for sequence_ids, lane in sequences.items():
        evidence_by_row = row_evidence_by_sequence[sequence_ids]
        evidence_items = tuple(
            evidence
            for row_evidence in evidence_by_row
            for evidence in row_evidence
        )
        approval_blocks = tuple(
            dict.fromkeys(
                (
                    *lane,
                    *(block for evidence in evidence_items for block in evidence.blocks),
                )
            )
        )
        contexts.append(
            _HeaderlessContextEvidence(
                name_blocks=lane,
                approval_block_ids=tuple(
                    block.source.block_id for block in approval_blocks
                ),
                bboxes=(
                    *(block.bbox for block in lane),
                    *(evidence.bbox for evidence in evidence_items),
                ),
                context_line_block_ids=frozenset(
                    block.source.block_id for block in approval_blocks
                ),
                weak=True,
                row_evidence=evidence_by_row,
            )
        )
    return tuple(contexts)


def _weak_medication_line_evidence(
    line_groups: tuple[_LineGroup, ...],
    upper_limit: float,
    excluded_ids: set[str],
) -> tuple[_WeakMedicationEvidence, ...]:
    evidence: list[_WeakMedicationEvidence] = []
    for line in line_groups:
        if line.bbox.y_max > upper_limit:
            continue
        blocks = tuple(
            block
            for block in line.blocks
            if block.source.block_id not in excluded_ids
        )
        if not blocks:
            continue
        normalized = _compact_text(" ".join(block.source.text for block in blocks))
        if _HEADERLESS_NON_MEDICATION_VOCABULARY_PATTERN.search(normalized) is not None:
            continue
        lexical = _WEAK_MEDICATION_CONTEXT_PATTERN.search(normalized) is not None
        strength = _HEADERLESS_NAME_STRENGTH_PATTERN.search(normalized) is not None
        hangul_blocks = sum(_contains_hangul(block.source.text) for block in blocks)
        hangul_characters = sum(
            "가" <= character <= "힣" for character in normalized
        )
        rich = lexical or strength or (
            len(blocks) >= 3 and hangul_blocks >= 3 and hangul_characters >= 8
        )
        if rich:
            evidence.append(
                _WeakMedicationEvidence(
                    blocks=blocks,
                    bbox=_union(block.bbox for block in blocks),
                    lexical=lexical,
                    explicit=lexical or strength,
                )
            )
    return tuple(evidence)


def _weak_medication_signal(block: _GeometryBlock) -> tuple[bool, bool]:
    normalized = _compact_text(block.source.text)
    lexical = _WEAK_MEDICATION_CONTEXT_PATTERN.search(normalized) is not None
    strength = _HEADERLESS_NAME_STRENGTH_PATTERN.search(normalized) is not None
    return lexical or strength, lexical


def _weak_name_has_product_cue(block: _GeometryBlock) -> bool:
    normalized = _compact_text(block.source.text)
    return _WEAK_MEDICATION_PRODUCT_PATTERN.search(normalized) is not None


def _weak_name_sequence_spacing_is_stable(
    blocks: tuple[_GeometryBlock, ...],
) -> bool:
    typical_height = median(block.bbox.height for block in blocks)
    gaps = tuple(
        blocks[index + 1].bbox.center_y - blocks[index].bbox.center_y
        for index in range(len(blocks) - 1)
    )
    if any(gap <= typical_height * 0.75 for gap in gaps):
        return False
    typical_gap = median(gaps)
    return all(typical_gap * 0.55 <= gap <= typical_gap * 1.65 for gap in gaps)


def _weak_name_sequence_is_separate(
    blocks: tuple[_GeometryBlock, ...],
    primary_bbox: AxisAlignedBBox,
    typical_height: float,
    horizontal_budget: float,
    vertical_budget: float,
) -> bool:
    lane_bbox = _union(block.bbox for block in blocks)
    margin = typical_height * 1.5
    on_right = lane_bbox.x_min >= primary_bbox.x_max + margin
    on_left = lane_bbox.x_max <= primary_bbox.x_min - margin
    return (
        (on_right or on_left)
        and _axis_gap(
            lane_bbox.x_min,
            lane_bbox.x_max,
            primary_bbox.x_min,
            primary_bbox.x_max,
        )
        <= horizontal_budget
        and _axis_gap(
            lane_bbox.y_min,
            lane_bbox.y_max,
            primary_bbox.y_min,
            primary_bbox.y_max,
        )
        <= vertical_budget
    )


def _weak_description_evidence(
    name_blocks: tuple[_GeometryBlock, ...],
    signal_evidence: tuple[_WeakMedicationEvidence, ...],
) -> tuple[tuple[_WeakMedicationEvidence, ...], ...]:
    typical_height = median(block.bbox.height for block in name_blocks)
    name_gaps = tuple(
        name_blocks[index + 1].bbox.center_y - name_blocks[index].bbox.center_y
        for index in range(len(name_blocks) - 1)
    )
    vertical_limit = max(typical_height * 1.75, median(name_gaps) * 0.48)
    lane_bbox = _union(block.bbox for block in name_blocks)
    horizontal_limit = max(
        typical_height * 20.0,
        median(block.bbox.width for block in name_blocks) * 2.0,
    )
    evidence: list[list[_WeakMedicationEvidence]] = [[] for _ in name_blocks]
    for signal in signal_evidence:
        if _axis_gap(
            signal.bbox.x_min,
            signal.bbox.x_max,
            lane_bbox.x_min,
            lane_bbox.x_max,
        ) > horizontal_limit:
            continue
        distances = tuple(
            abs(signal.bbox.center_y - name.bbox.center_y)
            for name in name_blocks
        )
        ordered = sorted((distance, index) for index, distance in enumerate(distances))
        closest_distance, closest_index = ordered[0]
        if closest_distance > vertical_limit:
            continue
        if (
            len(ordered) > 1
            and ordered[1][0] - closest_distance <= typical_height * 0.10
        ):
            continue
        evidence[closest_index].append(signal)
    return tuple(tuple(items) for items in evidence)


def _headerless_line_belongs_to_context(
    line: _LineGroup,
    context: _HeaderlessContextEvidence,
) -> bool:
    line_ids = {block.source.block_id for block in line.blocks}
    return bool(line_ids.intersection(context.context_line_block_ids))


def _headerless_final_names_are_valid(
    rows: tuple[_HeaderlessReceiptRow, ...],
    peer_evidence: _HeaderlessPeerEvidence,
    context: _HeaderlessContextEvidence,
) -> bool:
    canonical_names: list[str] = []
    for final_blocks, peer_block in zip(
        peer_evidence.output_name_blocks,
        peer_evidence.peer_blocks,
        strict=True,
    ):
        if not final_blocks or not _looks_like_headerless_medication_name(final_blocks):
            return False
        canonical_name = _inline_name_key(
            " ".join(block.source.text for block in final_blocks)
        )
        if not canonical_name or (
            not context.weak
            and not _compatible_inline_name(
                canonical_name,
                _inline_name_key(peer_block.source.text),
            )
        ):
            return False
        canonical_names.append(canonical_name)
    return len(set(canonical_names)) == len(canonical_names)


def _headerless_split_row_is_adjacent(
    rows: tuple[_HeaderlessReceiptRow, ...],
    missing_index: int,
) -> bool:
    if missing_index != len(rows) - 1 or len(rows) < 4:
        return False
    typical_height = median(row.bbox.height for row in rows)
    gap = rows[-1].center_y - rows[-2].center_y
    return typical_height * 0.45 <= gap <= typical_height * 1.75


def _headerless_peer_name_evidence(
    line_groups: tuple[_LineGroup, ...],
    rows: tuple[_HeaderlessReceiptRow, ...],
    semantics: _HeaderlessSemantics,
    context: _HeaderlessContextEvidence,
) -> _HeaderlessPeerEvidence | None:
    if len(context.name_blocks) != len(rows):
        return None
    if context.weak:
        return _headerless_weak_peer_evidence(rows, semantics, context)
    context_name_ids = {
        block.source.block_id for block in context.name_blocks
    }
    if len(context_name_ids) != len(context.name_blocks):
        return None
    primary_bbox, max_horizontal_gap, _ = _headerless_primary_geometry(rows)
    body_ids = {
        block.source.block_id
        for row in rows
        for block in (
            *row.name_blocks,
            *row.name_evidence_blocks,
            *row.numeric_blocks,
            *((row.derived_total_block,) if row.derived_total_block is not None else ()),
        )
    }
    approval_ids = {
        *(block.source.block_id for block in semantics.header_blocks),
        semantics.guidance_block.source.block_id,
    }
    typical_height = median(row.bbox.height for row in rows)
    horizontal_margin = typical_height * 1.5
    candidates: list[tuple[_GeometryBlock, str]] = []
    untrusted_candidates: list[tuple[_GeometryBlock, str]] = []
    for line in line_groups:
        is_context_line = _headerless_line_belongs_to_context(line, context)
        for block in line.blocks:
            if block.source.block_id in body_ids or block.source.block_id in approval_ids:
                continue
            normalized = _compact_text(block.source.text)
            if (
                not _contains_hangul(normalized)
                or _header_match(normalized) is not None
                or "복약안내" in normalized
                or "주의사항" in normalized
                or _SUMMARY_ROW_MARKER_PATTERN.search(normalized) is not None
            ):
                continue
            if is_context_line and block.source.block_id not in context_name_ids:
                continue
            if block.bbox.x_min >= primary_bbox.x_max + horizontal_margin:
                side = "right"
                horizontal_gap = block.bbox.x_min - primary_bbox.x_max
            elif block.bbox.x_max <= primary_bbox.x_min - horizontal_margin:
                side = "left"
                horizontal_gap = primary_bbox.x_min - block.bbox.x_max
            else:
                continue
            if horizontal_gap <= max_horizontal_gap:
                target = (
                    candidates
                    if block.source.block_id in context_name_ids
                    else untrusted_candidates
                )
                target.append((block, side))

    mapped: list[tuple[_GeometryBlock, str]] = []
    for row in rows:
        if not row.name_blocks:
            continue
        receipt_key = _inline_name_key(
            " ".join(block.source.text for block in row.name_blocks)
        )
        row_candidates = tuple(
            (block, side)
            for block, side in candidates
            if abs(block.bbox.center_y - row.center_y)
            <= median((block.bbox.height, row.bbox.height)) * 1.10
            and _compatible_inline_name(
                receipt_key,
                _inline_name_key(block.source.text),
            )
        )
        has_untrusted_match = any(
            abs(block.bbox.center_y - row.center_y)
            <= median((block.bbox.height, row.bbox.height)) * 1.10
            and _compatible_inline_name(
                receipt_key,
                _inline_name_key(block.source.text),
            )
            for block, _ in untrusted_candidates
        )
        if len(row_candidates) != 1 or has_untrusted_match:
            return None
        mapped.append(row_candidates[0])
    if len(mapped) < 2 or len({block.source.block_id for block, _ in mapped}) != len(mapped):
        return None
    sides = {side for _, side in mapped}
    if len(sides) != 1:
        return None
    side = next(iter(sides))
    peer_centers = tuple(block.bbox.center_x for block, _ in mapped)
    lane_tolerance = max(
        typical_height * 2.5,
        median(block.bbox.width for block, _ in mapped) * 1.5,
    )
    if max(peer_centers) - min(peer_centers) > lane_tolerance:
        return None
    if len(rows) == 2:
        if semantics.header_matches[0].fuzzy or any(
            _inline_name_key(" ".join(block.source.text for block in row.name_blocks))
            != _inline_name_key(peer.source.text)
            for row, (peer, _) in zip(rows, mapped, strict=True)
        ):
            return None

    recovered_name_block = None
    missing_rows = tuple(row for row in rows if not row.name_blocks)
    if missing_rows:
        missing_row = missing_rows[0]
        lane_center = median(peer_centers)
        if any(
            candidate_side == side
            and abs(block.bbox.center_y - missing_row.center_y)
            <= median((block.bbox.height, missing_row.bbox.height)) * 1.10
            for block, candidate_side in untrusted_candidates
        ):
            return None
        unmatched = tuple(
            block
            for block, candidate_side in candidates
            if candidate_side == side
            and block.source.block_id
            not in {mapped_block.source.block_id for mapped_block, _ in mapped}
            and abs(block.bbox.center_y - missing_row.center_y)
            <= median((block.bbox.height, missing_row.bbox.height)) * 1.10
            and abs(block.bbox.center_x - lane_center) <= lane_tolerance
        )
        if len(unmatched) != 1:
            return None
        recovered_name_block = unmatched[0]
        mapped.append((recovered_name_block, side))
    if len(mapped) != len(rows):
        return None
    if {block.source.block_id for block, _ in mapped} != context_name_ids:
        return None
    return _HeaderlessPeerEvidence(
        peer_blocks=tuple(block for block, _ in mapped),
        recovered_name_block=recovered_name_block,
        output_name_blocks=tuple(
            row.name_blocks
            or (
                (recovered_name_block,)
                if recovered_name_block is not None
                else ()
            )
            for row in rows
        ),
    )


def _headerless_weak_peer_evidence(
    rows: tuple[_HeaderlessReceiptRow, ...],
    semantics: _HeaderlessSemantics,
    context: _HeaderlessContextEvidence,
) -> _HeaderlessPeerEvidence | None:
    anchors: list[int] = []
    for index, (row, peer) in enumerate(
        zip(rows, context.name_blocks, strict=True)
    ):
        if not row.name_blocks:
            continue
        receipt_name = _inline_name_key(
            " ".join(block.source.text for block in row.name_blocks)
        )
        peer_name = _inline_name_key(peer.source.text)
        if _compatible_inline_name(receipt_name, peer_name):
            anchors.append(index)
    if len(rows) == 2:
        if semantics.header_matches[0].fuzzy or anchors != [0, 1] or any(
            _inline_name_key(
                " ".join(block.source.text for block in row.name_blocks)
            )
            != _inline_name_key(peer.source.text)
            for row, peer in zip(rows, context.name_blocks, strict=True)
        ):
            return None
    elif len(anchors) < 2:
        return None
    missing_indexes = tuple(
        index for index, row in enumerate(rows) if not row.name_blocks
    )
    recovered_name = (
        context.name_blocks[missing_indexes[0]] if missing_indexes else None
    )
    output_name_blocks = tuple(
        row.name_blocks or (peer,)
        for row, peer in zip(rows, context.name_blocks, strict=True)
    )
    return _HeaderlessPeerEvidence(
        peer_blocks=context.name_blocks,
        recovered_name_block=recovered_name,
        output_name_blocks=output_name_blocks,
    )


def _headerless_approval_is_spatially_local(
    rows: tuple[_HeaderlessReceiptRow, ...],
    semantics: _HeaderlessSemantics,
    peer_blocks: tuple[_GeometryBlock, ...],
    context: _HeaderlessContextEvidence,
) -> bool:
    primary_bbox, horizontal_budget, vertical_budget = _headerless_primary_geometry(rows)
    if context.weak:
        numeric_span = median(
            row.numeric_blocks[2].bbox.center_x
            - row.numeric_blocks[0].bbox.center_x
            for row in rows
        )
        vertical_budget = max(vertical_budget, numeric_span * 2.0)
    directly_bound_boxes = (
        *(block.bbox for block in semantics.header_blocks),
        semantics.guidance_block.bbox,
        *(block.bbox for block in peer_blocks),
    )
    if not all(
        _axis_gap(
            bbox.x_min,
            bbox.x_max,
            primary_bbox.x_min,
            primary_bbox.x_max,
        )
        <= horizontal_budget
        and _axis_gap(
            bbox.y_min,
            bbox.y_max,
            primary_bbox.y_min,
            primary_bbox.y_max,
        )
        <= vertical_budget
        for bbox in directly_bound_boxes
    ):
        return False
    if not context.weak:
        return all(
            _axis_gap(
                bbox.x_min,
                bbox.x_max,
                primary_bbox.x_min,
                primary_bbox.x_max,
            )
            <= horizontal_budget
            and _axis_gap(
                bbox.y_min,
                bbox.y_max,
                primary_bbox.y_min,
                primary_bbox.y_max,
            )
            <= vertical_budget
            for bbox in context.bboxes
        )
    evidence_items = tuple(
        evidence
        for row_evidence in context.row_evidence
        for evidence in row_evidence
    )
    return (
        len(context.row_evidence) == len(peer_blocks)
        and context.name_blocks == peer_blocks
        and context.bboxes
        == (
            *(block.bbox for block in peer_blocks),
            *(evidence.bbox for evidence in evidence_items),
        )
        and _weak_description_evidence(peer_blocks, evidence_items)
        == context.row_evidence
    )


def _headerless_primary_geometry(
    rows: tuple[_HeaderlessReceiptRow, ...],
) -> tuple[AxisAlignedBBox, float, float]:
    primary_boxes = tuple(
        block.bbox
        for row in rows
        for block in row.numeric_blocks
    )
    primary_bbox = _union(primary_boxes)
    typical_height = median(box.height for box in primary_boxes)
    numeric_spans = tuple(
        row.numeric_blocks[2].bbox.center_x
        - row.numeric_blocks[0].bbox.center_x
        for row in rows
    )
    row_gaps = tuple(
        rows[index + 1].center_y - rows[index].center_y
        for index in range(len(rows) - 1)
    )
    horizontal_budget = max(median(numeric_spans) * 2.5, typical_height * 24.0)
    vertical_budget = max(median(row_gaps) * 10.0, typical_height * 24.0)
    return primary_bbox, horizontal_budget, vertical_budget


def _axis_gap(
    first_min: float,
    first_max: float,
    second_min: float,
    second_max: float,
) -> float:
    if first_max < second_min:
        return second_min - first_max
    if second_max < first_min:
        return first_min - second_max
    return 0.0


def _headerless_row_spacing_is_stable(
    rows: tuple[_HeaderlessReceiptRow, ...],
) -> bool:
    typical_height = median(row.bbox.height for row in rows)
    gaps = tuple(
        rows[index + 1].center_y - rows[index].center_y
        for index in range(len(rows) - 1)
    )
    if any(gap <= typical_height * 0.45 or gap > typical_height * 6.0 for gap in gaps):
        return False
    typical_gap = median(gaps)
    return all(typical_gap * 0.60 <= gap <= typical_gap * 1.60 for gap in gaps)


def _invalid_headerless_row_is_near_cluster(
    rows: tuple[_HeaderlessReceiptRow, ...],
    invalid_row_centers: list[float],
) -> bool:
    gaps = tuple(
        rows[index + 1].center_y - rows[index].center_y
        for index in range(len(rows) - 1)
    )
    typical_gap = median(gaps)
    lower = rows[0].center_y - typical_gap * 1.25
    upper = rows[-1].center_y + typical_gap * 1.25
    return any(lower <= center <= upper for center in invalid_row_centers)


def _headerless_numeric_track_consistency(
    rows: tuple[_HeaderlessReceiptRow, ...],
    *,
    bbox_margin_factor: float = 0.15,
) -> float | None:
    blocks_by_row = tuple(
        (
            *row.numeric_blocks,
            *((row.derived_total_block,) if row.derived_total_block is not None else ()),
        )
        for row in rows
    )
    column_counts = {len(blocks) for blocks in blocks_by_row}
    if len(column_counts) != 1:
        return None
    column_count = next(iter(column_counts))
    centers = tuple(tuple(block.bbox.center_x for block in blocks) for blocks in blocks_by_row)
    gaps = tuple(
        (row[1] - row[0], row[2] - row[1])
        for row in centers
    )
    typical_height = median(
        block.bbox.height for blocks in blocks_by_row for block in blocks
    )
    if any(min(row_gaps) <= typical_height * 1.5 for row_gaps in gaps):
        return None
    spans = tuple(row[2] - row[0] for row in centers)
    typical_span = median(spans)
    if any(not typical_span * 0.70 <= span <= typical_span * 1.30 for span in spans):
        return None
    middle_ratios = tuple(row_gaps[0] / span for row_gaps, span in zip(gaps, spans, strict=True))
    if (
        any(not 0.30 <= ratio <= 0.70 for ratio in middle_ratios)
        or max(middle_ratios) - min(middle_ratios) > 0.12
    ):
        return None
    if column_count == 4:
        trailing_gaps = tuple(row[3] - row[2] for row in centers)
        typical_trailing_gap = median(trailing_gaps)
        if any(
            gap <= typical_height * 1.5
            or gap > span
            or not typical_trailing_gap * 0.70 <= gap <= typical_trailing_gap * 1.30
            for gap, span in zip(trailing_gaps, spans, strict=True)
        ):
            return None
    bbox_margin = typical_height * bbox_margin_factor
    for row, blocks in zip(rows, blocks_by_row, strict=True):
        if row.name_blocks:
            name_bbox = _union(block.bbox for block in row.name_blocks)
            if name_bbox.x_max + bbox_margin > blocks[0].bbox.x_min:
                return None
        if any(
            left.bbox.x_max + bbox_margin > right.bbox.x_min
            for left, right in zip(blocks, blocks[1:], strict=False)
        ):
            return None
    motion_tolerance = typical_height * 0.35
    fits: list[tuple[float, float]] = []
    scores: list[float] = []
    for column in range(column_count):
        deltas = tuple(
            centers[index + 1][column] - centers[index][column]
            for index in range(len(centers) - 1)
        )
        directions = {
            1 if delta > motion_tolerance else -1
            for delta in deltas
            if abs(delta) > motion_tolerance
        }
        if len(directions) > 1:
            return None
        points = tuple((row.center_y, centers[index][column]) for index, row in enumerate(rows))
        slopes = tuple(
            (right_x - left_x) / (right_y - left_y)
            for left_index, (left_y, left_x) in enumerate(points)
            for right_y, right_x in points[left_index + 1 :]
            if right_y != left_y
        )
        slope = median(slopes) if slopes else 0.0
        intercept = median(x - slope * y for y, x in points)
        residual_limit = max(typical_height, typical_span * 0.08)
        residuals = tuple(abs(x - (slope * y + intercept)) for y, x in points)
        if any(residual > residual_limit for residual in residuals):
            return None
        fits.append((slope, intercept))
        scores.extend(max(0.0, 1.0 - residual / residual_limit) for residual in residuals)
    for row, blocks in zip(rows, blocks_by_row, strict=True):
        expected = tuple(slope * row.center_y + intercept for slope, intercept in fits)
        boundaries = tuple(
            (expected[index] + expected[index + 1]) / 2.0
            for index in range(column_count - 1)
        )
        for column, block in enumerate(blocks):
            if column > 0 and block.bbox.x_min <= boundaries[column - 1] + bbox_margin:
                return None
            if column < column_count - 1 and block.bbox.x_max >= boundaries[column] - bbox_margin:
                return None
    return sum(scores) / len(scores) if scores else None


def _three_column_summary_rows(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[LayoutRow, ...]:
    """Recover an auxiliary receipt summary with name, dose, and times only."""

    headers: list[tuple[_GeometryBlock, _GeometryBlock, _GeometryBlock, float]] = []
    for upper, lower in zip(line_groups, line_groups[1:], strict=False):
        upper_headers = tuple(
            (block, match)
            for block in upper.blocks
            if (match := _header_match(block.source.text)) is not None
        )
        lower_headers = tuple(
            (block, match)
            for block in lower.blocks
            if (match := _header_match(block.source.text)) is not None
        )
        if (
            tuple(match.key for _, match in upper_headers) != ("name",)
            or tuple(match.key for _, match in lower_headers) != ("dose", "times")
            or any(match.fuzzy for _, match in (*upper_headers, *lower_headers))
        ):
            continue
        name_block = upper_headers[0][0]
        dose_block = lower_headers[0][0]
        times_block = lower_headers[1][0]
        centers = (
            name_block.bbox.center_x,
            dose_block.bbox.center_x,
            times_block.bbox.center_x,
        )
        if not centers[0] < centers[1] < centers[2]:
            continue
        vertical_gap = min(dose_block.bbox.y_min, times_block.bbox.y_min) - name_block.bbox.y_max
        typical_height = median(
            (name_block.bbox.height, dose_block.bbox.height, times_block.bbox.height)
        )
        if not _summary_header_gap_is_adjacent(vertical_gap, typical_height):
            continue
        headers.append((name_block, dose_block, times_block, lower.bbox.center_y))
    if len(headers) != 1:
        return ()

    name_header, dose_header, times_header, header_y = headers[0]
    name_dose_boundary = (name_header.bbox.center_x + dose_header.bbox.center_x) / 2.0
    numeric_left = name_dose_boundary
    numeric_right = times_header.bbox.center_x + (
        times_header.bbox.center_x - dose_header.bbox.center_x
    )
    rows: list[LayoutRow] = []
    last_row_y: float | None = None
    row_gaps: list[float] = []
    for line in line_groups:
        if line.bbox.center_y <= header_y:
            continue
        numeric_blocks = tuple(
            block
            for block in line.blocks
            if numeric_left <= block.bbox.center_x <= numeric_right
            and _is_structural_numeric(block.source.text)
        )
        if len(numeric_blocks) != 2:
            if rows and last_row_y is not None:
                typical_gap = median(row_gaps or (line.bbox.height * 3.0,))
                if line.bbox.center_y - last_row_y > typical_gap * 1.8:
                    break
            continue
        numeric_blocks = tuple(
            sorted(numeric_blocks, key=lambda block: (block.bbox.center_x, block.provider_order))
        )
        if numeric_blocks[0].bbox.center_x >= numeric_blocks[1].bbox.center_x:
            continue
        name_blocks = [
            block
            for block in line.blocks
            if block.bbox.center_x < numeric_blocks[0].bbox.center_x
            and _header_match(block.source.text) is None
            and not _is_structural_numeric(block.source.text)
        ]
        name_cell = _layout_cell(name_blocks)
        dose_cell = _layout_cell([numeric_blocks[0]])
        times_cell = _layout_cell([numeric_blocks[1]])
        if name_cell is None or dose_cell is None or times_cell is None:
            continue
        if last_row_y is not None:
            row_gaps.append(line.bbox.center_y - last_row_y)
        last_row_y = line.bbox.center_y
        cells: LayoutCells = (name_cell, dose_cell, times_cell, None)
        rows.append(
            LayoutRow(
                row_id=f"summary-row-{len(rows) + 1:04d}",
                cells=cells,
                bbox=_union((name_cell.bbox, dose_cell.bbox, times_cell.bbox)),
            )
        )
    return tuple(rows) if len(rows) >= 2 else ()


def _summary_header_gap_is_adjacent(
    vertical_gap: float,
    typical_height: float,
) -> bool:
    return -typical_height * 1.25 <= vertical_gap <= typical_height * 1.25


def _guidance_prefix_starts_near_name(
    header: _GuidanceHeader,
    name_cell: LayoutCell,
    instruction_blocks: tuple[_GeometryBlock, ...],
) -> bool:
    if not instruction_blocks:
        return False
    first_instruction_x = min(block.bbox.x_min for block in instruction_blocks)
    typical_height = median(
        (name_cell.bbox.height, *(block.bbox.height for block in instruction_blocks))
    )
    name_column_right = max(name_cell.bbox.x_max, header.name_band[1])
    horizontal_gap = first_instruction_x - name_column_right
    return horizontal_gap <= typical_height * _MAX_GUIDANCE_NAME_TO_INSTRUCTION_GAP


def _guidance_headers(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_GuidanceHeader, ...]:
    headers: list[_GuidanceHeader] = []
    for line in line_groups:
        name_headers = [
            (block, match)
            for block in line.blocks
            if (match := _header_match(block.source.text)) is not None
            and match.key == "name"
        ]
        for name_header, _ in name_headers:
            right_blocks = tuple(
                block
                for block in line.blocks
                if block.bbox.center_x > name_header.bbox.center_x
            )
            combined = "".join(
                _normalized_header_text(block.source.text) for block in right_blocks
            )
            marker_occurrences = {
                marker: sum(
                    _normalized_header_text(block.source.text).count(marker)
                    for block in right_blocks
                )
                for marker in ("복약안내", "투약량", "횟수", "일수", "주의사항")
            }
            guidance_blocks = tuple(
                block
                for block in right_blocks
                if "복약안내" in _normalized_header_text(block.source.text)
            )
            if (
                not guidance_blocks
                or "횟수" not in combined
                or "일수" not in combined
            ):
                continue
            dose_observed = marker_occurrences["투약량"] > 0
            if marker_occurrences["투약량"] > 1:
                continue
            starts = tuple(
                block
                for block in right_blocks
                if "복약안내" in _normalized_header_text(block.source.text)
                or "투약량" in _normalized_header_text(block.source.text)
            )
            if not starts:
                continue
            instruction_left = min(block.bbox.x_min for block in starts)
            caution_blocks = tuple(
                block
                for block in right_blocks
                if "주의사항" in _normalized_header_text(block.source.text)
            )
            if not dose_observed:
                times_blocks = tuple(
                    block
                    for block in right_blocks
                    if "횟수" in _normalized_header_text(block.source.text)
                )
                days_blocks = tuple(
                    block
                    for block in right_blocks
                    if "일수" in _normalized_header_text(block.source.text)
                )
                if (
                    len(name_headers) != 1
                    or len(guidance_blocks) != 1
                    or len(times_blocks) != 1
                    or len(days_blocks) != 1
                    or len(caution_blocks) != 1
                    or marker_occurrences["복약안내"] != 1
                    or marker_occurrences["횟수"] != 1
                    or marker_occurrences["일수"] != 1
                    or marker_occurrences["주의사항"] != 1
                ):
                    continue
            instruction_right = (
                min(block.bbox.x_min for block in caution_blocks)
                if caution_blocks
                else max(block.bbox.x_max for block in right_blocks)
            )
            if instruction_right <= instruction_left:
                continue
            name_center = name_header.bbox.center_x
            name_right = (name_center + instruction_left) / 2.0
            name_left = name_center - (name_right - name_center)
            headers.append(
                _GuidanceHeader(
                    name_band=(name_left, name_right),
                    instruction_band=(instruction_left, instruction_right),
                    bbox=_union((name_header.bbox, *(block.bbox for block in right_blocks))),
                )
            )
    headers.sort(key=lambda header: (header.bbox.center_y, header.bbox.x_min))
    return tuple(headers)


def _compact_schedule_headers(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_GuidanceHeader, ...]:
    """Recover a compact name/dose/times header for full inline schedules."""

    headers: list[_GuidanceHeader] = []
    for line in line_groups:
        observed = tuple(
            (block, match)
            for block in line.blocks
            if (match := _header_match(block.source.text)) is not None
        )
        if (
            tuple(match.key for _, match in observed) != ("name", "dose", "times")
            or observed[0][1].fuzzy
            or observed[2][1].fuzzy
            or sum(match.fuzzy for _, match in observed) > 1
        ):
            continue
        name_header, dose_header, times_header = (
            observed[0][0],
            observed[1][0],
            observed[2][0],
        )
        centers = (
            name_header.bbox.center_x,
            dose_header.bbox.center_x,
            times_header.bbox.center_x,
        )
        if not centers[0] < centers[1] < centers[2]:
            continue
        typical_height = median(
            (
                name_header.bbox.height,
                dose_header.bbox.height,
                times_header.bbox.height,
            )
        )
        numeric_spacing = centers[2] - centers[1]
        if numeric_spacing <= typical_height:
            continue
        name_right = (centers[0] + centers[1]) / 2.0
        name_left = centers[0] - (name_right - centers[0])
        instruction_left = times_header.bbox.x_max
        instruction_right = centers[2] + max(
            numeric_spacing * 4.0,
            typical_height * 8.0,
        )
        headers.append(
            _GuidanceHeader(
                name_band=(name_left, name_right),
                instruction_band=(instruction_left, instruction_right),
                bbox=_union(
                    (
                        name_header.bbox,
                        dose_header.bbox,
                        times_header.bbox,
                    )
                ),
            )
        )
    headers.sort(key=lambda header: (header.bbox.center_y, header.bbox.x_min))
    return tuple(headers)


def _guidance_instruction_cells(
    blocks: tuple[_GeometryBlock, ...],
) -> tuple[LayoutCell | None, LayoutCell, LayoutCell] | None:
    if not blocks:
        return None
    ordered = tuple(
        sorted(blocks, key=lambda block: (block.bbox.x_min, block.provider_order))
    )
    normalized = tuple(
        "".join(unicodedata.normalize("NFKC", block.source.text).split())
        for block in ordered
    )
    separatorless = _separatorless_guidance_cells(ordered, normalized)
    if separatorless is not None:
        return separatorless
    compact_slash = _compact_slash_guidance_cells(ordered, normalized)
    if compact_slash is not None:
        return compact_slash
    if (
        len(ordered) == 4
        and _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[0])
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[1])
        and normalized[2] == "/"
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[3])
    ):
        times_cell = _layout_cell([ordered[1]])
        days_cell = _layout_cell([ordered[3]])
        if times_cell is None or days_cell is None:
            return None
        return None, times_cell, days_cell

    slash_indices = [
        index for index, text in enumerate(normalized) if text == "/"
    ]
    if len(slash_indices) != 2 or normalized[0] != "1회":
        return None
    first_slash, second_slash = slash_indices
    daily_index = first_slash + 1
    times_index = daily_index + 1
    days_index = second_slash + 1
    if (
        first_slash < 2
        or second_slash != times_index + 1
        or days_index != len(ordered) - 1
        or not _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[daily_index])
        or not _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[times_index])
        or not _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[days_index])
    ):
        return None
    dose_blocks = list(ordered[1:first_slash])
    if not dose_blocks:
        return None
    dose_cell = _layout_cell(dose_blocks)
    times_cell = _layout_cell([ordered[times_index]])
    days_cell = _layout_cell([ordered[days_index]])
    if dose_cell is None or times_cell is None or days_cell is None:
        return None
    return dose_cell, times_cell, days_cell


def _compact_slash_guidance_cells(
    ordered: tuple[_GeometryBlock, ...],
    normalized: tuple[str, ...],
) -> tuple[LayoutCell | None, LayoutCell, LayoutCell] | None:
    if (
        len(ordered) >= 6
        and _GUIDANCE_DOSE_PATTERN.fullmatch(normalized[0])
        and normalized[1] == "/"
        and _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[2])
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[3])
        and normalized[4] == "/"
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[5])
        and _guidance_prefix_is_bounded(ordered, 6)
    ):
        dose_cell = _layout_cell([ordered[0]])
        times_cell = _layout_cell([ordered[3]])
        days_cell = _layout_cell([ordered[5]])
        if dose_cell is not None and times_cell is not None and days_cell is not None:
            return dose_cell, times_cell, days_cell
    if (
        len(ordered) >= 4
        and _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[0])
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[1])
        and normalized[2] == "/"
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[3])
        and _guidance_prefix_is_bounded(ordered, 4)
    ):
        times_cell = _layout_cell([ordered[1]])
        days_cell = _layout_cell([ordered[3]])
        if times_cell is not None and days_cell is not None:
            return None, times_cell, days_cell
    if (
        len(ordered) >= 3
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[0])
        and normalized[1] == "/"
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[2])
        and _guidance_prefix_is_bounded(ordered, 3)
    ):
        times_cell = _layout_cell([ordered[0]])
        days_cell = _layout_cell([ordered[2]])
        if times_cell is not None and days_cell is not None:
            return None, times_cell, days_cell
    return None


def _separatorless_guidance_cells(
    ordered: tuple[_GeometryBlock, ...],
    normalized: tuple[str, ...],
) -> tuple[LayoutCell | None, LayoutCell, LayoutCell] | None:
    if (
        len(ordered) >= 4
        and _GUIDANCE_DOSE_PATTERN.fullmatch(normalized[0])
        and _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[1])
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[2])
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[3])
        and _guidance_prefix_is_bounded(ordered, 4)
    ):
        dose_cell = _layout_cell([ordered[0]])
        times_cell = _layout_cell([ordered[2]])
        days_cell = _layout_cell([ordered[3]])
        if dose_cell is not None and times_cell is not None and days_cell is not None:
            return dose_cell, times_cell, days_cell
    if (
        len(ordered) >= 3
        and _GUIDANCE_DAILY_MARKER_PATTERN.fullmatch(normalized[0])
        and _GUIDANCE_TIMES_PATTERN.fullmatch(normalized[1])
        and _GUIDANCE_DAYS_PATTERN.fullmatch(normalized[2])
        and _guidance_prefix_is_bounded(ordered, 3)
    ):
        times_cell = _layout_cell([ordered[1]])
        days_cell = _layout_cell([ordered[2]])
        if times_cell is not None and days_cell is not None:
            return None, times_cell, days_cell
    return None


def _guidance_prefix_is_bounded(
    ordered: tuple[_GeometryBlock, ...], prefix_length: int
) -> bool:
    if len(ordered) == prefix_length:
        return True
    prefix = ordered[:prefix_length]
    horizontal_gap = ordered[prefix_length].bbox.x_min - prefix[-1].bbox.x_max
    typical_height = median(block.bbox.height for block in prefix)
    return horizontal_gap >= typical_height * 2.0


def _inline_composite_candidates(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[TableCandidate, ...]:
    headers = _inline_guidance_headers(line_groups)
    if len(headers) != 1:
        return ()
    header = headers[0]
    inline_rows = _inline_guidance_evidence(line_groups, header)
    if len(inline_rows) < 2:
        return ()
    receipt_matches = _matching_receipt_days(line_groups, header, inline_rows)
    if receipt_matches is None:
        return ()

    rows: list[LayoutRow] = []
    for inline, receipt_match in zip(inline_rows, receipt_matches, strict=True):
        name_cell = _layout_cell(list(inline.name_blocks))
        dose_cell = _layout_cell([inline.dose_block])
        times_cell = _layout_cell([inline.times_block])
        if name_cell is None or dose_cell is None or times_cell is None:
            return ()
        name_cell = receipt_match.preferred_name_cell or name_cell
        day_cell = receipt_match.day_cell
        cells: LayoutCells = (name_cell, dose_cell, times_cell, day_cell)
        rows.append(
            LayoutRow(
                row_id=f"row-{len(rows) + 1:04d}",
                cells=cells,
                bbox=_union(
                    (
                        name_cell.bbox,
                        dose_cell.bbox,
                        times_cell.bbox,
                        day_cell.bbox,
                    )
                ),
            )
        )

    first = rows[0]
    inferred_headers = tuple(
        HeaderColumn(
            key=key,
            source_text="",
            block_ids=(),
            bbox=cell.bbox,
            band_min=cell.bbox.x_min,
            band_max=cell.bbox.x_max,
        )
        for key, cell in zip(_HEADER_ORDER[1:], first.cells[1:], strict=True)
        if cell is not None
    )
    if len(inferred_headers) != 3:
        return ()
    name_column = HeaderColumn(
        key="name",
        source_text=header.name_block.source.text,
        block_ids=(header.name_block.source.block_id,),
        bbox=header.name_block.bbox,
        band_min=header.name_band[0],
        band_max=header.name_band[1],
    )
    observed_cells = [cell for row in rows for cell in row.cells if cell is not None]
    confidence_count = sum(cell.valid_confidence_count for cell in observed_cells)
    confidence_sum = sum(
        (cell.confidence or 0.0) * cell.valid_confidence_count for cell in observed_cells
    )
    candidate_bbox = _union(
        (
            header.name_block.bbox,
            header.guidance_block.bbox,
            *(row.bbox for row in rows),
        )
    )
    return (
        TableCandidate(
            candidate_id="table-inline-0001",
            bbox=candidate_bbox,
            header_columns=(
                name_column,
                inferred_headers[0],
                inferred_headers[1],
                inferred_headers[2],
            ),
            rows=tuple(rows),
            ambiguous_column_evidence=(),
            column_consistency=1.0,
            confidence_coverage=1.0 if confidence_count else 0.0,
            mean_confidence=(
                confidence_sum / confidence_count if confidence_count else None
            ),
        ),
    )


def _inline_guidance_headers(
    line_groups: tuple[_LineGroup, ...],
) -> tuple[_InlineGuidanceHeader, ...]:
    headers: list[_InlineGuidanceHeader] = []
    for line in line_groups:
        name_blocks = tuple(
            block
            for block in line.blocks
            if _normalized_header_text(block.source.text) == "약품명"
        )
        for name_block in name_blocks:
            guidance_blocks = tuple(
                block
                for block in line.blocks
                if block.bbox.x_min > name_block.bbox.center_x
                and "복약안내" in _normalized_header_text(block.source.text)
            )
            if len(guidance_blocks) != 1:
                continue
            guidance_block = guidance_blocks[0]
            horizontal_gap = guidance_block.bbox.x_min - name_block.bbox.center_x
            if horizontal_gap <= median((name_block.bbox.height, guidance_block.bbox.height)):
                continue
            name_left = name_block.bbox.center_x - horizontal_gap * 1.25
            headers.append(
                _InlineGuidanceHeader(
                    name_block=name_block,
                    guidance_block=guidance_block,
                    name_band=(
                        name_block.bbox.center_x - horizontal_gap * 0.65,
                        (name_block.bbox.center_x + guidance_block.bbox.x_min) / 2.0,
                    ),
                    schedule_band=(name_left, guidance_block.bbox.x_min),
                )
            )
    headers.sort(
        key=lambda item: (
            item.name_block.bbox.center_y,
            item.name_block.bbox.x_min,
        )
    )
    return tuple(headers)


def _inline_guidance_evidence(
    line_groups: tuple[_LineGroup, ...],
    header: _InlineGuidanceHeader,
) -> tuple[_InlineGuidanceRow, ...]:
    blocks = tuple(block for line in line_groups for block in line.blocks)
    anchors = tuple(
        block
        for block in blocks
        if _compact_text(block.source.text) == "1일"
        and header.schedule_band[0] <= block.bbox.center_x <= header.schedule_band[1]
        and block.bbox.center_y > header.name_block.bbox.center_y
    )
    rows: list[_InlineGuidanceRow] = []
    for anchor in sorted(
        anchors,
        key=lambda block: (block.bbox.center_y, block.bbox.x_min, block.provider_order),
    ):
        typical_height = median(
            block.bbox.height
            for block in blocks
            if abs(block.bbox.center_y - anchor.bbox.center_y)
            <= max(block.bbox.height, anchor.bbox.height)
        )
        schedule_blocks = tuple(
            sorted(
                (
                    block
                    for block in blocks
                    if block.bbox.x_min >= anchor.bbox.x_min
                    and block.bbox.center_x <= header.schedule_band[1]
                    and abs(block.bbox.center_y - anchor.bbox.center_y)
                    <= median((block.bbox.height, anchor.bbox.height)) * 0.80
                ),
                key=lambda block: (block.bbox.x_min, block.provider_order),
            )
        )
        parsed = _inline_schedule_blocks(schedule_blocks, anchor)
        if parsed is None:
            continue
        times_block, dose_block = parsed
        name_blocks = _inline_name_blocks(blocks, header, anchor, typical_height)
        if not name_blocks:
            continue
        rows.append(
            _InlineGuidanceRow(
                name_blocks=name_blocks,
                dose_block=dose_block,
                times_block=times_block,
                anchor_y=anchor.bbox.center_y,
            )
        )
    return tuple(rows)


def _inline_schedule_blocks(
    blocks: tuple[_GeometryBlock, ...],
    anchor: _GeometryBlock,
) -> tuple[_GeometryBlock, _GeometryBlock] | None:
    structural = tuple(
        block
        for block in blocks
        if _compact_text(block.source.text) not in {",", "，"}
    )
    try:
        start = structural.index(anchor)
    except ValueError:
        return None
    sequence = structural[start : start + 4]
    if len(sequence) != 4:
        return None
    normalized = tuple(_compact_text(block.source.text) for block in sequence)
    if (
        normalized[0] != "1일"
        or _INLINE_TIMES_PATTERN.fullmatch(normalized[1]) is None
        or normalized[2] != "1회"
        or _GUIDANCE_DOSE_PATTERN.fullmatch(normalized[3]) is None
    ):
        return None
    return sequence[1], sequence[3]


def _inline_name_blocks(
    blocks: tuple[_GeometryBlock, ...],
    header: _InlineGuidanceHeader,
    anchor: _GeometryBlock,
    typical_height: float,
) -> tuple[_GeometryBlock, ...]:
    candidates = tuple(
        block
        for block in blocks
        if header.name_band[0] <= block.bbox.center_x <= header.name_band[1]
        and block.bbox.center_y < anchor.bbox.center_y
        and anchor.bbox.center_y - block.bbox.center_y
        <= max(typical_height, block.bbox.height) * 2.5
        and _contains_hangul(block.source.text)
        and not _is_inline_structural(block.source.text)
        and _normalized_header_text(block.source.text)
        not in {"약품명", "복약안내", "주의사항", "약품사진"}
    )
    if not candidates:
        return ()
    nearest_y = max(block.bbox.center_y for block in candidates)
    same_line = tuple(
        block
        for block in candidates
        if abs(block.bbox.center_y - nearest_y)
        <= median((block.bbox.height, anchor.bbox.height)) * 0.60
    )
    return tuple(
        sorted(same_line, key=lambda block: (block.bbox.x_min, block.provider_order))
    )


def _matching_receipt_days(
    line_groups: tuple[_LineGroup, ...],
    header: _InlineGuidanceHeader,
    inline_rows: tuple[_InlineGuidanceRow, ...],
) -> tuple[_InlineReceiptMatch, ...] | None:
    blocks = tuple(block for line in line_groups for block in line.blocks)
    typical_height = median(block.bbox.height for block in blocks)
    numeric_left = max(0.0, header.name_band[0] * 0.65)
    numeric_right = min(
        block.bbox.x_min for row in inline_rows for block in row.name_blocks
    )
    lower_y = inline_rows[-1].anchor_y - typical_height
    dose_blocks = tuple(
        sorted(
            (
                block
                for block in blocks
                if numeric_left <= block.bbox.center_x < numeric_right
                and block.bbox.center_y >= lower_y
                and _receipt_dose_text(block.source.text) is not None
            ),
            key=lambda block: (block.bbox.center_y, block.bbox.center_x),
        )
    )
    if len(dose_blocks) != len(inline_rows):
        return None

    receipt_names: list[str] = []
    main_names: list[str] = []
    days: list[LayoutCell] = []
    main_name_cells: list[LayoutCell] = []
    receipt_name_cells: list[LayoutCell] = []
    exact_name_matches = 0
    incompatible_name_matches = 0
    for inline, dose_block in zip(inline_rows, dose_blocks, strict=True):
        main_dose = _inline_dose_text(inline.dose_block.source.text)
        receipt_dose = _receipt_dose_text(dose_block.source.text)
        if (
            main_dose is None
            or receipt_dose is None
            or _decimal_key(main_dose) != _decimal_key(receipt_dose)
        ):
            return None
        times_match = _INLINE_TIMES_PATTERN.fullmatch(
            _compact_text(inline.times_block.source.text)
        )
        if times_match is None:
            return None
        expected_times = int(times_match.group(1))
        numeric_tokens = _receipt_schedule_tokens(blocks, dose_block)
        day_evidence = _unique_day_evidence(numeric_tokens, expected_times)
        if day_evidence is None:
            return None
        day_text, day_block = day_evidence
        day_cell = _layout_cell([day_block])
        if day_cell is None:
            return None
        days.append(replace(day_cell, parsed_text=day_text))

        receipt_name_blocks = _receipt_name_blocks(blocks, dose_block)
        main_name_cell = _layout_cell(list(inline.name_blocks))
        receipt_name_cell = _layout_cell(list(receipt_name_blocks))
        if main_name_cell is None or receipt_name_cell is None:
            return None
        main_key = _inline_name_key(main_name_cell.text)
        receipt_key = _inline_name_key(receipt_name_cell.text)
        if not _compatible_inline_name(main_key, receipt_key):
            incompatible_name_matches += 1
        exact_name_matches += main_key == receipt_key
        main_names.append(main_key)
        receipt_names.append(receipt_key)
        main_name_cells.append(main_name_cell)
        receipt_name_cells.append(receipt_name_cell)

    strict_alignment = incompatible_name_matches == 0 and exact_name_matches >= 1
    relaxed_alignment = (
        len(inline_rows) >= 3
        and incompatible_name_matches <= 1
        and exact_name_matches >= max(2, len(inline_rows) - 2)
    )
    if (
        not (strict_alignment or relaxed_alignment)
        or len(set(main_names)) != len(main_names)
        or len(set(receipt_names)) != len(receipt_names)
    ):
        return None
    compatible_counts = tuple(
        sum(_compatible_inline_name(main, receipt) for main in main_names)
        for receipt in receipt_names
    )
    unmatched_limit = 1 if relaxed_alignment else 0
    if any(count > 1 for count in compatible_counts) or sum(
        count == 0 for count in compatible_counts
    ) > unmatched_limit:
        return None
    matches: list[_InlineReceiptMatch] = []
    for day_cell, main_name_cell, receipt_name_cell, main_key, receipt_key in zip(
        days,
        main_name_cells,
        receipt_name_cells,
        main_names,
        receipt_names,
        strict=True,
    ):
        preferred_name_cell = None
        if exact_name_matches >= 2 and _is_unique_inline_truncated_name_extension(
            main_name_cell,
            receipt_name_cell,
            receipt_name_cells,
        ):
            preferred_name_cell = receipt_name_cell
        elif (
            relaxed_alignment
            and not _compatible_inline_name(main_key, receipt_key)
            and _single_substitution_name(main_key, receipt_key)
            and _confidence_exceeds(
                receipt_name_cell.confidence,
                main_name_cell.confidence,
                _INLINE_NAME_CONFIDENCE_MARGIN,
            )
        ):
            preferred_name_cell = receipt_name_cell
        matches.append(_InlineReceiptMatch(day_cell, preferred_name_cell))
    return tuple(matches)


def _receipt_schedule_tokens(
    blocks: tuple[_GeometryBlock, ...],
    dose_block: _GeometryBlock,
) -> tuple[tuple[str, _GeometryBlock], ...]:
    dose_numbers = _INLINE_RECEIPT_NUMBER_PATTERN.findall(
        _compact_text(dose_block.source.text)
    )
    if len(dose_numbers) >= 3:
        return tuple((number, dose_block) for number in dose_numbers[1:])
    nearby = tuple(
        sorted(
            (
                block
                for block in blocks
                if block.bbox.x_min >= dose_block.bbox.x_min
                and abs(block.bbox.center_y - dose_block.bbox.center_y)
                <= median((block.bbox.height, dose_block.bbox.height)) * 0.90
            ),
            key=lambda block: (block.bbox.x_min, block.provider_order),
        )
    )
    tokens: list[tuple[str, _GeometryBlock]] = []
    for block in nearby:
        numbers = _INLINE_RECEIPT_NUMBER_PATTERN.findall(_compact_text(block.source.text))
        if block is dose_block and numbers:
            numbers = numbers[1:]
        tokens.extend((number, block) for number in numbers)
    return tuple(tokens)


def _unique_day_evidence(
    tokens: tuple[tuple[str, _GeometryBlock], ...],
    expected_times: int,
) -> tuple[str, _GeometryBlock] | None:
    candidates: set[tuple[str, _GeometryBlock]] = set()
    for index, (times_text, _) in enumerate(tokens):
        times_value = _positive_integer(times_text)
        if times_value != expected_times:
            continue
        for day_text, day_block in tokens[index + 1 :]:
            if _positive_integer(day_text) is not None:
                candidates.add((day_text, day_block))
    for text, block in tokens:
        if not text.isdigit():
            continue
        for split in range(1, len(text)):
            if _positive_integer(text[:split]) == expected_times and _positive_integer(
                text[split:]
            ) is not None:
                candidates.add((text[split:], block))
    normalized = {
        (str(_positive_integer(day_text)), block)
        for day_text, block in candidates
        if _positive_integer(day_text) is not None
    }
    return next(iter(normalized)) if len(normalized) == 1 else None


def _receipt_name_blocks(
    blocks: tuple[_GeometryBlock, ...],
    dose_block: _GeometryBlock,
) -> tuple[_GeometryBlock, ...]:
    candidates = tuple(
        block
        for block in blocks
        if block.bbox.x_max < dose_block.bbox.x_min
        and abs(block.bbox.center_y - dose_block.bbox.center_y)
        <= median((block.bbox.height, dose_block.bbox.height)) * 1.10
        and _contains_hangul(block.source.text)
        and _header_match(block.source.text) is None
    )
    if not candidates:
        return ()
    closest_y = min(
        (block.bbox.center_y for block in candidates),
        key=lambda value: abs(value - dose_block.bbox.center_y),
    )
    return tuple(
        sorted(
            (
                block
                for block in candidates
                if abs(block.bbox.center_y - closest_y)
                <= median((block.bbox.height, dose_block.bbox.height)) * 0.60
            ),
            key=lambda block: (block.bbox.x_min, block.provider_order),
        )
    )


def _receipt_dose_text(text: str) -> str | None:
    numbers = _INLINE_RECEIPT_NUMBER_PATTERN.findall(_compact_text(text))
    return numbers[0] if numbers and "." in numbers[0] else None


def _inline_dose_text(text: str) -> str | None:
    match = _GUIDANCE_DOSE_PATTERN.fullmatch(_compact_text(text))
    if match is None:
        return None
    number = _INLINE_RECEIPT_NUMBER_PATTERN.search(match.group(0))
    return number.group(0) if number is not None else None


def _decimal_key(text: str) -> tuple[str, str]:
    integer, _, fraction = text.partition(".")
    return integer.lstrip("0") or "0", fraction.rstrip("0")


def _positive_integer(text: str) -> int | None:
    if not text.isdigit() or int(text) <= 0:
        return None
    return int(text)


def _inline_name_key(text: str) -> str:
    normalized = _compact_text(text).replace("_", "")
    return normalized.split("(", 1)[0].rstrip(".·…⋯")


def _is_unique_inline_truncated_name_extension(
    main_name_cell: LayoutCell,
    receipt_name_cell: LayoutCell,
    receipt_name_cells: list[LayoutCell],
) -> bool:
    prefix = _inline_explicit_truncation_prefix(main_name_cell.text)
    receipt_name = _inline_name_key(receipt_name_cell.text)
    if (
        not prefix
        or not receipt_name.startswith(prefix)
        or len(receipt_name) <= len(prefix)
    ):
        return False
    return sum(
        _inline_name_key(candidate.text).startswith(prefix)
        for candidate in receipt_name_cells
    ) == 1


def _inline_explicit_truncation_prefix(text: str) -> str | None:
    normalized = _compact_text(text).replace("_", "")
    truncation = re.search(r"(?:\.{3,}|·{3,}|…|⋯)", normalized)
    if truncation is not None:
        prefix = normalized[: truncation.start()]
    elif normalized.endswith("-") and len(normalized) > 1:
        prefix = normalized[:-1]
    else:
        return None
    normalized_prefix = _inline_name_key(prefix)
    return (
        normalized_prefix
        if len(normalized_prefix) >= _MIN_TRUNCATED_NAME_PREFIX_LENGTH
        else None
    )


def _compatible_inline_name(first: str, second: str) -> bool:
    if not first or not second:
        return False
    if first == second:
        return True
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) < 4:
        return False
    if longer.startswith(shorter):
        return True
    common_prefix = 0
    for left, right in zip(first, second, strict=False):
        if left != right:
            break
        common_prefix += 1
    return common_prefix >= max(4, math.ceil(len(shorter) * 0.80))


def _single_substitution_name(first: str, second: str) -> bool:
    return (
        len(first) == len(second)
        and len(first) >= 4
        and sum(left != right for left, right in zip(first, second, strict=True)) == 1
    )


def _confidence_exceeds(
    candidate: float | None,
    baseline: float | None,
    margin: float,
) -> bool:
    return (
        candidate is not None
        and baseline is not None
        and math.isfinite(candidate)
        and math.isfinite(baseline)
        and candidate >= baseline + margin
    )


def _compact_text(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def _contains_hangul(text: str) -> bool:
    return any("가" <= character <= "힣" for character in text)


def _is_inline_structural(text: str) -> bool:
    normalized = _compact_text(text)
    return (
        normalized == "1일"
        or _INLINE_TIMES_PATTERN.fullmatch(normalized) is not None
        or _GUIDANCE_DOSE_PATTERN.fullmatch(normalized) is not None
    )


def _table_candidates(
    seeds: tuple[_HeaderSeed, ...], line_groups: tuple[_LineGroup, ...]
) -> tuple[tuple[TableCandidate, ...], tuple[LayoutIssue, ...]]:
    candidates: list[TableCandidate] = []
    issues: list[LayoutIssue] = []
    all_header_ids = {
        block_id for seed in seeds for block in seed.blocks for block_id in block.source_block_ids
    }
    for candidate_index, seed in enumerate(seeds, start=1):
        lower_header = _next_overlapping_header_top(seed, seeds)
        fragments, ambiguous_blocks, fragment_issues = _body_fragments(
            seed,
            line_groups,
            all_header_ids,
            lower_header,
        )
        body_bottom = _candidate_body_bottom(seed, fragments, ambiguous_blocks)
        candidate_body = _candidate_body_blocks(
            seed,
            line_groups,
            all_header_ids,
            lower_header,
            body_bottom,
        )
        rows = _anchored_layout_rows(seed, candidate_body)
        used_block_ids = {
            block_id for row in rows for block_id in row.source_block_ids
        }
        ambiguous_blocks = tuple(
            block
            for block in ambiguous_blocks
            if block.source.block_id not in used_block_ids
            and _is_structural_numeric(block.source.text)
        )
        fragment_issues = tuple(
            issue
            for issue in fragment_issues
            if not used_block_ids.intersection(issue.block_ids)
            and any(
                block.source.block_id in issue.block_ids
                and _is_structural_numeric(block.source.text)
                for block in candidate_body
            )
        )
        issues.extend(fragment_issues)
        ambiguous_evidence = _ambiguous_column_evidence(
            ambiguous_blocks,
            rows,
            seed.bands,
        )
        header_columns = tuple(
            HeaderColumn(
                key=key,
                source_text=block.source.text,
                block_ids=block.source_block_ids,
                bbox=block.bbox,
                band_min=band[0],
                band_max=band[1],
            )
            for key, block, band in zip(
                _HEADER_ORDER, seed.blocks, seed.bands, strict=True
            )
        )
        body_boxes = [
            *(row.bbox for row in rows),
            *(evidence.bbox for evidence in ambiguous_evidence),
        ]
        candidate_bbox = _union((seed.bbox, *body_boxes))
        body_by_id = {block.source.block_id: block for block in candidate_body}
        assigned_blocks = [body_by_id[block_id] for block_id in used_block_ids]
        consistency = _column_consistency(assigned_blocks, seed.bands)
        observed_blocks = [*seed.blocks, *assigned_blocks, *ambiguous_blocks]
        valid_confidences = [
            block.source.confidence
            for block in observed_blocks
            if block.source.confidence is not None
            and math.isfinite(block.source.confidence)
        ]
        confidence_total = len(observed_blocks)
        candidates.append(
            TableCandidate(
                candidate_id=f"table-{candidate_index:04d}",
                bbox=candidate_bbox,
                header_columns=(
                    header_columns[0],
                    header_columns[1],
                    header_columns[2],
                    header_columns[3],
                ),
                rows=rows,
                ambiguous_column_evidence=ambiguous_evidence,
                column_consistency=consistency,
                confidence_coverage=(
                    len(valid_confidences) / confidence_total if confidence_total else 0.0
                ),
                mean_confidence=(
                    sum(valid_confidences) / len(valid_confidences)
                    if valid_confidences
                    else None
                ),
            )
        )
    return tuple(candidates), tuple(issues)


def _candidate_body_blocks(
    seed: _HeaderSeed,
    line_groups: tuple[_LineGroup, ...],
    all_header_ids: set[str],
    lower_header: float | None,
    body_bottom: float,
) -> tuple[_GeometryBlock, ...]:
    margin = seed.bbox.width * 0.08
    left = seed.bbox.x_min - margin
    right = seed.bbox.x_max + margin
    blocks = {
        block.source.block_id: block
        for line in line_groups
        for block in line.blocks
        if block.source.block_id not in all_header_ids
        and block.bbox.center_y > seed.bbox.center_y
        and block.bbox.y_min <= body_bottom
        and (
            seed.numeric_right_bound is None
            or block.bbox.center_x < seed.numeric_right_bound
        )
        and (lower_header is None or block.bbox.y_min < lower_header)
        and block.bbox.x_max > left
        and block.bbox.x_min < right
    }
    return tuple(
        sorted(
            blocks.values(),
            key=lambda block: (
                block.bbox.center_y,
                block.bbox.x_min,
                block.provider_order,
            ),
        )
    )


def _candidate_body_bottom(
    seed: _HeaderSeed,
    fragments: tuple[_BodyFragment, ...],
    ambiguous_blocks: tuple[_GeometryBlock, ...],
) -> float:
    observed_boxes = (
        *(fragment.bbox for fragment in fragments),
        *(block.bbox for block in ambiguous_blocks),
    )
    if not observed_boxes:
        return seed.bbox.y_max
    header_height = median(block.bbox.height for block in seed.blocks)
    return max(box.y_max for box in observed_boxes) + header_height * 0.75


def _anchored_layout_rows(
    seed: _HeaderSeed,
    body_blocks: tuple[_GeometryBlock, ...],
) -> tuple[LayoutRow, ...]:
    numeric_left = seed.bands[0][1]
    numeric_blocks = [
        block
        for block in body_blocks
        if block.bbox.center_x >= numeric_left
        and _is_structural_numeric(block.source.text)
    ]
    if not numeric_blocks:
        return ()
    typical_height = median(block.bbox.height for block in numeric_blocks)
    normal_numeric_blocks = tuple(
        block
        for block in numeric_blocks
        if block.bbox.height <= typical_height * 1.8
    )
    numeric_seeds = _numeric_row_seeds(seed, normal_numeric_blocks, typical_height)
    numeric_seeds = tuple(seed for seed in numeric_seeds if len(seed.blocks) in {1, 2, 3})
    if not numeric_seeds:
        return ()

    full_seeds = tuple(seed for seed in numeric_seeds if len(seed.blocks) == 3)
    tracks = _numeric_tracks(seed, full_seeds)
    mapped_numeric = tuple(
        _map_numeric_seed(row_seed, tracks) for row_seed in numeric_seeds
    )
    name_groups = _name_line_groups(seed, body_blocks)
    row_centers = tuple(row_seed.center_y for row_seed in numeric_seeds)
    typical_gap = median(
        tuple(
            row_centers[index + 1] - row_centers[index]
            for index in range(len(row_centers) - 1)
        )
        or (typical_height * 3.0,)
    )
    name_row_offset = _name_column_row_offset(
        name_groups,
        row_centers,
        typical_height,
        typical_gap,
    )
    rows: list[LayoutRow] = []
    for index, (row_seed, numeric_cells) in enumerate(
        zip(numeric_seeds, mapped_numeric, strict=True),
        start=1,
    ):
        if numeric_cells is None:
            continue
        lower = (
            (row_centers[index - 2] + row_seed.center_y) / 2.0
            if index > 1
            else row_seed.center_y - typical_gap / 2.0
        )
        upper = (
            (row_seed.center_y + row_centers[index]) / 2.0
            if index < len(row_centers)
            else row_seed.center_y + typical_gap / 2.0
        )
        name_blocks = _name_blocks_for_row(
            name_groups,
            row_seed.center_y + name_row_offset,
            lower + name_row_offset,
            upper + name_row_offset,
            typical_height,
        )
        name_cell = _layout_cell(list(name_blocks))
        dose_blocks = (
            (numeric_cells[0],)
            if numeric_cells[0] is not None
            else _nonnumeric_dose_blocks_for_row(
                seed,
                body_blocks,
                tracks,
                row_seed.center_y,
                lower,
                upper,
                typical_height,
            )
        )
        if len(row_seed.blocks) == 1 and (
            name_cell is None or numeric_cells[0] is not None or not dose_blocks
        ):
            continue
        cells: LayoutCells = (
            name_cell,
            _layout_cell(list(dose_blocks)),
            _layout_cell([numeric_cells[1]]) if numeric_cells[1] is not None else None,
            _layout_cell([numeric_cells[2]]) if numeric_cells[2] is not None else None,
        )
        present_cells = tuple(cell for cell in cells if cell is not None)
        rows.append(
            LayoutRow(
                row_id=f"row-{len(rows) + 1:04d}",
                cells=cells,
                bbox=_union(cell.bbox for cell in present_cells),
            )
        )
    return _rows_in_authoritative_numeric_lane(seed, tuple(rows), typical_height)


def _name_column_row_offset(
    groups: tuple[tuple[_GeometryBlock, ...], ...],
    row_centers: tuple[float, ...],
    typical_height: float,
    typical_gap: float,
) -> float:
    name_groups = tuple(group for group in groups if _looks_like_medication_name_blocks(group))
    if len(row_centers) < 2 or len(name_groups) != len(row_centers):
        return 0.0
    offsets = tuple(
        median(block.bbox.center_y for block in group) - row_center
        for group, row_center in zip(name_groups, row_centers, strict=True)
    )
    offset = median(offsets)
    tolerance = max(
        typical_height,
        median(block.bbox.height for group in name_groups for block in group),
    ) * 1.25
    if (
        max(abs(value - offset) for value in offsets) > tolerance
        or abs(offset) > typical_gap * 1.5
    ):
        return 0.0
    return offset


def _rows_in_authoritative_numeric_lane(
    seed: _HeaderSeed,
    rows: tuple[LayoutRow, ...],
    typical_height: float,
) -> tuple[LayoutRow, ...]:
    if len(rows) < 4:
        return rows
    offsets = tuple(
        median(
            cell.bbox.center_x - header.bbox.center_x
            for cell, header in zip(row.cells[1:], seed.blocks[1:], strict=True)
            if cell is not None
        )
        for row in rows
    )
    tolerance = typical_height * _MAX_NUMERIC_LANE_OFFSET_GAP
    clusters: list[list[int]] = []
    previous_offset: float | None = None
    for offset, index in sorted(
        (offset, index) for index, offset in enumerate(offsets)
    ):
        if previous_offset is None or offset - previous_offset > tolerance:
            clusters.append([])
        clusters[-1].append(index)
        previous_offset = offset
    multirow_clusters = tuple(cluster for cluster in clusters if len(cluster) >= 2)
    if len(multirow_clusters) < 2:
        return rows
    authoritative = min(
        multirow_clusters,
        key=lambda cluster: (
            abs(median(offsets[index] for index in cluster)),
            -len(cluster),
            min(cluster),
        ),
    )
    return tuple(
        replace(rows[index], row_id=f"row-{output_index:04d}")
        for output_index, index in enumerate(
            sorted(authoritative),
            start=1,
        )
    )


def _nonnumeric_dose_blocks_for_row(
    seed: _HeaderSeed,
    body_blocks: tuple[_GeometryBlock, ...],
    tracks: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    anchor_y: float,
    lower: float,
    upper: float,
    typical_height: float,
) -> tuple[_GeometryBlock, ...]:
    expected = tuple(slope * anchor_y + intercept for slope, intercept in tracks)
    track_gap = min(expected[1] - expected[0], expected[2] - expected[1])
    if track_gap <= 0.0:
        return ()
    dose_left = seed.bands[1][0]
    candidates = [
        block
        for block in body_blocks
        if not _is_structural_numeric(block.source.text)
        and _header_match(block.source.text) is None
        and dose_left <= block.bbox.x_min
        and abs(block.bbox.center_x - expected[0]) <= track_gap * 0.60
        and lower <= block.bbox.center_y < upper
        and abs(block.bbox.center_y - anchor_y)
        <= max(typical_height, block.bbox.height) * 0.80
    ]
    if not candidates:
        return ()
    closest = min(
        candidates,
        key=lambda block: (
            abs(block.bbox.center_y - anchor_y),
            abs(block.bbox.center_x - expected[0]),
            block.provider_order,
        ),
    )
    same_line = [
        block
        for block in candidates
        if abs(block.bbox.center_y - closest.bbox.center_y)
        <= median((block.bbox.height, closest.bbox.height)) * 0.60
    ]
    return tuple(
        sorted(
            same_line,
            key=lambda block: (block.bbox.x_min, block.provider_order),
        )
    )


def _numeric_row_seeds(
    header: _HeaderSeed,
    blocks: tuple[_GeometryBlock, ...],
    typical_height: float,
) -> tuple[_NumericRowSeed, ...]:
    groups: list[list[_GeometryBlock]] = []
    max_span = typical_height * 0.75
    for block in sorted(
        blocks,
        key=lambda item: (item.bbox.center_y, item.bbox.center_x, item.provider_order),
    ):
        compatible = [
            group
            for group in groups
            if max(
                *(member.bbox.center_y for member in group),
                block.bbox.center_y,
            )
            - min(
                *(member.bbox.center_y for member in group),
                block.bbox.center_y,
            )
            <= max_span
        ]
        if compatible:
            min(
                compatible,
                key=lambda group: abs(
                    block.bbox.center_y
                    - median(member.bbox.center_y for member in group)
                ),
            ).append(block)
        else:
            groups.append([block])
    seeds = [
        _NumericRowSeed(
            blocks=_authoritative_numeric_seed_blocks(header, group),
            center_y=median(block.bbox.center_y for block in group),
        )
        for group in groups
    ]
    seeds.sort(key=lambda item: item.center_y)
    return tuple(seeds)


def _authoritative_numeric_seed_blocks(
    header: _HeaderSeed,
    group: list[_GeometryBlock],
) -> tuple[_GeometryBlock, ...]:
    ordered = tuple(
        sorted(
            group,
            key=lambda block: (block.bbox.center_x, block.provider_order),
        )
    )
    if len(ordered) <= 3:
        return ordered
    by_column = tuple(
        tuple(
            block
            for block in ordered
            if _assigned_column(block.bbox, header.bands) == column
        )
        for column in range(1, 4)
    )
    if sum(map(len, by_column)) != len(ordered) or any(
        len(candidates) < 2 for candidates in by_column
    ):
        return ordered
    return tuple(
        min(
            candidates,
            key=lambda block: (
                abs(block.bbox.center_x - header.blocks[column].bbox.center_x),
                block.provider_order,
            ),
        )
        for column, candidates in enumerate(by_column, start=1)
    )


def _numeric_tracks(
    header: _HeaderSeed,
    full_seeds: tuple[_NumericRowSeed, ...],
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    header_centers = tuple(block.bbox.center_x for block in header.blocks[1:])
    tracks: list[tuple[float, float]] = []
    for column in range(3):
        points = tuple(
            (row.center_y, row.blocks[column].bbox.center_x) for row in full_seeds
        )
        slopes = tuple(
            (right_x - left_x) / (right_y - left_y)
            for left_index, (left_y, left_x) in enumerate(points)
            for right_y, right_x in points[left_index + 1 :]
            if right_y != left_y
        )
        if slopes:
            slope = median(slopes)
            intercept = median(x - slope * y for y, x in points)
        else:
            slope = 0.0
            intercept = header_centers[column]
        tracks.append((slope, intercept))
    return tracks[0], tracks[1], tracks[2]


def _map_numeric_seed(
    seed: _NumericRowSeed,
    tracks: tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
) -> tuple[_GeometryBlock | None, _GeometryBlock | None, _GeometryBlock | None] | None:
    expected = tuple(slope * seed.center_y + intercept for slope, intercept in tracks)
    track_gap = min(expected[1] - expected[0], expected[2] - expected[1])
    if track_gap <= 0.0:
        return None
    if len(seed.blocks) == 3:
        if any(
            abs(block.bbox.center_x - expected[column]) > track_gap * 0.60
            for column, block in enumerate(seed.blocks)
        ):
            return None
        return seed.blocks[0], seed.blocks[1], seed.blocks[2]
    if len(seed.blocks) == 1:
        ranked_columns = sorted(
            (
                abs(seed.blocks[0].bbox.center_x - expected[column]),
                column,
            )
            for column in range(3)
        )
        best_error, best_column = ranked_columns[0]
        second_error = ranked_columns[1][0]
        if (
            best_error > track_gap * 0.60
            or second_error - best_error < track_gap * 0.25
        ):
            return None
        mapped_single: list[_GeometryBlock | None] = [None, None, None]
        mapped_single[best_column] = seed.blocks[0]
        return mapped_single[0], mapped_single[1], mapped_single[2]
    if len(seed.blocks) != 2:
        return None
    combinations = ((0, 1), (0, 2), (1, 2))
    ranked = sorted(
        (
            sum(
                abs(block.bbox.center_x - expected[column])
                for block, column in zip(seed.blocks, columns, strict=True)
            ),
            columns,
        )
        for columns in combinations
    )
    best_error, best_columns = ranked[0]
    second_error = ranked[1][0]
    if best_error > track_gap or second_error - best_error < track_gap * 0.25:
        return None
    mapped: list[_GeometryBlock | None] = [None, None, None]
    for block, column in zip(seed.blocks, best_columns, strict=True):
        mapped[column] = block
    return mapped[0], mapped[1], mapped[2]


def _name_line_groups(
    seed: _HeaderSeed,
    body_blocks: tuple[_GeometryBlock, ...],
) -> tuple[tuple[_GeometryBlock, ...], ...]:
    name_band_width = seed.bands[0][1] - seed.bands[0][0]
    header_start = seed.blocks[0].bbox.x_min
    minimum_start = header_start - name_band_width * 0.65
    name_blocks = [
        block
        for block in body_blocks
        if minimum_start <= block.bbox.x_min
        and block.bbox.x_min < seed.bands[0][1]
        and not _is_structural_numeric(block.source.text)
    ]
    if len(name_blocks) >= 3:
        typical_name_height = median(block.bbox.height for block in name_blocks)
        name_blocks = [
            block
            for block in name_blocks
            if block.bbox.height
            <= typical_name_height * _MAX_NAME_BLOCK_HEIGHT_RATIO
        ]
    groups: list[list[_GeometryBlock]] = []
    for block in sorted(
        name_blocks,
        key=lambda item: (item.bbox.center_y, item.bbox.x_min, item.provider_order),
    ):
        compatible = [
            group
            for group in groups
            if _name_fragment_center_is_local(block, group)
            and _name_fragment_is_horizontally_local(block, group)
        ]
        if compatible:
            min(
                compatible,
                key=lambda group: abs(
                    block.bbox.center_y
                    - median(member.bbox.center_y for member in group)
                ),
            ).append(block)
        else:
            groups.append([block])
    ordered_groups = [
        tuple(sorted(group, key=lambda block: (block.bbox.x_min, block.provider_order)))
        for group in groups
    ]
    ordered_groups.sort(
        key=lambda group: (
            median(block.bbox.center_y for block in group),
            min(block.bbox.x_min for block in group),
        )
    )
    return tuple(ordered_groups)


def _name_fragment_center_is_local(
    block: _GeometryBlock,
    group: list[_GeometryBlock],
) -> bool:
    group_bbox = _union(member.bbox for member in group)
    overlap_ratio = _horizontal_overlap(block.bbox, group_bbox) / min(
        block.bbox.width,
        group_bbox.width,
    )
    has_parenthetical = any(
        _compact_text(member.source.text).startswith(("(", "["))
        for member in (block, *group)
    )
    distance_ratio = (
        0.25
        if has_parenthetical
        else 0.60 if overlap_ratio < 0.25 else _MAX_NAME_FRAGMENT_CENTER_DISTANCE
    )
    typical_height = median(
        (block.bbox.height, *(member.bbox.height for member in group))
    )
    return (
        abs(
            block.bbox.center_y
            - median(member.bbox.center_y for member in group)
        )
        <= typical_height * distance_ratio
    )


def _name_fragment_is_horizontally_local(
    block: _GeometryBlock,
    group: list[_GeometryBlock],
) -> bool:
    group_bbox = _union(member.bbox for member in group)
    if block.bbox.x_min >= group_bbox.x_max and any(
        _inline_explicit_truncation_prefix(member.source.text) is not None
        for member in group
    ):
        return False
    if (
        block.bbox.x_max <= group_bbox.x_min
        and _inline_explicit_truncation_prefix(block.source.text) is not None
    ):
        return False
    horizontal_gap = max(
        0.0,
        block.bbox.x_min - group_bbox.x_max,
        group_bbox.x_min - block.bbox.x_max,
    )
    typical_height = median(
        (block.bbox.height, *(member.bbox.height for member in group))
    )
    return horizontal_gap <= typical_height * _MAX_NAME_FRAGMENT_HORIZONTAL_GAP


def _name_blocks_for_row(
    groups: tuple[tuple[_GeometryBlock, ...], ...],
    anchor_y: float,
    lower: float,
    upper: float,
    typical_height: float,
) -> tuple[_GeometryBlock, ...]:
    candidates = [
        group
        for group in groups
        if lower <= median(block.bbox.center_y for block in group) < upper
        and abs(median(block.bbox.center_y for block in group) - anchor_y)
        <= max(
            typical_height * _MAX_WRAPPED_NAME_DISTANCE,
            median(block.bbox.height for block in group)
            * _MAX_WRAPPED_NAME_DISTANCE,
        )
    ]
    if not candidates:
        return ()
    selected = min(
        candidates,
        key=lambda group: (
            not _looks_like_medication_name_blocks(group),
            abs(median(block.bbox.center_y for block in group) - anchor_y),
            min(block.bbox.x_min for block in group),
            tuple(block.provider_order for block in group),
        ),
    )
    selected_center = median(block.bbox.center_y for block in selected)
    preceding = [
        group
        for group in candidates
        if median(block.bbox.center_y for block in group) < selected_center
    ]
    if preceding:
        previous = max(
            preceding,
            key=lambda group: median(block.bbox.center_y for block in group),
        )
        previous_bbox = _union(block.bbox for block in previous)
        selected_bbox = _union(block.bbox for block in selected)
        vertical_distance = (
            selected_center - median(block.bbox.center_y for block in previous)
        ) / median((previous_bbox.height, selected_bbox.height))
        horizontal_overlap = _horizontal_overlap(previous_bbox, selected_bbox) / min(
            previous_bbox.width, selected_bbox.width
        )
        left_edge_gap = abs(previous_bbox.x_min - selected_bbox.x_min)
        if (
            vertical_distance <= _MAX_WRAPPED_NAME_JOIN_DISTANCE
            and horizontal_overlap >= _MIN_WRAPPED_NAME_HORIZONTAL_OVERLAP
            and left_edge_gap
            <= median((previous_bbox.height, selected_bbox.height))
            * _MAX_NAME_FRAGMENT_HORIZONTAL_GAP
            and not any(
                _compact_text(block.source.text).startswith(("(", "["))
                for block in previous
            )
        ):
            return (*previous, *selected)
    return selected


def _looks_like_medication_name_blocks(
    blocks: tuple[_GeometryBlock, ...],
) -> bool:
    normalized = _compact_text(" ".join(block.source.text for block in blocks))
    unit_normalized = normalize_measurement_unit_ocr(normalized)
    return (
        sum("가" <= character <= "힣" for character in normalized) >= 2
        and (
            _MEDICATION_NAME_FORM_PATTERN.search(normalized) is not None
            or _OCR_STRENGTH_LIKE_PATTERN.search(unit_normalized) is not None
        )
        and _SUMMARY_ROW_MARKER_PATTERN.search(normalized) is None
        and not ("[앞]" in normalized and "[뒤]" in normalized)
    )


def _next_overlapping_header_top(
    current: _HeaderSeed, seeds: tuple[_HeaderSeed, ...]
) -> float | None:
    overlapping_tops = [
        seed.bbox.y_min
        for seed in seeds
        if seed.bbox.center_y > current.bbox.center_y
        and _horizontal_overlap(seed.bbox, current.bbox)
        / min(seed.bbox.width, current.bbox.width)
        >= 0.5
    ]
    return min(overlapping_tops, default=None)


def _body_fragments(
    seed: _HeaderSeed,
    line_groups: tuple[_LineGroup, ...],
    all_header_ids: set[str],
    lower_header: float | None,
) -> tuple[
    tuple[_BodyFragment, ...],
    tuple[_GeometryBlock, ...],
    tuple[LayoutIssue, ...],
]:
    fragments: list[_BodyFragment] = []
    ambiguous_blocks: list[_GeometryBlock] = []
    issues: list[LayoutIssue] = []
    previous_center = seed.bbox.center_y
    previous_height = median(block.bbox.height for block in seed.blocks)
    for line in line_groups:
        if line.bbox.center_y <= seed.bbox.center_y:
            continue
        if lower_header is not None and line.bbox.y_min >= lower_header:
            break
        relevant = [
            block
            for block in line.blocks
            if block.source.block_id not in all_header_ids
            and _horizontal_overlap(block.bbox, seed.bbox) > 0.0
            and (
                seed.numeric_right_bound is None
                or block.bbox.center_x < seed.numeric_right_bound
            )
        ]
        if not relevant:
            continue
        line_height = median(block.bbox.height for block in relevant)
        gap = (line.bbox.center_y - previous_center) / median(
            (line_height, previous_height)
        )
        if gap > _MAX_BODY_LINE_GAP and not _is_nearby_strong_body_row(
            seed,
            relevant,
            gap,
            prior_fragment_count=len(fragments),
        ):
            break
        assigned: list[list[_GeometryBlock]] = [[], [], [], []]
        for block in relevant:
            column = _assigned_column(block.bbox, seed.bands)
            if column is None:
                ambiguous_blocks.append(block)
                issues.append(
                    LayoutIssue(
                        LayoutIssueCode.AMBIGUOUS_COLUMN_ASSIGNMENT,
                        (block.source.block_id,),
                    )
                )
                continue
            assigned[column].append(block)
        assigned_blocks = [block for column in assigned for block in column]
        if not assigned_blocks:
            continue
        fragment_bbox = _union(block.bbox for block in assigned_blocks)
        fragments.append(
            _BodyFragment(
                blocks_by_column=(
                    tuple(assigned[0]),
                    tuple(assigned[1]),
                    tuple(assigned[2]),
                    tuple(assigned[3]),
                ),
                bbox=fragment_bbox,
            )
        )
        previous_center = fragment_bbox.center_y
        previous_height = median(block.bbox.height for block in assigned_blocks)
    return tuple(fragments), tuple(ambiguous_blocks), tuple(issues)


def _is_nearby_strong_body_row(
    seed: _HeaderSeed,
    blocks: list[_GeometryBlock],
    normalized_gap: float,
    *,
    prior_fragment_count: int,
) -> bool:
    if (
        prior_fragment_count < 2
        or normalized_gap > _MAX_STRONG_BODY_LINE_GAP
    ):
        return False
    columns = tuple(_assigned_column(block.bbox, seed.bands) for block in blocks)
    if any(column is None for column in columns):
        return False
    name_blocks = tuple(
        block
        for block, column in zip(blocks, columns, strict=True)
        if column == 0
    )
    if not _looks_like_medication_name(name_blocks):
        return False
    assigned_columns = {column for column in columns if column is not None}
    structural_numeric_count = sum(
        _is_structural_numeric(block.source.text)
        for block, column in zip(blocks, columns, strict=True)
        if column is not None and column > 0
    )
    return (
        0 in assigned_columns
        and len(assigned_columns) >= 3
        and structural_numeric_count >= 2
    )


def _looks_like_medication_name(blocks: tuple[_GeometryBlock, ...]) -> bool:
    normalized = "".join(
        "".join(unicodedata.normalize("NFKC", block.source.text).split())
        for block in blocks
    )
    return (
        bool(normalized)
        and any(character.isalpha() for character in normalized)
        and _SUMMARY_ROW_MARKER_PATTERN.search(normalized) is None
    )


def _ambiguous_column_evidence(
    blocks: tuple[_GeometryBlock, ...],
    rows: tuple[LayoutRow, ...],
    bands: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
) -> tuple[AmbiguousColumnEvidence, ...]:
    evidence: list[AmbiguousColumnEvidence] = []
    for block in sorted(
        blocks,
        key=lambda item: (
            item.bbox.center_y,
            item.bbox.x_min,
            item.provider_order,
        ),
    ):
        nearest_row_index = None
        if rows:
            _, nearest_row_index = min(
                (
                    abs(block.bbox.center_y - row.bbox.center_y)
                    / median((block.bbox.height, row.bbox.height)),
                    index,
                )
                for index, row in enumerate(rows)
            )
        evidence.append(
            AmbiguousColumnEvidence(
                source_text=block.source.text,
                block_ids=(block.source.block_id,),
                bbox=block.bbox,
                nearest_row_index=nearest_row_index,
                overlapping_columns=tuple(
                    _HEADER_ORDER[index]
                    for index, (left, right) in enumerate(bands)
                    if block.bbox.x_max > left and block.bbox.x_min < right
                ),
            )
        )
    return tuple(evidence)


def _assigned_column(
    bbox: AxisAlignedBBox,
    bands: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
) -> int | None:
    overlap_fractions = [
        max(0.0, min(bbox.x_max, right) - max(bbox.x_min, left)) / bbox.width
        for left, right in bands
    ]
    ranked = sorted(
        ((fraction, index) for index, fraction in enumerate(overlap_fractions)),
        reverse=True,
    )
    best_fraction, best_index = ranked[0]
    second_fraction = ranked[1][0]
    if (
        best_fraction < _COLUMN_MIN_OVERLAP
        or second_fraction > _COLUMN_MAX_SECONDARY_OVERLAP
    ):
        return None
    return best_index


def _layout_rows(fragments: tuple[_BodyFragment, ...]) -> tuple[LayoutRow, ...]:
    if not fragments:
        return ()
    anchor_indices = [
        index
        for index, fragment in enumerate(fragments)
        if _numeric_anchor_count(fragment) >= 2
    ]
    grouped: dict[int, list[_BodyFragment]] = {
        index: [fragments[index]] for index in anchor_indices
    }
    for index, fragment in enumerate(fragments):
        if index in grouped:
            continue
        following_anchors = [anchor for anchor in anchor_indices if anchor > index]
        if following_anchors and fragment.blocks_by_column[0]:
            following_distances = [
                (
                    abs(fragment.bbox.center_y - fragments[anchor].bbox.center_y)
                    / median((fragment.bbox.height, fragments[anchor].bbox.height)),
                    anchor,
                )
                for anchor in following_anchors
            ]
            distance, nearest = min(following_distances)
            preceding_anchor_is_close = any(
                abs(fragment.bbox.center_y - fragments[anchor].bbox.center_y)
                / median((fragment.bbox.height, fragments[anchor].bbox.height))
                <= _MAX_WRAPPED_NAME_DISTANCE
                for anchor in anchor_indices
                if anchor < index
            )
            next_name_blocks = fragments[nearest].blocks_by_column[0]
            horizontal_overlap = 0.0
            if next_name_blocks:
                next_name_bbox = _union(block.bbox for block in next_name_blocks)
                horizontal_overlap = (
                    _horizontal_overlap(fragment.bbox, next_name_bbox)
                    / min(fragment.bbox.width, next_name_bbox.width)
                )
            if (
                distance <= _MAX_WRAPPED_NAME_DISTANCE
                and not preceding_anchor_is_close
                and horizontal_overlap >= _MIN_WRAPPED_NAME_HORIZONTAL_OVERLAP
            ):
                grouped[nearest].append(fragment)
                continue
    row_groups = list(grouped.values())
    row_groups.sort(
        key=lambda group: (
            min(fragment.bbox.center_y for fragment in group),
            min(fragment.bbox.x_min for fragment in group),
        )
    )
    rows: list[LayoutRow] = []
    for row_index, fragments_for_row in enumerate(row_groups, start=1):
        ordered_fragments = sorted(
            fragments_for_row,
            key=lambda fragment: (
                fragment.bbox.center_y,
                fragment.bbox.x_min,
            ),
        )
        cells: list[LayoutCell | None] = []
        for column in range(4):
            blocks = [
                block
                for fragment in ordered_fragments
                for block in fragment.blocks_by_column[column]
            ]
            cells.append(_layout_cell(blocks))
        present_cells = [cell for cell in cells if cell is not None]
        if not present_cells:
            continue
        rows.append(
            LayoutRow(
                row_id=f"row-{row_index:04d}",
                cells=(cells[0], cells[1], cells[2], cells[3]),
                bbox=_union(cell.bbox for cell in present_cells),
            )
        )
    return tuple(rows)


def _numeric_anchor_count(fragment: _BodyFragment) -> int:
    return sum(
        any(_is_structural_numeric(block.source.text) for block in column_blocks)
        for column_blocks in fragment.blocks_by_column[1:]
    )


def _is_structural_numeric(text: str) -> bool:
    comparison = "".join(unicodedata.normalize("NFKC", text).split())
    return _STRUCTURAL_NUMERIC_PATTERN.fullmatch(comparison) is not None


def _layout_cell(blocks: list[_GeometryBlock]) -> LayoutCell | None:
    if not blocks:
        return None
    ordered = blocks
    confidences = [
        block.source.confidence
        for block in ordered
        if block.source.confidence is not None and math.isfinite(block.source.confidence)
    ]
    source_issues = tuple(
        dict.fromkeys(issue for block in ordered for issue in block.source_issues)
    )
    return LayoutCell(
        text=" ".join(block.source.text for block in ordered),
        block_ids=tuple(block.source.block_id for block in ordered),
        bbox=_union(block.bbox for block in ordered),
        confidence=sum(confidences) / len(confidences) if confidences else None,
        valid_confidence_count=len(confidences),
        source_issues=source_issues,
    )


def _column_consistency(
    blocks: list[_GeometryBlock],
    bands: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
) -> float:
    if not blocks:
        return 0.0
    values: list[float] = []
    for block in blocks:
        column = _assigned_column(block.bbox, bands)
        if column is None:
            continue
        left, right = bands[column]
        half_width = (right - left) / 2.0
        center = (left + right) / 2.0
        values.append(max(0.0, 1.0 - abs(block.bbox.center_x - center) / half_width))
    return sum(values) / len(values) if values else 0.0


def _horizontal_overlap(first: AxisAlignedBBox, second: AxisAlignedBBox) -> float:
    return max(0.0, min(first.x_max, second.x_max) - max(first.x_min, second.x_min))


def _union(boxes: Iterable[AxisAlignedBBox]) -> AxisAlignedBBox:
    materialized = tuple(boxes)
    if not materialized:
        raise ValueError("Cannot union an empty bbox collection.")
    return AxisAlignedBBox(
        min(box.x_min for box in materialized),
        min(box.y_min for box in materialized),
        max(box.x_max for box in materialized),
        max(box.y_max for box in materialized),
    )


def _deduplicate_issues(issues: Iterable[LayoutIssue]) -> tuple[LayoutIssue, ...]:
    unique = {
        (issue.code, issue.block_ids): issue
        for issue in issues
    }
    return tuple(
        unique[key]
        for key in sorted(
            unique,
            key=lambda item: (
                item[1] and _provider_order(item[1][0]) or (2**63 - 1, ""),
                item[0].value,
                item[1],
            ),
        )
    )

