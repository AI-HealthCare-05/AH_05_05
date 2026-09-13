"""Lossless, field-scoped whitespace repair after strict plan-structure validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ai_worker.reports.v11_cards import (
    V11EvidenceCatalog,
    _collect_text_issues,
    _compact_text,
    _fact_index,
    _text_issue,
    _validate_plan_structure,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCardsPlan

_PROTECTED = re.compile(r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);|[0-9]+(?:[.,:/][0-9]+)*[A-Za-z%]*")
_SEPARATOR = re.compile(r"[,;.!?。]\s*|\s+")
_SAFETY_WORD = re.compile(r"금지|금기|하지|마십시오|마세요|아니")
_MAX_CHUNK_SOURCE_CHARACTERS = 100
_MAX_BATCH_SOURCE_CHARACTERS = 800


class SpacingChunkPositions(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    index: StrictInt = Field(ge=0)
    space_after: list[StrictInt] = Field(alias="spaceAfter")


class SpacingChunkRepair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str = Field(min_length=1)
    chunks: list[SpacingChunkPositions] = Field(min_length=1)


class SpacingRepairResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    repairs: list[SpacingChunkRepair] = Field(default_factory=list)


class SpacingProposalMutationError(ValueError):
    """A whitespace proposal changed source characters and cannot be projected."""


def project_spacing_proposals(fields: list[dict[str, Any]], proposals: dict[str, str]) -> dict[str, Any]:
    """Extract positions only after exact character equality; never use model prose."""
    repairs = []
    for field_index, field in enumerate(fields):
        original = "".join(chunk["text"] for chunk in field["chunks"])
        proposed = proposals[f"f{field_index}"]
        original_compact = re.sub(r"\s", "", original)
        proposed_compact = re.sub(r"\s", "", proposed)
        if proposed_compact != original_compact:
            raise SpacingProposalMutationError("SPACING_PROPOSAL_MUTATION: preserve every non-whitespace character")
        proposed_boundaries: set[int] = set()
        compact_offset = 0
        for character in proposed:
            if character.isspace():
                proposed_boundaries.add(compact_offset)
            else:
                compact_offset += 1
        allowed = {
            start + offset
            for start, chunk in _chunk_starts(field["chunks"])
            for offset in chunk.get("allowedSpaceAfter", [])
        } or _allowed_boundaries(original)
        selected: set[int] = set()
        compact_offset = 0
        for offset, character in enumerate(original, 1):
            if not character.isspace():
                compact_offset += 1
            if offset in allowed and compact_offset in proposed_boundaries:
                selected.add(offset)
        chunks = []
        start = 0
        for chunk in field["chunks"]:
            end = start + len(chunk["text"])
            chunks.append(
                {"index": chunk["index"], "spaceAfter": sorted(i - start for i in selected if start < i <= end)}
            )
            start = end
        repairs.append({"key": field["key"], "chunks": chunks})
    return {"repairs": repairs}


def _chunk_starts(chunks: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    start = 0
    indexed = []
    for chunk in chunks:
        indexed.append((start, chunk))
        start += len(chunk["text"])
    return indexed


def _reject_excessive_spacing(original: str, selected: set[int]) -> None:
    reconstructed = "".join(
        character + (" " if offset in selected else "") for offset, character in enumerate(original, 1)
    )
    for run in re.finditer(r"(?<![가-힣])(?:[가-힣] ){5,}[가-힣](?![가-힣])", reconstructed):
        if run.group() not in original:
            raise ValueError("SPACING_REPAIR_EXCESSIVE: do not split a local word into syllables")
    allowed = _allowed_boundaries(original)
    # Measure across chunk boundaries. A long prose run with almost every
    # eligible boundary selected is syllable splitting, not Korean spacing.
    for run in re.finditer(r"[가-힣]{18,}", original):
        eligible = allowed.intersection(range(run.start() + 1, run.end()))
        if eligible and len(selected & eligible) * 100 >= len(eligible) * 85:
            raise ValueError("SPACING_REPAIR_EXCESSIVE: do not split words into syllables")


def _allowed_boundaries(text: str) -> set[int]:
    # Only insertion between Korean syllables is allowed. Existing whitespace,
    # numbers, units, punctuation and encoded entities remain byte-for-byte intact.
    protected = {index for match in _SAFETY_WORD.finditer(text) for index in range(match.start() + 1, match.end())}
    return {
        index
        for index in range(1, len(text))
        if index not in protected and all("가" <= ch <= "힣" for ch in text[index - 1 : index + 1])
    }


def source_spacing_pattern(text: str) -> str:
    """Constrain model decoding to the original characters and eligible spaces."""
    allowed = _allowed_boundaries(text)
    return (
        "^"
        + "".join(
            re.escape(character) + (" ?" if offset in allowed else "") for offset, character in enumerate(text, 1)
        )
        + "$"
    )


def payload_spacing_pattern(chunks: list[dict[str, Any]]) -> str:
    """Allow only server-approved positions, including a safe batch seam."""
    allowed = {
        start + offset for start, chunk in _chunk_starts(chunks) for offset in chunk.get("allowedSpaceAfter", [])
    }
    text = "".join(chunk["text"] for chunk in chunks)
    return (
        "^"
        + "".join(
            re.escape(character) + (" ?" if offset in allowed else "") for offset, character in enumerate(text, 1)
        )
        + "$"
    )


def _split_chunks(text: str) -> list[str] | None:
    if not text:
        return None
    protected = {index for match in _PROTECTED.finditer(text) for index in range(match.start() + 1, match.end())}
    separators = {match.end() for match in _SEPARATOR.finditer(text) if match.end() not in protected}
    hangul = {
        index
        for index in range(1, len(text))
        if "가" <= text[index - 1] <= "힣" and "가" <= text[index] <= "힣" and index not in protected
    }
    chunks: list[str] = []
    position = 0
    while len(text) - position > _MAX_CHUNK_SOURCE_CHARACTERS:
        limit = position + _MAX_CHUNK_SOURCE_CHARACTERS
        boundary = next((index for index in range(limit, position, -1) if index in separators), None)
        if boundary is None:
            boundary = next((index for index in range(limit, position, -1) if index in hangul), None)
        if boundary is None:
            return None
        chunks.append(text[position:boundary])
        position = boundary
    chunks.append(text[position:])
    return chunks


@dataclass(frozen=True)
class _SpacingField:
    path: tuple[str | int, ...]
    plan_key: tuple[str, ...]
    canonical: str
    chunks: list[str]

    @property
    def key(self) -> str:
        return "/".join(str(part) for part in self.path)


def _text_fields(plan: IntakeReportCardsPlan, catalog: V11EvidenceCatalog):
    facts = _fact_index(catalog)
    key: tuple[str, ...]
    for index, selection in enumerate(plan.medications):
        for category in ("efficacy", "caution", "contraindication"):
            section = getattr(selection, category)
            canonical = " ".join(facts[eid].text for eid in section.evidence_ids)
            key = (
                "medication",
                str(selection.item_id),
                category,
                ",".join(section.evidence_ids),
                _compact_text(canonical),
            )
            yield ("medications", index, category, "text"), key, canonical
        for detail_index, evidence_id in enumerate(selection.detail_ids):
            canonical = facts[evidence_id].text
            key = (
                "medication-detail",
                str(selection.item_id),
                str(detail_index),
                evidence_id,
                _compact_text(canonical),
            )
            yield ("medications", index, "detail_texts", detail_index), key, canonical
    for scope, field_name, selections, cards in (
        ("interaction", "interactions", plan.interactions, catalog.interactions),
        ("lifestyle", "lifestyle", plan.lifestyle, catalog.lifestyle),
    ):
        by_id = {card.card_id: card for card in cards}
        for index, card_selection in enumerate(selections):
            canonical = by_id[card_selection.card_id].summary
            key = (scope, card_selection.card_id, _compact_text(canonical))
            yield (field_name, index, "summary_text"), key, canonical


class SpacingRepairRequest:
    def __init__(self, plan: IntakeReportCardsPlan, catalog: V11EvidenceCatalog, fields: list[_SpacingField]) -> None:
        self._plan = plan
        self._catalog = catalog
        self._fields = fields

    def _all_batch(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (field_index, chunk_index)
            for field_index, field in enumerate(self._fields)
            for chunk_index in range(len(field.chunks))
        )

    def batches(self) -> list[tuple[tuple[int, int], ...]]:
        """Return source-bounded, ordered work units without dropping a chunk."""
        batches: list[tuple[tuple[int, int], ...]] = []
        current: list[tuple[int, int]] = []
        current_size = 0
        for field_index, field in enumerate(self._fields):
            for chunk_index, chunk in enumerate(field.chunks):
                chunk_size = len(chunk)
                if chunk_size > _MAX_BATCH_SOURCE_CHARACTERS:
                    raise ValueError("SPACING_REPAIR_CHUNK_SIZE: source chunk exceeds batch bound")
                if current and current_size + chunk_size > _MAX_BATCH_SOURCE_CHARACTERS:
                    batches.append(tuple(current))
                    current = []
                    current_size = 0
                current.append((field_index, chunk_index))
                current_size += chunk_size
        if current:
            batches.append(tuple(current))
        return batches

    def _selected_chunk_indexes(self, batch: tuple[tuple[int, int], ...] | None) -> dict[int, list[int]]:
        if batch is None:
            batch = self._all_batch()
        selected: dict[int, list[int]] = {}
        for field_index, chunk_index in batch:
            if not 0 <= field_index < len(self._fields) or not 0 <= chunk_index < len(self._fields[field_index].chunks):
                raise ValueError("SPACING_REPAIR_BATCH: unknown source chunk")
            selected.setdefault(field_index, []).append(chunk_index)
        if not selected or any(indexes != sorted(set(indexes)) for indexes in selected.values()):
            raise ValueError("SPACING_REPAIR_BATCH: source chunks must be distinct and ordered")
        return selected

    def payload(self, batch: tuple[tuple[int, int], ...] | None = None) -> list[dict[str, Any]]:
        selected_by_field = self._selected_chunk_indexes(batch)
        fields = []
        for field_index, field in enumerate(self._fields):
            selected_indexes = selected_by_field.get(field_index)
            if selected_indexes is None:
                continue
            chunks = []
            boundaries = _allowed_boundaries(field.canonical)
            start = 0
            for index, chunk in enumerate(field.chunks):
                if index not in selected_indexes:
                    start += len(chunk)
                    continue
                # Global eligibility also protects words that straddle two chunks.
                allowed = {offset - start for offset in boundaries if start < offset <= start + len(chunk)}
                marked = "".join(
                    character + (f"⟦{offset}⟧" if offset in allowed else "")
                    for offset, character in enumerate(chunk, 1)
                )
                chunks.append(
                    {
                        "index": index,
                        "selectionKey": f"f{field_index}_c{index}",
                        "text": chunk,
                        "markedText": marked,
                        "allowedSpaceAfter": sorted(allowed),
                    }
                )
                start += len(chunk)
            fields.append({"key": field.key, "chunks": chunks})
        return fields

    def validate_batch_response(
        self,
        batch: tuple[tuple[int, int], ...],
        response: SpacingRepairResponse | dict[str, Any],
    ) -> list[dict[int, set[int]]]:
        parsed = (
            response if isinstance(response, SpacingRepairResponse) else SpacingRepairResponse.model_validate(response)
        )
        repairs = {repair.key: repair for repair in parsed.repairs}
        selected_by_field = self._selected_chunk_indexes(batch)
        expected_fields = {self._fields[field_index].key for field_index in selected_by_field}
        if len(repairs) != len(parsed.repairs) or set(repairs) != expected_fields:
            raise ValueError("SPACING_REPAIR_COVERAGE: keys must match exactly once")
        selected_positions: list[dict[int, set[int]]] = [dict() for _ in self._fields]
        payload_by_key = {entry["key"]: entry for entry in self.payload(batch)}
        for field_index, indexes in selected_by_field.items():
            field = self._fields[field_index]
            chunks = repairs[field.key].chunks
            if [chunk.index for chunk in chunks] != indexes:
                raise ValueError("SPACING_REPAIR_CHUNKS: chunk indexes must match in order exactly once")
            for positions, supplied in zip(chunks, payload_by_key[field.key]["chunks"], strict=True):
                selected = set(positions.space_after)
                if len(selected) != len(positions.space_after) or not selected <= set(supplied["allowedSpaceAfter"]):
                    raise ValueError("SPACING_REPAIR_INVALID: choose distinct allowedSpaceAfter positions only")
                selected_positions[field_index][positions.index] = selected
        return selected_positions

    def _combined_selected_positions(
        self, batch_responses: list[tuple[tuple[tuple[int, int], ...], SpacingRepairResponse | dict[str, Any]]]
    ) -> list[dict[int, set[int]]]:
        selected_positions: list[dict[int, set[int]]] = [dict() for _ in self._fields]
        for batch, response in batch_responses:
            validated = self.validate_batch_response(batch, response)
            for field_index, field_positions in enumerate(validated):
                for chunk_index, positions in field_positions.items():
                    if chunk_index in selected_positions[field_index]:
                        raise ValueError("SPACING_REPAIR_COVERAGE: source chunks must be returned exactly once")
                    selected_positions[field_index][chunk_index] = positions
        if any(
            set(positions) != set(range(len(field.chunks)))
            for positions, field in zip(selected_positions, self._fields, strict=True)
        ):
            raise ValueError("SPACING_REPAIR_COVERAGE: source chunks must be returned exactly once")
        return selected_positions

    def _joined_field_texts(self, selected_positions: list[dict[int, set[int]]]) -> list[str]:
        return [
            self._joined_field_text(field, positions_by_chunk)
            for field, positions_by_chunk in zip(self._fields, selected_positions, strict=True)
        ]

    @staticmethod
    def _joined_field_text(field: _SpacingField, positions_by_chunk: dict[int, set[int]]) -> str:
        reconstructed = []
        global_selected: set[int] = set()
        start = 0
        for chunk_index, original in enumerate(field.chunks):
            selected = positions_by_chunk[chunk_index]
            global_selected.update(start + offset for offset in selected)
            start += len(original)
            reconstructed.append(
                "".join(character + (" " if offset in selected else "") for offset, character in enumerate(original, 1))
            )
        joined = "".join(reconstructed)
        _reject_excessive_spacing(field.canonical, global_selected)
        if _text_issue(selected_text=joined, canonical_text=field.canonical, locator=field.key, key=field.plan_key):
            raise ValueError(f"SPACING_REPAIR_INVALID: {field.key}")
        return joined

    def invalid_field_indexes(
        self, batch_responses: list[tuple[tuple[tuple[int, int], ...], SpacingRepairResponse | dict[str, Any]]]
    ) -> set[int]:
        selected_positions = self._combined_selected_positions(batch_responses)
        invalid = set()
        for field_index, field in enumerate(self._fields):
            try:
                self._joined_field_text(field, selected_positions[field_index])
            except (KeyError, ValueError):
                invalid.add(field_index)
        return invalid

    def apply_batches(
        self, batch_responses: list[tuple[tuple[tuple[int, int], ...], SpacingRepairResponse | dict[str, Any]]]
    ) -> IntakeReportCardsPlan:
        selected_positions = self._combined_selected_positions(batch_responses)
        joined_texts = self._joined_field_texts(selected_positions)
        raw = self._plan.model_dump(mode="python")
        facts = _fact_index(self._catalog)
        for field, joined in zip(self._fields, joined_texts, strict=True):
            if field.path[0] == "medications" and field.path[2] == "detail_texts":
                index = field.path[1]
                assert isinstance(index, int)
                if not raw["medications"][index]["detail_texts"]:
                    raw["medications"][index]["detail_texts"] = [
                        facts[eid].text for eid in self._plan.medications[index].detail_ids
                    ]
            target: Any = raw
            for part in field.path[:-1]:
                target = target[part]
            target[field.path[-1]] = joined
        return IntakeReportCardsPlan.model_validate(raw)

    def apply(self, response: SpacingRepairResponse | dict[str, Any]) -> IntakeReportCardsPlan:
        return self.apply_batches([(self._all_batch(), response)])


def prepare_spacing_repair(plan: IntakeReportCardsPlan, catalog: V11EvidenceCatalog) -> SpacingRepairRequest | None:
    _validate_plan_structure(plan, catalog)
    failing = {issue.key for issue in _collect_text_issues(plan, catalog)}
    if not failing:
        return None
    fields = []
    for path, key, canonical in _text_fields(plan, catalog):
        if key not in failing:
            continue
        chunks = _split_chunks(canonical)
        if chunks is None:
            return None
        fields.append(_SpacingField(path, key, canonical, chunks))
    if {field.plan_key for field in fields} != failing:
        raise ValueError("SPACING_REPAIR_COVERAGE: unmapped text issue")
    return SpacingRepairRequest(plan, catalog, fields)
