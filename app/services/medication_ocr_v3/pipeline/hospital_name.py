"""Deterministic hospital-name extraction from header OCR geometry."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import StrEnum

from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrResult
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox, OcrLayoutResult

_LABEL_PATTERN = re.compile(r"(?:병원정보|의료기관|요양기관|병[·ㆍ]?의원명|병원명|발행기관)\s*[:：]?")
_ISSUING_INSTITUTION_END_PATTERN = re.compile(r"(?:병원|의원|의료원|클리닉)")
# A document title such as 조제약&복약안내 precedes the hospital header.
# Only a standalone guidance heading (or a medication column) ends it.
_HEADER_END_PATTERN = re.compile(r"(?:약품명|투약량|1회량|^복약안내(?:\(.*\))?$)")
_TRAILING_PATTERN = re.compile(r"(?:Tel\.?|전화|주소|사업자|조제약사|처방의|담당의)", re.IGNORECASE)
_HOSPITAL_END_PATTERN = re.compile(
    r"(?:종합병원|대학병원|치과병원|치과의원|한의원|의료원|클리닉|병원|의원|[가-힣]{2,15}과)$"
)
_DEPARTMENT_PATTERN = re.compile(
    r"(?:마취통증의학과|정신건강의학과|소아청소년과|비뇨의학과|"
    r"재활의학과|영상의학과|응급의학과|가정의학과|이비인후과|"
    r"정형외과|신경외과|흉부외과|성형외과|산부인과|피부과|신경과|내과|외과|안과|치과)"
)
_PERSON_NAME_PATTERN = re.compile(
    r"[김이박최정강조윤장임한오서신권황안송류홍전고문양손배백허유남심노하곽성차주우구민진지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용][가-힣]{1,2}$"
)
_EXCLUDED_PATTERN = re.compile(r"(?:약국|약사|치료제|복약|약품|주의사항|효능|용법|투약)")
_MAX_HOSPITAL_NAME_LENGTH = 255


class HospitalNameIssueCode(StrEnum):
    AMBIGUOUS_HOSPITAL_NAME = "AMBIGUOUS_HOSPITAL_NAME"


@dataclass(frozen=True, slots=True)
class HospitalNameExtraction:
    value: str | None
    confidence: float | None
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox | None
    issues: tuple[HospitalNameIssueCode, ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    value: str
    confidence: float | None
    block_ids: tuple[str, ...]
    bbox: AxisAlignedBBox
    rank: int


def extract_hospital_name(result: OcrResult, layout: OcrLayoutResult) -> HospitalNameExtraction:
    """Select one header hospital/clinic name without involving the LLM."""

    blocks_by_id = {block.block_id: block for block in result.blocks}
    header_limit = min(
        (line.bbox.y_min for line in layout.lines if _HEADER_END_PATTERN.search(_compact(line.text))),
        default=math.inf,
    )
    candidates: list[_Candidate] = []
    for line in layout.lines:
        if line.bbox.y_min >= header_limit:
            continue
        line_blocks = tuple(
            sorted(
                (blocks_by_id[block_id] for block_id in line.block_ids if block_id in blocks_by_id),
                key=lambda block: bbox.x_min if (bbox := _bbox(block)) is not None else math.inf,
            )
        )
        for region in _horizontal_regions(line_blocks):
            candidate = _candidate_from_line(region)
            if candidate is not None:
                candidates.append(candidate)

    # A receipt can pull the label and value into different global lines, or
    # pull a table-header line above the label. Anchor to original block bounds.
    anchor_header_limit = min(
        (
            bbox.y_min
            for block in result.blocks
            if _HEADER_END_PATTERN.search(_compact(block.text)) and (bbox := _bbox(block)) is not None
        ),
        default=header_limit,
    )
    for block in result.blocks:
        if _LABEL_PATTERN.search(_compact(block.text)) is not None:
            candidate = _candidate_from_label_anchor(block, result.blocks, anchor_header_limit)
            if candidate is not None:
                candidates.append(candidate)

    if not candidates:
        return HospitalNameExtraction(None, None, (), None)
    best_rank = max(candidate.rank for candidate in candidates)
    best_by_value: dict[str, _Candidate] = {}
    for candidate in candidates:
        if candidate.rank == best_rank:
            best_by_value.setdefault(candidate.value, candidate)
    if len(best_by_value) != 1:
        ambiguous = tuple(best_by_value.values())
        confidences = tuple(candidate.confidence for candidate in ambiguous if candidate.confidence is not None)
        return HospitalNameExtraction(
            None,
            min(confidences) if confidences else None,
            tuple(dict.fromkeys(block_id for candidate in ambiguous for block_id in candidate.block_ids)),
            _union(tuple(candidate.bbox for candidate in ambiguous)),
            (HospitalNameIssueCode.AMBIGUOUS_HOSPITAL_NAME,),
        )
    selected = next(iter(best_by_value.values()))
    return HospitalNameExtraction(
        selected.value,
        selected.confidence,
        selected.block_ids,
        selected.bbox,
    )


def _horizontal_regions(blocks: tuple[OcrBlock, ...]) -> tuple[tuple[OcrBlock, ...], ...]:
    """Do not concatenate separate receipt/header panels in a global y-line."""
    regions: list[list[OcrBlock]] = []
    previous: AxisAlignedBBox | None = None
    for block in blocks:
        bbox = _bbox(block)
        if bbox is None:
            continue
        if previous is None or bbox.x_min - previous.x_max > max(
            min(previous.width, bbox.width), min(previous.height, bbox.height) * 3.0
        ):
            regions.append([])
        regions[-1].append(block)
        previous = bbox
    return tuple(tuple(region) for region in regions)


def _candidate_from_label_anchor(
    label: OcrBlock, blocks: tuple[OcrBlock, ...], header_limit: float
) -> _Candidate | None:
    label_bbox = _bbox(label)
    if label_bbox is None or label_bbox.y_min >= header_limit:
        return None
    aligned: list[tuple[OcrBlock, AxisAlignedBBox]] = []
    for block in blocks:
        bbox = _bbox(block)
        if bbox is None or block.block_id == label.block_id or bbox.x_min < label_bbox.x_max:
            continue
        overlap = min(bbox.y_max, label_bbox.y_max) - max(bbox.y_min, label_bbox.y_min)
        if overlap >= min(bbox.height, label_bbox.height) * 0.35:
            aligned.append((block, bbox))
    local = [label]
    previous = label_bbox
    max_gap = max(label_bbox.width, label_bbox.height * 2.0)
    for block, bbox in sorted(aligned, key=lambda item: (item[1].x_min, item[1].y_min, item[0].block_id)):
        if bbox.x_min - previous.x_max > max_gap or _LABEL_PATTERN.search(_compact(block.text)) is not None:
            break
        local.append(block)
        previous = bbox
    candidate = _candidate_from_line(tuple(local))
    return replace(candidate, rank=3) if candidate is not None else None


def _candidate_from_line(blocks: tuple[OcrBlock, ...]) -> _Candidate | None:
    if not blocks:
        return None
    issuer_bbox = next((_bbox(block) for block in blocks if "발행기관" in block.text), None)
    if issuer_bbox is not None:
        # Receipt columns can bridge separate header rows into one layout line.
        # Keep only blocks vertically aligned with the issuer label itself.
        blocks = tuple(
            block
            for block in blocks
            if (bbox := _bbox(block)) is not None
            and min(bbox.y_max, issuer_bbox.y_max) - max(bbox.y_min, issuer_bbox.y_min)
            >= min(bbox.height, issuer_bbox.height) * 0.35
        )
    rendered = _render_blocks(blocks)
    label_match = _LABEL_PATTERN.search(rendered)
    rank = 2 if label_match is not None else 1
    source = rendered[label_match.end() :] if label_match is not None else rendered
    source = _TRAILING_PATTERN.split(source, maxsplit=1)[0]
    is_issuer = label_match is not None and label_match.group().startswith("발행기관")
    if is_issuer:
        # This header often continues with an unlabelled doctor and receipt columns.
        # An issuer may also be a pharmacy: require an explicit institution suffix.
        source = _compact(source)
        institution_end = _ISSUING_INSTITUTION_END_PATTERN.search(source)
        if institution_end is None:
            return None
        source = source[: institution_end.end()]
    value = _normalize_candidate(source, labelled=label_match is not None)
    if value is None:
        return None

    evidence_blocks = _evidence_blocks(blocks, label_match is not None)
    if is_issuer:
        for end in range(1, len(evidence_blocks) + 1):
            if value in _compact(_render_blocks(evidence_blocks[:end])):
                evidence_blocks = evidence_blocks[:end]
                break
    bboxes = tuple(bbox for block in evidence_blocks if (bbox := _bbox(block)) is not None)
    if not evidence_blocks or not bboxes:
        return None
    confidences = tuple(
        float(block.confidence)
        for block in evidence_blocks
        if block.confidence is not None and math.isfinite(block.confidence)
    )
    confidence = min(confidences) if confidences else None
    if label_match is not None and _HOSPITAL_END_PATTERN.search(value) is None:
        confidence = min(confidence, 0.69) if confidence is not None else 0.69
    return _Candidate(
        value=value,
        confidence=confidence,
        block_ids=tuple(block.block_id for block in evidence_blocks),
        bbox=_union(bboxes),
        rank=rank,
    )


def _render_blocks(blocks: tuple[OcrBlock, ...]) -> str:
    rendered = blocks[0].text.strip()
    previous_bbox = _bbox(blocks[0])
    for block in blocks[1:]:
        current_bbox = _bbox(block)
        separator = " "
        if previous_bbox is not None and current_bbox is not None:
            gap = current_bbox.x_min - previous_bbox.x_max
            if gap <= min(previous_bbox.height, current_bbox.height) * 0.6:
                separator = ""
        rendered += separator + block.text.strip()
        previous_bbox = current_bbox
    return rendered


def _normalize_candidate(source: str, *, labelled: bool) -> str | None:
    value = source.strip(" :：·ㆍ,，-/[]()")
    value = "".join(value.split())
    if not 3 <= len(value) <= _MAX_HOSPITAL_NAME_LENGTH:
        return None
    if _EXCLUDED_PATTERN.search(value):
        return None
    value = _trim_person_after_department(value)
    if _HOSPITAL_END_PATTERN.search(value) is None and not labelled:
        return None
    if labelled and len(re.findall(r"[가-힣]", value)) < 3:
        return None
    return value


def _trim_person_after_department(value: str) -> str:
    for match in reversed(tuple(_DEPARTMENT_PATTERN.finditer(value))):
        trailing = value[match.end() :].strip("()（）")
        if _PERSON_NAME_PATTERN.fullmatch(trailing):
            return value[: match.end()]
    return value


def _evidence_blocks(blocks: tuple[OcrBlock, ...], labelled: bool) -> tuple[OcrBlock, ...]:
    if not labelled:
        return blocks
    label_seen = False
    first_value_index: int | None = None
    for index, block in enumerate(blocks):
        text = block.text.strip()
        label_match = _LABEL_PATTERN.search(text)
        if label_match is not None:
            label_seen = True
            if text[label_match.end() :].strip(" :：·ㆍ,，-/[]()"):
                first_value_index = index
                break
            continue
        if label_seen and text.strip(" :：·ㆍ,，-/[]()"):
            first_value_index = index
            break
    if first_value_index is None:
        return ()
    value_blocks: list[OcrBlock] = []
    for block in blocks[first_value_index:]:
        if _TRAILING_PATTERN.search(block.text):
            break
        value_blocks.append(block)
    return tuple(value_blocks)


def _bbox(block: OcrBlock) -> AxisAlignedBBox | None:
    if block.bbox is None:
        return None
    xs = tuple(point.x for point in block.bbox)
    ys = tuple(point.y for point in block.bbox)
    if not all(math.isfinite(value) for value in (*xs, *ys)):
        return None
    bbox = AxisAlignedBBox(min(xs), min(ys), max(xs), max(ys))
    return bbox if bbox.width > 0 and bbox.height > 0 else None


def _union(bboxes: tuple[AxisAlignedBBox, ...]) -> AxisAlignedBBox:
    return AxisAlignedBBox(
        min(bbox.x_min for bbox in bboxes),
        min(bbox.y_min for bbox in bboxes),
        max(bbox.x_max for bbox in bboxes),
        max(bbox.y_max for bbox in bboxes),
    )


def _compact(value: str) -> str:
    return "".join(value.split())
