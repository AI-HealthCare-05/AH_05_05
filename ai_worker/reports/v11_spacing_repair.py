"""Lossless, field-scoped whitespace repair after strict plan-structure validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ai_worker.reports.v11_cards import (
    V11EvidenceCatalog,
    _collect_text_issues,
    _compact_text,
    _fact_index,
    _project_near_match_whitespace,
    _text_issue,
    _validate_plan_structure,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCardsPlan

_PROTECTED = re.compile(r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);|[0-9]+(?:[.,:/][0-9]+)*[A-Za-z%]*")
_SEPARATOR = re.compile(r"[,;.!?。]\s*|\s+")


class SpacingChunkRepair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    key: str = Field(min_length=1)
    chunks: list[str] = Field(min_length=1)


class SpacingRepairResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    repairs: list[SpacingChunkRepair] = Field(default_factory=list)


def _split_chunks(text: str) -> list[str] | None:
    if not text or len(text) > 4_000:
        return None
    protected = {index for match in _PROTECTED.finditer(text) for index in range(match.start() + 1, match.end())}
    separators = [match.end() for match in _SEPARATOR.finditer(text) if match.end() not in protected]
    hangul = [
        index
        for index in range(1, len(text))
        if "가" <= text[index - 1] <= "힣" and "가" <= text[index] <= "힣" and index not in protected
    ]
    chunks: list[str] = []
    position = 0
    while len(text) - position > 100:
        boundary = next((index for index in reversed(separators) if position < index <= position + 100), None)
        if boundary is None:
            boundary = next((index for index in reversed(hangul) if position < index <= position + 100), None)
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
        for index, selection in enumerate(selections):
            canonical = by_id[selection.card_id].summary
            key = (scope, selection.card_id, _compact_text(canonical))
            yield (field_name, index, "summary_text"), key, canonical


class SpacingRepairRequest:
    def __init__(self, plan: IntakeReportCardsPlan, catalog: V11EvidenceCatalog, fields: list[_SpacingField]) -> None:
        self._plan = plan
        self._catalog = catalog
        self._fields = fields

    def payload(self) -> list[dict[str, Any]]:
        return [{"key": field.key, "chunks": list(field.chunks)} for field in self._fields]

    def apply(self, response: SpacingRepairResponse | dict[str, Any]) -> IntakeReportCardsPlan:
        parsed = (
            response if isinstance(response, SpacingRepairResponse) else SpacingRepairResponse.model_validate(response)
        )
        repairs = {repair.key: repair for repair in parsed.repairs}
        if len(repairs) != len(parsed.repairs) or set(repairs) != {field.key for field in self._fields}:
            raise ValueError("SPACING_REPAIR_COVERAGE: keys must match exactly once")
        raw = self._plan.model_dump(mode="python")
        facts = _fact_index(self._catalog)
        for field in self._fields:
            chunks = repairs[field.key].chunks
            if len(chunks) != len(field.chunks) or any(
                len(proposed) > len(original) + 200 or _project_near_match_whitespace(proposed, original) is None
                for proposed, original in zip(chunks, field.chunks, strict=True)
            ):
                raise ValueError("SPACING_REPAIR_CHUNKS: chunk count, order and characters must be preserved")
            proposal = "".join(chunks)
            if len(proposal) > len(field.canonical) + 2_000:
                raise ValueError("SPACING_REPAIR_INVALID: excess whitespace")
            # Reuse the existing whole-field budget; never add per-chunk mutation allowances.
            joined = _project_near_match_whitespace(proposal, field.canonical)
            if joined is None:
                raise ValueError("SPACING_REPAIR_INVALID: proposal cannot safely map to canonical characters")
            if _text_issue(selected_text=joined, canonical_text=field.canonical, locator=field.key, key=field.plan_key):
                raise ValueError("SPACING_REPAIR_INVALID: full text must pass unchanged safety guards")
            if field.path[0] == "medications" and field.path[2] == "detail_texts":
                index = field.path[1]
                if not raw["medications"][index]["detail_texts"]:
                    raw["medications"][index]["detail_texts"] = [
                        facts[eid].text for eid in self._plan.medications[index].detail_ids
                    ]
            target = raw
            for part in field.path[:-1]:
                target = target[part]
            target[field.path[-1]] = joined
        return IntakeReportCardsPlan.model_validate(raw)


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
