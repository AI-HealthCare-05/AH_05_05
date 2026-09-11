"""Fail-closed plain-language projection for already validated v11 cards."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_worker.llm.prompts.prompt_assets import load_prompt_asset
from ai_worker.schemas.intake_report_cards import IntakeReportCards, OriginalCardText

_MAX_FIELDS = 80
_MAX_CHARACTERS = 45_000
_REGISTERED_INTAKE_LABEL = re.compile(r"등록.*복용|복용.*등록")
_HTML_ENTITY = r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);"
_NUMBER = r"[+-]?\d+(?:[.,]\d+)*"
_UNIT = r"(?:mg|mcg|μg|µg|㎍|g|mL|ml|L|IU|mEq|mmol|kcal|%|정|캡슐|포|회|번|일|시간|분|세|개월|년)"
_COMPOSITE_NUMBER = rf"{_NUMBER}(?:\s*[/：:]\s*{_NUMBER})+(?:\s*{_UNIT})?"
_PROTECTED_TOKEN = re.compile(
    rf"{_HTML_ENTITY}|{_COMPOSITE_NUMBER}|(?:<=|>=|≤|≥|<|>|±)\s*{_NUMBER}(?:\s*{_UNIT})?|{_NUMBER}(?:\s*{_UNIT})?|(?:<=|>=|≤|≥|<|>|±|~|–)",
    re.IGNORECASE,
)
_NEW_MARKUP_OR_LINK = re.compile(
    r"https?://|www\.|\[[^\]\n]+\]\([^\)\n]+\)|```|(?:^|\n)\s{0,3}#{1,6}\s|"
    r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+|\*\*|__|</?[A-Za-z][^>]*>",
    re.IGNORECASE,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PlainLanguageEdit(_StrictModel):
    key: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=8_000)


class PlainLanguageEdits(_StrictModel):
    edits: list[PlainLanguageEdit]


class PlainLanguageReviewItem(_StrictModel):
    key: str = Field(min_length=1)
    faithful: bool
    complete: bool
    no_new_claims: bool


class PlainLanguageReview(_StrictModel):
    reviews: list[PlainLanguageReviewItem]


class AsyncPlainLanguageClient(Protocol):
    async def ainvoke(self, messages: Any) -> BaseModel | dict[str, Any]: ...


@dataclass(frozen=True)
class _NarrativeField:
    key: str
    label: str
    text: str
    source_ids: tuple[str, ...]
    path: tuple[str | int, ...]
    kind: str
    writer_key: str


def _writer_identity(kind: str, text: str, key: str) -> tuple[str, str]:
    return (kind, text) if kind == "action" else ("key", key)


def _collect_fields(cards: IntakeReportCards) -> list[_NarrativeField]:  # noqa: C901 - card traversal stays explicit
    fields: list[_NarrativeField] = []
    shared_actions: dict[tuple[str, str], str] = {}

    def add(
        *,
        key: str,
        label: str,
        text: str,
        source_ids: list[str],
        path: tuple[str | int, ...],
        kind: str,
    ) -> None:
        if not text.strip() or _REGISTERED_INTAKE_LABEL.search(label):
            return
        identity = _writer_identity(kind, text, key)
        writer_key = shared_actions.setdefault(identity, key)
        fields.append(_NarrativeField(key, label, text, tuple(source_ids), path, kind, writer_key))

    for medication_index, medication in enumerate(cards.medications):
        for field_name, korean_label in (
            ("efficacy", "효능"),
            ("caution", "주의"),
            ("contraindication", "복용 금지"),
        ):
            section = getattr(medication, field_name)
            add(
                key=f"medication:{medication.item_id}:{field_name}",
                label=f"{medication.product_name} · {korean_label}",
                text=section.text,
                source_ids=section.source_ids,
                path=("medications", medication_index, field_name, "text"),
                kind=field_name,
            )
        for detail_index, detail in enumerate(medication.details):
            add(
                key=f"medication:{medication.item_id}:detail:{detail_index}",
                label=f"{medication.product_name} · {detail.label}",
                text=detail.text,
                source_ids=detail.source_ids,
                path=("medications", medication_index, "details", detail_index, "text"),
                kind="detail",
            )

    for collection_name, cards_in_collection in (
        ("interactions", cards.interactions),
        ("overlaps", cards.overlaps),
        ("lifestyle", cards.lifestyle),
    ):
        scope = collection_name.removesuffix("s")
        for card_index, card in enumerate(cards_in_collection):
            identity = getattr(card, "id", None) or str(card_index)
            for field_name, korean_label in (("summary", "요약"), ("action", "확인할 일")):
                add(
                    key=f"{scope}:{identity}:{field_name}",
                    label=f"{card.title} · {korean_label}",
                    text=getattr(card, field_name),
                    source_ids=card.source_ids,
                    path=(collection_name, card_index, field_name),
                    kind=field_name,
                )
    return fields


def _exact_key_map(items: list[Any], expected: set[str]) -> dict[str, Any] | None:
    keys = [item.key for item in items]
    if len(keys) != len(expected) or set(keys) != expected:
        return None
    return dict(zip(keys, items, strict=True))


def _protected_tokens(text: str) -> Counter[str]:
    return Counter(re.sub(r"\s+", "", match.group()) for match in _PROTECTED_TOKEN.finditer(text))


def _passes_deterministic_guard(original: str, candidate: str) -> bool:
    stripped = candidate.strip()
    if not stripped or _NEW_MARKUP_OR_LINK.search(stripped):
        return False
    return _protected_tokens(original) == _protected_tokens(stripped)


def _set_path(payload: dict[str, Any], path: tuple[str | int, ...], value: str) -> None:
    target: Any = payload
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value


class PlainLanguageRefiner:
    """Rewrite narrative display fields only after an independent, fail-closed review."""

    def __init__(
        self,
        *,
        writer: AsyncPlainLanguageClient,
        reviewer: AsyncPlainLanguageClient,
        timeout_seconds: float = 25,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("쉬운 문구 생성 제한 시간은 양수여야 합니다.")
        self._writer = writer
        self._reviewer = reviewer
        self._timeout_seconds = timeout_seconds

    async def refine(self, cards: IntakeReportCards) -> IntakeReportCards:
        if cards.original_texts:
            return cards
        fields = _collect_fields(cards)
        if not fields or len(fields) > _MAX_FIELDS or sum(len(field.text) for field in fields) > _MAX_CHARACTERS:
            return cards
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._refine(cards, fields)
        except (TimeoutError, ValidationError, ValueError, TypeError, KeyError, AttributeError):
            return cards
        except Exception:
            return cards

    async def _refine(  # noqa: C901 - one linear fail-closed writer/reviewer boundary
        self,
        cards: IntakeReportCards,
        fields: list[_NarrativeField],
    ) -> IntakeReportCards:
        writer_fields: dict[str, _NarrativeField] = {}
        for field in fields:
            writer_fields.setdefault(field.writer_key, field)
        writer_payload = {
            "fields": [
                {"key": key, "label": field.label, "kind": field.kind, "text": field.text}
                for key, field in writer_fields.items()
            ]
        }
        raw_edits = await self._writer.ainvoke(
            [
                SystemMessage(content=load_prompt_asset("intake_report_plain_language.md")),
                HumanMessage(content=json.dumps(writer_payload, ensure_ascii=False, separators=(",", ":"))),
            ]
        )
        edits = raw_edits if isinstance(raw_edits, PlainLanguageEdits) else PlainLanguageEdits.model_validate(raw_edits)
        edits_by_key = _exact_key_map(edits.edits, set(writer_fields))
        if edits_by_key is None:
            return cards

        candidates = {field.key: edits_by_key[field.writer_key].text.strip() for field in fields}
        review_payload = {
            "fields": [
                {
                    "key": field.key,
                    "label": field.label,
                    "kind": field.kind,
                    "originalText": field.text,
                    "candidateText": candidates[field.key],
                }
                for field in fields
            ]
        }
        raw_review = await self._reviewer.ainvoke(
            [
                SystemMessage(content=load_prompt_asset("intake_report_plain_language_review.md")),
                HumanMessage(content=json.dumps(review_payload, ensure_ascii=False, separators=(",", ":"))),
            ]
        )
        review = (
            raw_review
            if isinstance(raw_review, PlainLanguageReview)
            else PlainLanguageReview.model_validate(raw_review)
        )
        reviews_by_key = _exact_key_map(review.reviews, {field.key for field in fields})
        if reviews_by_key is None:
            return cards

        accepted: dict[str, bool] = {}
        for field in fields:
            decision = reviews_by_key[field.key]
            accepted[field.key] = (
                decision.faithful
                and decision.complete
                and decision.no_new_claims
                and _passes_deterministic_guard(field.text, candidates[field.key])
            )
        action_groups: dict[tuple[str, str], list[_NarrativeField]] = {}
        for field in fields:
            if field.kind == "action":
                action_groups.setdefault((field.kind, field.text), []).append(field)
        for group in action_groups.values():
            group_is_accepted = all(accepted[field.key] for field in group)
            for field in group:
                accepted[field.key] = group_is_accepted

        payload = cards.model_dump(mode="python")
        originals = list(cards.original_texts)
        for field in fields:
            candidate = candidates[field.key]
            if not accepted[field.key] or candidate == field.text:
                continue
            _set_path(payload, field.path, candidate)
            originals.append(
                OriginalCardText(
                    key=field.key,
                    label=field.label,
                    text=field.text,
                    source_ids=list(field.source_ids),
                )
            )
        payload["original_texts"] = originals
        return IntakeReportCards.model_validate(payload)


__all__ = ["PlainLanguageEdits", "PlainLanguageReview", "PlainLanguageRefiner"]
