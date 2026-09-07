"""Validate five-field LLM proposals against exact, row-owned OCR evidence."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import replace

from app.services.medication_ocr_v3.domain.grounding import (
    EvidenceBlock,
    EvidenceCatalog,
    GroundingSelection,
    SemanticFieldSelection,
    SemanticGroundingSelection,
)
from app.services.medication_ocr_v3.pipeline.grounding import (
    _STRENGTH_PATTERN,
    GroundedField,
    GroundedMedication,
    GroundedResult,
    GroundingIssue,
    GroundingIssueCode,
    _bbox_union,
    _conservative_confidence,
    _visual_reading_order,
    materialize_grounded_selection,
    parse_strength,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationFields,
    MedicationRowsResult,
    _canonical_name_value,
    dose_quantity_value_and_unit,
    parse_days,
    parse_times_per_day,
)
from app.services.medication_ocr_v3.pipeline.ocr_normalization import (
    normalize_measurement_unit_ocr,
    normalize_strength_ocr,
)
from app.services.medication_ocr_v3.pipeline.review_projection import _public_dose_quantity

_FIELDS = {
    "name": "name",
    "strength": "strength",
    "doseQuantity": "dose_quantity",
    "timesPerDay": "times_per_day",
    "days": "days",
}


def materialize_semantic_review(
    catalog: EvidenceCatalog,
    medication_rows: MedicationRowsResult,
    baseline: GroundedResult,
    selection: SemanticGroundingSelection,
) -> tuple[MedicationRowsResult, GroundedResult]:
    """Apply supported proposals; preserve fallback and flag all rejected decisions."""
    block_counts = Counter(b.block_id for b in catalog.blocks)
    blocks = {b.block_id: b for b in catalog.blocks if block_counts[b.block_id] == 1}
    row_counts = Counter(row.row_id for row in catalog.rows)
    rows = {row.row_id: set(row.block_ids) for row in catalog.rows if row_counts[row.row_id] == 1}
    selection_counts = Counter(row.row_id for row in selection.medications)
    selected = {row.row_id: row for row in selection.medications if selection_counts[row.row_id] == 1}
    grounded_by_id = {row.row_id: row for row in baseline.medications}
    issues: list[GroundingIssue] = []
    accepted_fields: set[tuple[str, str]] = set()
    invalid_reuse = _invalid_reuse(selection)

    for row in selection.medications:
        if row.row_id not in rows:
            issues.append(GroundingIssue(GroundingIssueCode.UNKNOWN_ROW_ID, "name", (), row.row_id))
        elif selection_counts[row.row_id] > 1:
            issues.append(GroundingIssue(GroundingIssueCode.DUPLICATE_ROW_ID, "name", (), row.row_id))

    reviewed_rows = []
    reviewed_grounded = dict(grounded_by_id)
    for row in medication_rows.medications:
        memberships = [key for key, ids in rows.items() if ids.intersection(row.fields.name.block_ids)]
        if len(memberships) != 1:
            reviewed_rows.append(row)
            fallback_ids = [
                original.row_id
                for original in baseline.medications
                if set(original.name.block_ids).intersection(row.fields.name.block_ids)
            ]
            issues.append(
                GroundingIssue(
                    GroundingIssueCode.INCOMPLETE_SEMANTIC_REVIEW,
                    "name",
                    tuple(row.fields.name.block_ids),
                    fallback_ids[0] if len(fallback_ids) == 1 else None,
                )
            )
            continue
        row_id = memberships[0]
        original = grounded_by_id.get(row_id) or GroundedMedication(
            row_id,
            _from_medication_field(row.fields.name),
            _empty(),
            _from_medication_field(row.fields.dose_quantity),
            _from_medication_field(row.fields.times_per_day),
            _from_medication_field(row.fields.days),
        )
        proposal = selected.get(row_id)
        replacements = {}
        if proposal is None:
            issues.append(GroundingIssue(GroundingIssueCode.INCOMPLETE_SEMANTIC_REVIEW, "name", (), row_id))
        else:
            for field, attribute in _FIELDS.items():
                offered = getattr(proposal, attribute)
                fallback = getattr(original, attribute)
                if offered.status != "supported":
                    if offered.text is not None or offered.block_ids:
                        issues.append(
                            GroundingIssue(
                                GroundingIssueCode.INVALID_FIELD_VALUE, field, tuple(offered.block_ids), row_id
                            )
                        )
                    elif offered.status == "uncertain" or fallback.value not in (None, ""):
                        issues.append(GroundingIssue(GroundingIssueCode.AMBIGUOUS_FIELD_VALUE, field, (), row_id))
                    continue
                value, rejected = _validate_field(
                    blocks,
                    rows[row_id],
                    row_id,
                    field,
                    offered,
                    (row_id, field) in invalid_reuse,
                )
                issues.extend(rejected)
                if value is not None:
                    replacements[attribute] = value
                    accepted_fields.add((row_id, field))
        grounded = replace(original, **replacements)
        fields = MedicationFields(
            *(
                _to_medication_field(getattr(grounded, field)) if field in replacements else getattr(row.fields, field)
                for field in ("name", "dose_quantity", "times_per_day", "days")
            )
        )
        reviewed_rows.append(
            replace(
                row,
                name=fields.name.value or "",
                dose_quantity=fields.dose_quantity.value or "",
                times_per_day=fields.times_per_day.value,
                days=fields.days.value,
                fields=fields,
            )
        )
        reviewed_grounded[row_id] = grounded

    dispensed_date = baseline.dispensed_date
    if selection.dispensed_date_block_ids:
        date_result = materialize_grounded_selection(
            catalog,
            GroundingSelection(
                dispensed_date_block_ids=selection.dispensed_date_block_ids,
                medications=[],
            ),
        )
        if date_result.dispensed_date.value is not None and not date_result.issues:
            dispensed_date = date_result.dispensed_date
            accepted_fields.add(("", "dispensedDate"))
        issues.extend(date_result.issues)
    issues.extend(issue for issue in baseline.issues if (issue.row_id or "", issue.field) not in accepted_fields)
    return replace(medication_rows, medications=tuple(reviewed_rows)), GroundedResult(
        dispensed_date,
        tuple(reviewed_grounded.values()),
        tuple(dict.fromkeys(issues)),
    )


def _invalid_reuse(selection: SemanticGroundingSelection) -> set[tuple[str, str]]:
    uses: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in selection.medications:
        for field, attribute in _FIELDS.items():
            for block_id in getattr(row, attribute).block_ids:
                uses[block_id].append((row.row_id, field))
    for block_id in selection.dispensed_date_block_ids:
        uses[block_id].append(("", "dispensedDate"))
    invalid = set()
    for owners in uses.values():
        if len(owners) <= 1:
            continue
        allowed = (
            len(owners) == 2
            and len({row for row, _ in owners}) == 1
            and {field for _, field in owners} == {"name", "strength"}
        )
        if not allowed:
            invalid.update(owners)
    return invalid


def _validate_field(
    blocks: dict[str, EvidenceBlock],
    row_ids: set[str],
    row_id: str,
    field: str,
    proposal: SemanticFieldSelection,
    invalid_reuse: bool,
) -> tuple[GroundedField | None, list[GroundingIssue]]:
    codes: list[GroundingIssueCode] = []
    ids = tuple(proposal.block_ids)
    if not ids or not proposal.text:
        codes.append(GroundingIssueCode.INVALID_FIELD_VALUE)
    if invalid_reuse or len(set(ids)) != len(ids):
        codes.append(GroundingIssueCode.DUPLICATE_BLOCK_ID)
    evidence = []
    for block_id in ids:
        block = blocks.get(block_id)
        if block is None:
            codes.append(GroundingIssueCode.UNKNOWN_BLOCK_ID)
            continue
        if block.row_ids != (row_id,) or block_id not in row_ids:
            codes.append(GroundingIssueCode.CROSS_ROW_BLOCK_ID)
        if field not in block.allowed_fields:
            codes.append(GroundingIssueCode.WRONG_FIELD)
        evidence.append(block)
    title_evidence = tuple(block for block in evidence if "name" in block.allowed_fields)
    if field == "strength" and title_evidence:
        # Title ownership does not authorize dropping another printed component.
        title_strengths = _strength_values(" ".join(block.text for block in _visual_reading_order(title_evidence)))
        if not title_strengths.issubset(_strength_values(proposal.text or "")):
            codes.append(GroundingIssueCode.AMBIGUOUS_FIELD_VALUE)
    if field == "strength" and not title_evidence:
        # Different ingredient amounts are not interchangeable product strengths.
        # Only an explicit product-title expression can disambiguate this safely.
        row_strength_blocks = tuple(
            block
            for block_id in row_ids
            if (block := blocks.get(block_id)) is not None
            and block.row_ids == (row_id,)
            and "strength" in block.allowed_fields
        )
        strength_text = " ".join(block.text for block in _visual_reading_order(row_strength_blocks))
        if len(_strength_values(strength_text)) > 1:
            codes.append(GroundingIssueCode.AMBIGUOUS_FIELD_VALUE)
    if field in {"doseQuantity", "timesPerDay", "days"} and len(evidence) > 1:
        if len({block.field_hints or block.allowed_fields for block in evidence}) > 1:
            codes.append(GroundingIssueCode.WRONG_FIELD)
    if not codes:
        ordered = _visual_reading_order(evidence)
        source = " ".join(block.text for block in ordered)
        quote = proposal.text or ""
        value = _parse_value(field, quote)
        if not _supported_excerpt(source, quote, field, tuple(block.text for block in ordered)) or value is None:
            codes.append(GroundingIssueCode.INVALID_FIELD_VALUE)
        else:
            return GroundedField(
                value,
                quote,
                tuple(block.block_id for block in ordered),
                (),
                _bbox_union(block.bbox for block in ordered),
                _conservative_confidence(ordered),
                (),
            ), []
    return None, [GroundingIssue(code, field, ids, row_id) for code in dict.fromkeys(codes)]


def _strength_values(text: str) -> set[str]:
    return {
        normalize_strength_ocr(match.group()).casefold()
        for match in _STRENGTH_PATTERN.finditer(normalize_measurement_unit_ocr(text))
    }


def _compact(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def _supported_excerpt(source: str, excerpt: str, field: str, block_texts: tuple[str, ...] = ()) -> bool:
    normalized_source = unicodedata.normalize("NFKC", source)
    positions = [index for index, character in enumerate(normalized_source) if not character.isspace()]
    source, excerpt = _compact(source), _compact(excerpt)
    if not excerpt:
        return False
    for match in re.finditer(re.escape(excerpt), source):
        before, after = source[: match.start()], source[match.end() :]
        if excerpt[0].isdigit() and before and before[-1] in "0123456789./+-":
            continue
        if excerpt[-1].isdigit() and after and after[0] in "0123456789./":
            continue
        if field == "strength" and after.startswith(("/", "+")):
            continue
        if field == "name" and before and before[-1].isalnum():
            continue
        if field in {"name", "doseQuantity"} and after and after[0].isalnum():
            continue
        span = normalized_source[positions[match.start()] : positions[match.end() - 1] + 1]
        if field != "name" and re.search(r"\d\s+\d", span):
            continue
        if block_texts and (
            any(not _compact(text) for text in block_texts)
            or match.start() >= len(_compact(block_texts[0]))
            or match.end() <= len(source) - len(_compact(block_texts[-1]))
        ):
            continue
        return True
    return False


def _parse_value(field: str, text: str) -> str | int | None:
    compact = _compact(text)
    if field == "name":
        return _canonical_name_value(text) if any(c.isalpha() for c in compact) else None
    if field == "strength":
        value = parse_strength(text)
        normalized = normalize_strength_ocr(text)
        return value if value is not None and _compact(value).casefold() == _compact(normalized).casefold() else None
    if field == "doseQuantity":
        value, unit = dose_quantity_value_and_unit(text)
        candidate = MedicationField(f"{value}{unit or ''}", text, (), None, None, ())
        return _public_dose_quantity(candidate)
    if field == "timesPerDay":
        value = parse_times_per_day(compact)
        return value if value is not None and 1 <= value <= 6 else None
    value = parse_days(compact)
    return value if value is not None and 1 <= value <= 365 else None


def _from_medication_field(field: MedicationField) -> GroundedField:
    return GroundedField(field.value, field.source_text, field.block_ids, (), field.bbox, field.confidence, ())


def _to_medication_field(field: GroundedField) -> MedicationField:
    return MedicationField(field.value, field.source_text, field.block_ids, field.bbox, field.confidence, ())


def _empty() -> GroundedField:
    return GroundedField(None, "", (), (), None, None, ())
