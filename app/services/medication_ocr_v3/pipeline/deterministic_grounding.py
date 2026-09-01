"""Plan deterministic v3 grounding and validate the ambiguity-only LLM fallback."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from app.services.medication_ocr_v3.domain.grounding import (
    EvidenceBlock,
    EvidenceCatalog,
    GroundingSelection,
    MedicationBlockSelection,
)
from app.services.medication_ocr_v3.pipeline.grounding import (
    GroundedField,
    GroundedMedication,
    GroundedResult,
    GroundingIssue,
    GroundingIssueCode,
    materialize_grounded_selection,
    parse_dispensed_date,
    parse_strength,
    seoul_today,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationIssueCode,
    MedicationRow,
    MedicationRowsResult,
)


@dataclass(frozen=True, slots=True)
class CanonicalizedField:
    row_id: str
    field: str
    original_block_ids: tuple[str, ...]
    accepted_block_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeterministicGroundingPlan:
    selection: GroundingSelection
    deterministic_row_ids: frozenset[str]
    ambiguous_date: bool
    ambiguous_strength_row_ids: frozenset[str]
    issues: tuple[GroundingIssue, ...]

    @property
    def ambiguity_required(self) -> bool:
        return bool(self.deterministic_row_ids) and (self.ambiguous_date or bool(self.ambiguous_strength_row_ids))


@dataclass(frozen=True, slots=True)
class CanonicalizedGroundingSelection:
    selection: GroundingSelection
    deterministic_row_ids: frozenset[str]
    replaced_fields: tuple[CanonicalizedField, ...]
    issues: tuple[GroundingIssue, ...]
    ambiguity_required: bool = False


@dataclass(frozen=True, slots=True)
class _CandidateSet:
    by_value: dict[str, tuple[tuple[str, ...], ...]]
    invalid_block_ids: tuple[str, ...] = ()

    @property
    def ambiguous(self) -> bool:
        return len(self.by_value) > 1

    def unique_ids(self) -> tuple[str, ...] | None:
        if len(self.by_value) != 1:
            return None
        choices = next(iter(self.by_value.values()))
        return min(choices, key=lambda ids: (len(ids), ids))

    def contains(self, block_ids: tuple[str, ...]) -> bool:
        selected = frozenset(block_ids)
        return any(
            len(choice) == len(block_ids) and frozenset(choice) == selected
            for choices in self.by_value.values()
            for choice in choices
        )


@dataclass(frozen=True, slots=True)
class _ProvenRow:
    row_id: str
    row: MedicationRow


def plan_deterministic_grounding(
    catalog: EvidenceCatalog,
    medication_rows: MedicationRowsResult,
    *,
    today: date | None = None,
) -> DeterministicGroundingPlan:
    """Select every unique valid date/strength candidate without an LLM call."""

    effective_today = today or seoul_today()
    proven_rows = _proven_rows(catalog, medication_rows)
    issues: list[GroundingIssue] = []
    date_candidates = _date_candidates(catalog, today=effective_today)
    date_ids = date_candidates.unique_ids() or ()
    if date_candidates.invalid_block_ids and not date_candidates.by_value:
        issues.append(
            GroundingIssue(
                GroundingIssueCode.INVALID_FIELD_VALUE,
                "dispensedDate",
                date_candidates.invalid_block_ids,
            )
        )

    medications: list[MedicationBlockSelection] = []
    ambiguous_strength_row_ids: set[str] = set()
    for proven in proven_rows:
        candidates = _strength_candidates(catalog, proven.row_id)
        if candidates.ambiguous:
            ambiguous_strength_row_ids.add(proven.row_id)
        strength_ids = candidates.unique_ids() or ()
        if strength_ids:
            medications.append(
                MedicationBlockSelection(
                    row_id=proven.row_id,
                    strength_block_ids=list(strength_ids),
                )
            )

    return DeterministicGroundingPlan(
        selection=GroundingSelection(
            dispensed_date_block_ids=list(date_ids),
            medications=medications,
        ),
        deterministic_row_ids=frozenset(proven.row_id for proven in proven_rows),
        ambiguous_date=date_candidates.ambiguous,
        ambiguous_strength_row_ids=frozenset(ambiguous_strength_row_ids),
        issues=tuple(issues),
    )


def canonicalize_deterministic_selection(
    catalog: EvidenceCatalog,
    medication_rows: MedicationRowsResult,
    llm_selection: GroundingSelection,
    *,
    today: date | None = None,
) -> CanonicalizedGroundingSelection:
    """Merge only valid ambiguity selections into the deterministic base plan."""

    effective_today = today or seoul_today()
    plan = plan_deterministic_grounding(
        catalog,
        medication_rows,
        today=effective_today,
    )
    raw_grounded = materialize_grounded_selection(
        catalog,
        llm_selection,
        today=effective_today,
    )
    issues: list[GroundingIssue] = [*plan.issues, *raw_grounded.issues]
    date_ids = list(plan.selection.dispensed_date_block_ids)
    date_candidates = _date_candidates(catalog, today=effective_today)
    selected_date_ids = tuple(llm_selection.dispensed_date_block_ids)
    if selected_date_ids:
        if plan.ambiguous_date and date_candidates.contains(selected_date_ids):
            if raw_grounded.dispensed_date.value is not None:
                date_ids = list(selected_date_ids)
        elif not _has_issue(issues, "dispensedDate", None):
            issues.append(
                GroundingIssue(
                    GroundingIssueCode.INVALID_FIELD_VALUE,
                    "dispensedDate",
                    selected_date_ids,
                )
            )
    elif plan.ambiguous_date:
        issues.append(
            GroundingIssue(
                GroundingIssueCode.AMBIGUOUS_FIELD_VALUE,
                "dispensedDate",
                tuple(block.block_id for block in catalog.date_candidates),
            )
        )

    direct_by_row = {medication.row_id: medication for medication in plan.selection.medications}
    llm_counts = Counter(medication.row_id for medication in llm_selection.medications)
    grounded_by_row = {medication.row_id: medication for medication in raw_grounded.medications}
    medications: list[MedicationBlockSelection] = list(direct_by_row.values())
    for row_id in sorted(plan.ambiguous_strength_row_ids):
        selections = [medication for medication in llm_selection.medications if medication.row_id == row_id]
        candidates = _strength_candidates(catalog, row_id)
        if len(selections) == 1:
            selected_ids = tuple(selections[0].strength_block_ids)
            grounded = grounded_by_row.get(row_id)
            if (
                selected_ids
                and llm_counts[row_id] == 1
                and candidates.contains(selected_ids)
                and grounded is not None
                and grounded.strength.value is not None
                and not grounded.strength.issues
            ):
                medications.append(selections[0])
                continue
        if not _has_issue(issues, "strength", row_id):
            rejected = tuple(
                dict.fromkeys(block_id for selection in selections for block_id in selection.strength_block_ids)
            )
            issues.append(
                GroundingIssue(
                    GroundingIssueCode.AMBIGUOUS_FIELD_VALUE,
                    "strength",
                    rejected,
                    row_id,
                )
            )

    for selection in llm_selection.medications:
        if selection.row_id not in plan.ambiguous_strength_row_ids and not _has_issue(
            issues,
            "strength",
            selection.row_id,
        ):
            issues.append(
                GroundingIssue(
                    GroundingIssueCode.INVALID_FIELD_VALUE,
                    "strength",
                    tuple(selection.strength_block_ids),
                    selection.row_id,
                )
            )

    return CanonicalizedGroundingSelection(
        selection=GroundingSelection(
            dispensed_date_block_ids=date_ids,
            medications=medications,
        ),
        deterministic_row_ids=plan.deterministic_row_ids,
        replaced_fields=(),
        issues=_deduplicate_issues(issues),
        ambiguity_required=plan.ambiguity_required,
    )


def materialize_deterministic_grounding(
    catalog: EvidenceCatalog,
    medication_rows: MedicationRowsResult,
    canonical: CanonicalizedGroundingSelection,
    *,
    today: date | None = None,
) -> GroundedResult:
    """Attach server-owned medication fields to validated date/strength grounding."""

    grounded = materialize_grounded_selection(
        catalog,
        canonical.selection,
        today=today,
    )
    selected_by_row = {medication.row_id: medication for medication in grounded.medications}
    medications: list[GroundedMedication] = []
    for proven in _proven_rows(catalog, medication_rows):
        selected = selected_by_row.get(proven.row_id)
        medications.append(
            GroundedMedication(
                row_id=proven.row_id,
                name=_grounded_field(proven.row.fields.name),
                strength=(selected.strength if selected is not None else _missing_grounded_field()),
                dose_quantity=_grounded_field(proven.row.fields.dose_quantity),
                times_per_day=_grounded_field(proven.row.fields.times_per_day),
                days=_grounded_field(proven.row.fields.days),
            )
        )
    return GroundedResult(
        dispensed_date=grounded.dispensed_date,
        medications=tuple(medications),
        issues=_deduplicate_issues([*grounded.issues, *canonical.issues]),
    )


def rejected_canonicalized_issues(
    _catalog: EvidenceCatalog,
    _llm_selection: GroundingSelection,
    _replaced_fields: tuple[CanonicalizedField, ...],
) -> tuple[GroundingIssue, ...]:
    """Compatibility seam; v3 records rejection issues during canonicalization."""

    return ()


def apply_canonicalization_issues(
    grounded: GroundedResult,
    canonicalization_issues: tuple[GroundingIssue, ...],
) -> GroundedResult:
    return GroundedResult(
        dispensed_date=grounded.dispensed_date,
        medications=grounded.medications,
        issues=_deduplicate_issues([*grounded.issues, *canonicalization_issues]),
    )


def _proven_rows(
    catalog: EvidenceCatalog,
    medication_rows: MedicationRowsResult,
) -> tuple[_ProvenRow, ...]:
    block_counts = Counter(block.block_id for block in catalog.blocks)
    blocks_by_id = {block.block_id: block for block in catalog.blocks if block_counts[block.block_id] == 1}
    row_counts = Counter(row.row_id for row in catalog.rows)
    memberships: dict[str, list[str]] = defaultdict(list)
    for row in catalog.rows:
        for block_id in row.block_ids:
            memberships[block_id].append(row.row_id)

    proven: list[_ProvenRow] = []
    for medication in medication_rows.medications:
        field = medication.fields.name
        if (
            not medication.name
            or not field.block_ids
            or len(set(field.block_ids)) != len(field.block_ids)
            or field.bbox is None
            or MedicationIssueCode.INVALID_BLOCK_GEOMETRY in field.issues
        ):
            continue
        row_ids: set[str] = set()
        valid = True
        for block_id in field.block_ids:
            block = blocks_by_id.get(block_id)
            block_memberships = memberships.get(block_id, [])
            if (
                block is None
                or "name" not in block.allowed_fields
                or len(block.row_ids) != 1
                or len(block_memberships) != 1
                or block.row_ids[0] != block_memberships[0]
                or row_counts[block_memberships[0]] != 1
            ):
                valid = False
                break
            row_ids.add(block_memberships[0])
        if valid and len(row_ids) == 1:
            proven.append(_ProvenRow(row_ids.pop(), medication))
    proven_counts = Counter(item.row_id for item in proven)
    return tuple(item for item in proven if proven_counts[item.row_id] == 1)


def _date_candidates(catalog: EvidenceCatalog, *, today: date) -> _CandidateSet:
    by_value: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    invalid_ids: list[str] = []
    for block in catalog.date_candidates:
        value = parse_dispensed_date(block.text, today=today)
        if value is not None:
            by_value[value].append((block.block_id,))
        elif any(character.isdigit() for character in block.text):
            invalid_ids.append(block.block_id)
    return _CandidateSet(
        by_value={key: tuple(values) for key, values in by_value.items()},
        invalid_block_ids=tuple(dict.fromkeys(invalid_ids)),
    )


def _strength_candidates(catalog: EvidenceCatalog, row_id: str) -> _CandidateSet:
    blocks_by_id = {block.block_id: block for block in catalog.blocks}
    matching_rows = [row for row in catalog.rows if row.row_id == row_id]
    if len(matching_rows) != 1:
        return _CandidateSet({})
    blocks = tuple(
        sorted(
            (
                blocks_by_id[block_id]
                for block_id in matching_rows[0].block_ids
                if block_id in blocks_by_id
                and "strength" in blocks_by_id[block_id].allowed_fields
                and blocks_by_id[block_id].row_ids == (row_id,)
            ),
            key=_evidence_key,
        )
    )
    groups: set[tuple[str, ...]] = set()
    by_line: dict[str, list[EvidenceBlock]] = defaultdict(list)
    for block in blocks:
        by_line[block.line_id].append(block)
    for line_blocks in by_line.values():
        ordered = sorted(line_blocks, key=_evidence_key)
        combined_ids = tuple(block.block_id for block in ordered[:4])
        combined_text = " ".join(block.text for block in ordered[:4])
        if parse_strength(combined_text) is not None:
            groups.add(combined_ids)
        for block in ordered:
            if parse_strength(block.text) is not None:
                groups.add((block.block_id,))

    values: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    for block_ids in groups:
        selected = [blocks_by_id[block_id] for block_id in block_ids]
        selected.sort(key=_evidence_key)
        value = parse_strength(" ".join(block.text for block in selected))
        if value is not None:
            values[_normalized_strength(value)].append(tuple(block.block_id for block in selected))
    name_block_ids = {block.block_id for block in blocks if "name" in block.allowed_fields}
    name_values = {
        value: [ids for ids in choices if name_block_ids.intersection(ids)] for value, choices in values.items()
    }
    if any(name_values.values()):
        values = defaultdict(list, {key: value for key, value in name_values.items() if value})
    atomic_candidates = tuple(
        (value, block_ids)
        for value, choices in values.items()
        for block_ids in choices
        if _slash_strength_components(value)
    )
    filtered_values: dict[str, tuple[tuple[str, ...], ...]] = {}
    for value, choices in values.items():
        remaining = tuple(
            block_ids
            for block_ids in choices
            if not _is_component_subset_of_atomic_strength(
                value,
                block_ids,
                atomic_candidates,
            )
        )
        if remaining:
            filtered_values[value] = remaining
    return _CandidateSet(
        {key: tuple(sorted(set(choices), key=lambda ids: (len(ids), ids))) for key, choices in filtered_values.items()}
    )


def _normalized_strength(value: str) -> str:
    return "".join(value.casefold().split())


_SLASH_LINKED_STRENGTH_PATTERN = re.compile(r"^(?P<amounts>\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)+)(?P<unit>[^\d/]+)$")


def _slash_strength_components(value: str) -> frozenset[str]:
    normalized = _normalized_strength(value)
    match = _SLASH_LINKED_STRENGTH_PATTERN.fullmatch(normalized)
    if match is None or parse_strength(normalized) != normalized:
        return frozenset()
    unit = match.group("unit")
    return frozenset(f"{amount}{unit}" for amount in match.group("amounts").split("/"))


def _is_component_subset_of_atomic_strength(
    value: str,
    block_ids: tuple[str, ...],
    atomic_candidates: tuple[tuple[str, tuple[str, ...]], ...],
) -> bool:
    candidate_ids = frozenset(block_ids)
    return any(
        candidate_ids < frozenset(atomic_ids) and value in _slash_strength_components(atomic_value)
        for atomic_value, atomic_ids in atomic_candidates
    )


def _grounded_field(field: MedicationField) -> GroundedField:
    issues = (
        (GroundingIssueCode.INVALID_FIELD_VALUE,)
        if any(issue in _FIELD_VALIDATION_ISSUES for issue in field.issues)
        else ()
    )
    return GroundedField(
        value=field.value,
        source_text=field.source_text,
        block_ids=field.block_ids,
        rejected_block_ids=(),
        bbox=field.bbox,
        confidence=field.confidence,
        issues=issues,
    )


_FIELD_VALIDATION_ISSUES = frozenset(
    {
        MedicationIssueCode.INVALID_FIELD_VALUE,
        MedicationIssueCode.INVALID_POSITIVE_INTEGER,
        MedicationIssueCode.UNREPRESENTABLE_POSITIVE_INTEGER,
        MedicationIssueCode.INVALID_BLOCK_GEOMETRY,
    }
)


def _missing_grounded_field() -> GroundedField:
    return GroundedField(None, "", (), (), None, None, ())


def _has_issue(
    issues: list[GroundingIssue],
    field: str,
    row_id: str | None,
) -> bool:
    return any(issue.field == field and issue.row_id == row_id for issue in issues)


def _evidence_key(block: EvidenceBlock) -> tuple[float, float, str]:
    return block.bbox.y_min, block.bbox.x_min, block.block_id


def _deduplicate_issues(issues: list[GroundingIssue]) -> tuple[GroundingIssue, ...]:
    return tuple({(issue.code, issue.field, issue.block_ids, issue.row_id): issue for issue in issues}.values())
