"""Add privacy-bounded product-title context for semantic medication review."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.services.medication_ocr_v3.domain.grounding import EvidenceBlock, EvidenceCatalog
from app.services.medication_ocr_v3.domain.models import OcrResult
from app.services.medication_ocr_v3.pipeline.evidence_catalog import (
    _canonical_name,
    _eligible,
    _line_indexes,
    _names_match,
    _normalized,
    _strength_block_id_groups,
    _unique_geometry_sources,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import MedicationRowsResult, _is_plausible_product_name
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox, OcrLayoutResult

_SCHEDULE_FIELDS = ("doseQuantity", "timesPerDay", "days")


@dataclass(frozen=True, slots=True)
class _Title:
    block_id: str
    row_id: str | None
    bbox: AxisAlignedBBox


def build_semantic_evidence_catalog(
    ocr_result: OcrResult,
    layout: OcrLayoutResult,
    medication_rows: MedicationRowsResult,
    original: EvidenceCatalog,
) -> EvidenceCatalog:
    """Retain legacy evidence and link printed strengths to matching product titles.

    Only titles matching one already-extracted medication and their local strength
    lines can add text. Raw document lines and unconstrained nearby numbers cannot.
    The original catalog is immutable and remains the legacy/no-LLM comparison.
    """
    sources, duplicate_ids = _unique_geometry_sources(ocr_result.blocks)
    line_ids, sensitive_ids, segments = _line_indexes(layout, sources)

    def eligible(block_id: str) -> bool:
        return _eligible(block_id, sources, duplicate_ids, line_ids, sensitive_ids)

    row_names: dict[str, str] = {}
    for medication in medication_rows.medications:
        name_ids = set(medication.fields.name.block_ids)
        matches = [row.row_id for row in original.rows if name_ids.intersection(row.block_ids)]
        if len(matches) == 1:
            row_names[matches[0]] = _canonical_name(medication.name)

    titles: list[_Title] = []
    for block_id, (source, bbox) in sources.items():
        if not eligible(block_id):
            continue
        name = _canonical_name(source.text)
        matches = [row_id for row_id, candidate in row_names.items() if _names_match(name, candidate)]
        if len(matches) == 1:
            titles.append(_Title(block_id, matches[0], bbox))
        elif _is_plausible_product_name(source.text.split("(", 1)[0]):
            # An unmatched product can bound a region but cannot supply evidence.
            titles.append(_Title(block_id, None, bbox))

    blocks = {block.block_id: block for block in original.blocks}
    schedule_ids = {
        block.block_id for block in original.blocks if set(block.allowed_fields).intersection(_SCHEDULE_FIELDS)
    }
    fragmented_schedule_ids = set()
    table_rows = medication_rows.selected_table.rows if medication_rows.selected_table is not None else ()
    for table_row in table_rows:
        for cell in table_row.cells[1:]:
            if cell is None or not cell.parsed_text or len(cell.block_ids) != 1 or cell.block_ids[0] not in sources:
                continue
            source = sources[cell.block_ids[0]][0]
            raw = "".join(_normalized(source.text).split())
            fragment = "".join(_normalized(cell.parsed_text).split())
            if (
                re.fullmatch(r"\d+(?:\.\d+)?", raw)
                and re.fullmatch(r"\d+(?:\.\d+)?", fragment)
                and raw != fragment
                and fragment in raw
            ):
                # A layout-split cell (3 from OCR 33) is not the whole OCR token.
                # Keep its safe fallback; don't offer the joined token as a new value.
                fragmented_schedule_ids.add(cell.block_ids[0])

    def assign(block_id: str, row_id: str, fields: tuple[str, ...]) -> None:
        source, bbox = sources[block_id]
        previous = blocks.get(block_id)
        # Never move structural schedule/name evidence into another medication.
        if (
            previous is not None
            and previous.row_ids != (row_id,)
            and any(field != "strength" for field in previous.allowed_fields)
        ):
            return
        merged = tuple(
            dict.fromkeys((*(previous.allowed_fields if previous and previous.row_ids == (row_id,) else ()), *fields))
        )
        blocks[block_id] = EvidenceBlock(
            block_id,
            _normalized(source.text),
            source.confidence,
            bbox,
            line_ids[block_id],
            (row_id,),
            merged,
            previous.allowed_fields if previous and previous.row_ids == (row_id,) else fields,
        )

    for title in titles:
        if title.row_id is not None:
            assign(title.block_id, title.row_id, ("name",))

    for line in segments:
        if not all(eligible(block_id) for block_id in line.block_ids):
            continue
        groups = _strength_block_id_groups(line, sources)
        for group in groups:
            if not group or group.intersection(schedule_ids):
                continue
            boxes = [sources[block_id][1] for block_id in group]
            bbox = AxisAlignedBBox(
                min(b.x_min for b in boxes),
                min(b.y_min for b in boxes),
                max(b.x_max for b in boxes),
                max(b.y_max for b in boxes),
            )
            title = _preceding_title(bbox, titles)
            if title is None or title.row_id is None:
                continue
            for block_id in group:
                assign(block_id, title.row_id, ("strength",))
            # Do not send arbitrary neighboring text: it may be an unlabeled person.

    for block_id, block in tuple(blocks.items()):
        if block_id in schedule_ids:
            blocks[block_id] = replace(
                block,
                allowed_fields=() if block_id in fragmented_schedule_ids else _SCHEDULE_FIELDS,
                field_hints=block.allowed_fields,
            )
    rows = tuple(
        replace(
            row,
            block_ids=tuple(
                b.block_id
                for b in sorted(blocks.values(), key=lambda b: (b.bbox.y_min, b.bbox.x_min, b.block_id))
                if b.row_ids == (row.row_id,)
            )[:192],
        )
        for row in original.rows
    )
    included_ids = {block_id for row in rows for block_id in row.block_ids}
    included_ids.update(block.block_id for block in original.date_candidates)
    return EvidenceCatalog(
        blocks=tuple(block for block_id, block in blocks.items() if block_id in included_ids),
        date_candidates=original.date_candidates,
        rows=rows,
        schema_version="semantic-v1",
    )


def _preceding_title(bbox: AxisAlignedBBox, titles: list[_Title]) -> _Title | None:
    candidates = []
    for title in titles:
        horizontal_overlap = min(bbox.x_max, title.bbox.x_max) - max(bbox.x_min, title.bbox.x_min)
        height = max(title.bbox.height, bbox.height)
        crosses_title = any(
            other.block_id != title.block_id
            and title.bbox.y_min + bbox.height * 0.5 < other.bbox.y_min <= bbox.y_min
            and abs(other.bbox.x_min - title.bbox.x_min) <= max(height, other.bbox.height) * 2.0
            for other in titles
        )
        if (
            horizontal_overlap >= min(bbox.width, title.bbox.width) * 0.5
            and title.bbox.y_min <= bbox.y_min + bbox.height * 0.25
            and bbox.y_min - title.bbox.y_max <= height * 6.0
            and not crosses_title
        ):
            candidates.append(title)
    if not candidates:
        return None
    nearest_y = max(title.bbox.y_min for title in candidates)
    nearest = [title for title in candidates if abs(title.bbox.y_min - nearest_y) <= bbox.height * 0.5]
    if len({title.row_id for title in nearest}) != 1:
        return None
    return max(nearest, key=lambda title: title.bbox.y_min)
