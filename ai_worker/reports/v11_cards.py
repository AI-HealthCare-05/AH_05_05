"""Evidence catalog, validator and deterministic renderer for v11 report cards.

The model is allowed to order reviewed evidence identifiers.  It cannot create
clinical prose, change a safety category, attach evidence to another product,
or invent citations.  The public cards and email Markdown are projections of
the same validated plan.
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Literal

from ai_worker.reports.v11_lifestyle_guidance import build_lifestyle_guidance_cards
from ai_worker.schemas.intake_report_cards import (
    CardDetail,
    CardSection,
    CardSource,
    IntakeReportCards,
    IntakeReportCardsPlan,
    IntakeReportMedicationSelection,
    InteractionCard,
    LifestyleCard,
    MedicationCard,
    OverlapCard,
)

if TYPE_CHECKING:
    from ai_worker.schemas.intake_report import (
        IntakeReportDraft,
        IntakeReportNutrientTotal,
        IntakeReportSource,
    )


EvidenceCategory = Literal["efficacy", "caution", "contraindication", "detail"]

_BLOCK_SEPARATOR_RE = re.compile(r"\s*(?:\r?\n+|[•●])\s*")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?。])(?!\d)\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_PROJECTION_TEXT_LENGTH = 4_000
_MAX_PROJECTION_WHITESPACE = 2_000
_MIN_PROJECTION_SIMILARITY = 0.97
_MAX_PROJECTION_CHANGED_CHARS = 3
_NUMERIC_TOKEN_PUNCTUATION = frozenset(".,:/%+-")
_CONTRAINDICATION_MARKERS = (
    "금기",
    "복용하지 마",
    "먹지 마",
    "사용하지 마",
    "투여하지 마",
    "해서는 안",
    "하면 안",
    "피해야",
    "금합니다",
    "복용 금지",
    "사용 금지",
)
_COMPACT_CONTRAINDICATION_MARKERS = tuple(_WHITESPACE_RE.sub("", marker) for marker in _CONTRAINDICATION_MARKERS)
_PROMPT_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all instructions",
    "system prompt",
    "reveal prompt",
    "이전 지시",
    "지시를 무시",
    "시스템 프롬프트",
    "시스템 메시지",
    "프롬프트를 출력",
    "비밀 프롬프트",
)
_MISSING_TEXT = {
    "efficacy": "제공된 제품 안내에서 효능 정보를 확인할 수 없습니다.",
    "caution": "제공된 제품 안내에서 주의 정보를 확인할 수 없습니다.",
    "contraindication": "제공된 제품 안내에서 금기 정보를 확인할 수 없습니다.",
}
_CATEGORY_LABELS = {
    "efficacy": "어떤 약인가요?",
    "caution": "주의하세요",
    "contraindication": "먹으면 안 돼요",
}
_EVIDENCE_LEVEL_LABELS = {
    "APPROVED_RULE": "승인된 규칙",
    "PUBLIC_GUIDE": "공개 안내",
    "RESEARCH": "연구 근거",
    "REGISTERED_INTAKE": "등록한 복용 정보",
    "UNVERIFIED": "확인 필요",
}


@dataclass(frozen=True)
class EvidenceFact:
    evidence_id: str
    owner_item_id: int
    category: EvidenceCategory
    label: str
    text: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class MedicationEvidence:
    item_id: int
    product_name: str
    facts: tuple[EvidenceFact, ...]


@dataclass(frozen=True)
class CatalogInteraction:
    card_id: str
    title: str
    summary: str
    action: str
    related_item_ids: tuple[int, ...]
    source_ids: tuple[str, ...]
    evidence_level: str
    action_level: Literal["WARNING", "CHECK", "INFORMATION"]


@dataclass(frozen=True)
class CatalogLifestyle:
    card_id: str
    category: str
    title: str
    summary: str
    action: str
    related_item_ids: tuple[int, ...]
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class V11EvidenceCatalog:
    medications: dict[int, MedicationEvidence]
    interactions: tuple[CatalogInteraction, ...]
    lifestyle: tuple[CatalogLifestyle, ...]
    sources: tuple[CardSource, ...]

    def model_payload(self) -> dict[str, object]:
        """Return only the quoted evidence and IDs needed to construct a plan."""
        return {
            "medications": [
                {
                    "itemId": medication.item_id,
                    "productName": medication.product_name,
                    "canonicalSections": {
                        category: " ".join(fact.text for fact in medication.facts if fact.category == category)
                        for category in ("efficacy", "caution", "contraindication")
                    },
                    "evidence": [
                        {
                            "evidenceId": fact.evidence_id,
                            "category": fact.category,
                            "label": fact.label,
                            "text": fact.text,
                            "sourceIds": list(fact.source_ids),
                        }
                        for fact in medication.facts
                    ],
                }
                for medication in self.medications.values()
            ],
            "interactions": [
                {
                    "cardId": card.card_id,
                    "summary": card.summary,
                    "sourceIds": list(card.source_ids),
                    "actionLevel": card.action_level,
                }
                for card in self.interactions
            ],
            "lifestyle": [
                {
                    "cardId": card.card_id,
                    "summary": card.summary,
                    "sourceIds": list(card.source_ids),
                }
                for card in self.lifestyle
            ],
        }


def _unique(values: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _compact_text(value: str) -> str:
    return _WHITESPACE_RE.sub("", value)


def _whitespace_boundaries(value: str) -> tuple[str, set[int]]:
    compact: list[str] = []
    boundaries: set[int] = set()
    for character in value:
        if character.isspace():
            boundaries.add(len(compact))
        else:
            compact.append(character)
    return "".join(compact), boundaries


def _is_hangul_text(value: str) -> bool:
    return all("가" <= character <= "힣" for character in value)


def _is_intra_token_punctuation(compact: str, index: int) -> bool:
    if compact[index] not in _NUMERIC_TOKEN_PUNCTUATION:
        return False
    before = compact[index - 1] if index else ""
    after = compact[index + 1] if index + 1 < len(compact) else ""
    if compact[index] == ".":
        return before.isascii() and before.isdigit() and after.isascii() and after.isdigit()
    return bool(before) and before.isascii() and before.isalnum()


def _unsafe_new_whitespace_boundary(  # noqa: C901 - protected token rules stay auditable together
    selected: str,
    canonical: str,
) -> bool:
    """Detect new whitespace that splits a protected lexical token."""
    selected_compact, selected_boundaries = _whitespace_boundaries(selected)
    canonical_compact, canonical_boundaries = _whitespace_boundaries(canonical)
    if selected_compact != canonical_compact:
        return False
    new_boundaries = selected_boundaries - canonical_boundaries
    entity_spans = [
        match.span()
        for match in re.finditer(
            r"&(?:#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);",
            canonical_compact,
        )
    ]

    def is_ascii_letter(character: str) -> bool:
        return "A" <= character <= "Z" or "a" <= character <= "z"

    for boundary in new_boundaries:
        if not 0 < boundary < len(canonical_compact):
            continue
        if any(start < boundary < end for start, end in entity_spans):
            return True
        left = canonical_compact[boundary - 1]
        right = canonical_compact[boundary]
        if left.isascii() and left.isdigit() and right.isascii() and right.isdigit():
            return True
        if is_ascii_letter(left) and (is_ascii_letter(right) or right.isdigit()):
            return True
        if left.isdigit() and is_ascii_letter(right):
            start = boundary - 1
            while start > 0 and re.fullmatch(r"[0-9A-Za-z.]", canonical_compact[start - 1]):
                start -= 1
            end = boundary
            while end < len(canonical_compact) and re.fullmatch(r"[0-9A-Za-z.]", canonical_compact[end]):
                end += 1
            token = canonical_compact[start:end]
            match = re.fullmatch(r"(\d+(?:\.\d+)?)([A-Za-z]+)", token)
            if match is None or boundary - start != len(match.group(1)):
                return True
            continue
        if _is_intra_token_punctuation(canonical_compact, boundary - 1) or _is_intra_token_punctuation(
            canonical_compact, boundary
        ):
            token_start = boundary - 1
            while token_start > 0 and re.fullmatch(r"[0-9A-Za-z.,:/%+\-]", canonical_compact[token_start - 1]):
                token_start -= 1
            token_end = boundary
            while token_end < len(canonical_compact) and re.fullmatch(
                r"[0-9A-Za-z.,:/%+\-]", canonical_compact[token_end]
            ):
                token_end += 1
            if any(character.isdigit() for character in canonical_compact[token_start:token_end]):
                return True
    return False


def _project_near_match_whitespace(  # noqa: C901 - all bounded projection guards are co-located
    proposed: str,
    canonical: str,
) -> str | None:
    """Project only safe whitespace boundaries onto canonical source characters."""
    if max(len(proposed), len(canonical)) > _MAX_PROJECTION_TEXT_LENGTH:
        return None
    proposed_compact, proposed_boundaries = _whitespace_boundaries(proposed)
    canonical_compact, canonical_boundaries = _whitespace_boundaries(canonical)
    if len(proposed) - len(proposed_compact) > _MAX_PROJECTION_WHITESPACE:
        return None
    if proposed_compact == canonical_compact:
        return proposed
    decoded_canonical = html.unescape(canonical_compact)
    decoded_proposed = html.unescape(proposed_compact)
    if abs(len(decoded_proposed) - len(decoded_canonical)) > _MAX_PROJECTION_CHANGED_CHARS:
        return None

    matcher = SequenceMatcher(None, canonical_compact, proposed_compact, autojunk=False)
    similarity_matcher = (
        matcher
        if decoded_canonical == canonical_compact and decoded_proposed == proposed_compact
        else SequenceMatcher(None, decoded_canonical, decoded_proposed, autojunk=False)
    )
    similarity = 1.0 if decoded_canonical == decoded_proposed else similarity_matcher.ratio()
    if similarity < _MIN_PROJECTION_SIMILARITY:
        return None
    proposed_to_canonical: dict[int, int] = {}
    total_changed = 0
    for tag, canonical_start, canonical_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(proposed_end - proposed_start + 1):
                proposed_to_canonical[proposed_start + offset] = canonical_start + offset
            continue
        canonical_change = canonical_compact[canonical_start:canonical_end]
        proposed_change = proposed_compact[proposed_start:proposed_end]
        # Equivalent encoding only changes alignment, never the emitted source.
        if canonical_change and html.unescape(canonical_change) == html.unescape(proposed_change):
            continue
        terminal_period = (
            tag == "insert"
            and canonical_start == len(canonical_compact)
            and proposed_end == len(proposed_compact)
            and proposed_change == "."
        )
        if max(len(canonical_change), len(proposed_change)) > _MAX_PROJECTION_CHANGED_CHARS:
            return None
        if not _is_hangul_text(canonical_change + proposed_change) and not terminal_period:
            return None
        total_changed += max(len(canonical_change), len(proposed_change))
        if total_changed > _MAX_PROJECTION_CHANGED_CHARS:
            return None

    projected_boundaries = set(canonical_boundaries)
    for proposed_boundary in proposed_boundaries:
        canonical_boundary = proposed_to_canonical.get(proposed_boundary)
        if canonical_boundary is None or not 0 < canonical_boundary < len(canonical_compact):
            continue
        if _is_hangul_text(canonical_compact[canonical_boundary - 1 : canonical_boundary + 1]):
            projected_boundaries.add(canonical_boundary)

    projected = "".join(
        (" " if index in projected_boundaries else "") + character for index, character in enumerate(canonical_compact)
    ).strip()
    if _compact_text(projected) != canonical_compact:
        raise AssertionError("whitespace projection changed canonical characters")
    return projected


def _needs_korean_spacing(value: str) -> bool:
    return any(len(run) >= 18 for run in re.findall(r"[가-힣]+", value))


def _is_prompt_injection(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _PROMPT_INJECTION_MARKERS)


def _is_truncated(value: str) -> bool:
    stripped = value.rstrip()
    return stripped.endswith(("...", "…", ":", ";", ",")) or stripped.count("(") != stripped.count(")")


def _normalize_source_delimiters(value: str) -> str:
    normalized = value.replace("\u00a0", " ")
    normalized = re.sub(r"(?<=[.!?。])\|+", "", normalized)
    normalized = re.sub(r"(?<=\d)\|(?=\d{3}(?:\D|$))", ",", normalized)
    return normalized.replace("|", ", ")


def _recover_after_malformed_prefix(value: str) -> str | None:
    starts = [value.find(marker, 1) for marker in ("이약을복용하기전에", "이약을사용하기전에")]
    indexes = [index for index in starts if index > 0]
    if not indexes:
        return None
    candidate = value[min(indexes) :].strip()
    return candidate if candidate and not _is_truncated(candidate) else None


def _fragments(value: str) -> tuple[list[str], bool]:
    accepted: list[str] = []
    rejected = False
    normalized = _normalize_source_delimiters(value or "")
    raw_fragments = [
        sentence for block in _BLOCK_SEPARATOR_RE.split(normalized) for sentence in _SENTENCE_BOUNDARY_RE.split(block)
    ]
    for raw_fragment in raw_fragments:
        fragment = re.sub(r"[ \t]+", " ", raw_fragment).strip(" \t\r\n-•●")
        if not fragment:
            continue
        if _is_prompt_injection(fragment):
            rejected = True
            continue
        if _is_truncated(fragment):
            rejected = True
            recovered = _recover_after_malformed_prefix(fragment)
            if recovered is not None and not _is_prompt_injection(recovered):
                accepted.append(recovered)
            continue
        accepted.append(fragment)
    return _unique(accepted), rejected


def _safe_url(value: str | None) -> str | None:
    if value is None:
        return None
    url = value.strip()
    if not url.lower().startswith(("https://", "http://")):
        return None
    return None if re.search(r'[\s\[\]()<>"\']', url) else url


def _external_source_id(source: IntakeReportSource) -> str:
    identity = "\x1f".join(
        (
            source.title,
            source.organization or "",
            source.url or "",
            source.evidence_level.value,
        )
    )
    return "source:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _source_from_review(source: IntakeReportSource) -> CardSource:
    return CardSource(
        id=_external_source_id(source),
        title=source.title,
        organization=source.organization,
        url=_safe_url(source.url),
        evidence_level=source.evidence_level.value,
    )


def _missing_fact(*, item_id: int, category: str, index: int = 1) -> EvidenceFact:
    return EvidenceFact(
        evidence_id=f"med:{item_id}:missing-{category}:{index}",
        owner_item_id=item_id,
        category=category,  # type: ignore[arg-type]
        label=_CATEGORY_LABELS[category],
        text=_MISSING_TEXT[category],
        source_ids=(),
    )


def _medication_evidence(  # noqa: C901 - one pass preserves category/owner invariants together
    draft: IntakeReportDraft,
) -> tuple[dict[int, MedicationEvidence], list[CardSource]]:
    medication_items = [item for item in draft.current_stack if item.item_type.value == "MEDICATION"]
    medication_ids = {item.item_id for item in medication_items}
    if set(draft.guide_item_bindings) - medication_ids:
        raise ValueError("EVIDENCE_BINDING: a guide is bound to an unknown medication")

    guides: dict[int, object] = {}
    for guide in draft.guide_evidence:
        if guide.medication_guide_id in guides:
            if guides[guide.medication_guide_id] != guide:
                raise ValueError("EVIDENCE_BINDING: conflicting duplicate guide identity")
            continue
        guides[guide.medication_guide_id] = guide

    sources: list[CardSource] = []
    medications: dict[int, MedicationEvidence] = {}
    for item in medication_items:
        guide_id = draft.guide_item_bindings.get(item.item_id)
        guide = guides.get(guide_id) if guide_id is not None else None
        source_ids: tuple[str, ...] = ()
        if guide is not None:
            source_id = f"guide:{guide.medication_guide_id}"
            source_ids = (source_id,)
            sources.append(
                CardSource(
                    id=source_id,
                    title=f"{item.product_name} 제품 안내",
                    organization=guide.manufacturer_name,
                    evidence_level="PUBLIC_GUIDE",
                )
            )

        facts: list[EvidenceFact] = []
        if guide is not None:
            efficacy_fragments, efficacy_rejected = _fragments(guide.efficacy)
        else:
            efficacy_fragments, efficacy_rejected = [], False
        for index, text in enumerate(efficacy_fragments, start=1):
            facts.append(
                EvidenceFact(
                    evidence_id=f"med:{item.item_id}:efficacy:{index}",
                    owner_item_id=item.item_id,
                    category="efficacy",
                    label=_CATEGORY_LABELS["efficacy"],
                    text=text,
                    source_ids=source_ids,
                )
            )
        if not efficacy_fragments or efficacy_rejected:
            facts.append(_missing_fact(item_id=item.item_id, category="efficacy"))

        safety_fragments: list[tuple[str, str]] = []
        safety_rejected = False
        if guide is not None:
            for field_name, raw_value in (
                ("pre-use-warning", guide.pre_use_warning),
                ("precautions", guide.precautions),
            ):
                fragments, rejected = _fragments(raw_value)
                safety_rejected = safety_rejected or rejected
                safety_fragments.extend((field_name, fragment) for fragment in fragments)
        seen_safety: set[tuple[str, str]] = set()
        field_indexes: dict[str, int] = {}
        for field_name, text in safety_fragments:
            compact_text = _compact_text(text)
            category = (
                "contraindication"
                if any(marker in compact_text for marker in _COMPACT_CONTRAINDICATION_MARKERS)
                else "caution"
            )
            if (category, text) in seen_safety:
                continue
            seen_safety.add((category, text))
            field_indexes[field_name] = field_indexes.get(field_name, 0) + 1
            facts.append(
                EvidenceFact(
                    evidence_id=f"med:{item.item_id}:{field_name}:{field_indexes[field_name]}",
                    owner_item_id=item.item_id,
                    category=category,
                    label=_CATEGORY_LABELS[category],
                    text=text,
                    source_ids=source_ids,
                )
            )
        for category in ("caution", "contraindication"):
            if not any(fact.category == category for fact in facts) or safety_rejected:
                facts.append(_missing_fact(item_id=item.item_id, category=category))

        if guide is not None:
            for field_name, label, raw_value in (
                ("usage-instructions", "복용 방법", guide.usage_instructions),
                ("adverse-reactions", "이상 반응", guide.adverse_reactions),
            ):
                detail_fragments, _ = _fragments(raw_value)
                for index, text in enumerate(detail_fragments, start=1):
                    facts.append(
                        EvidenceFact(
                            evidence_id=f"med:{item.item_id}:{field_name}:{index}",
                            owner_item_id=item.item_id,
                            category="detail",
                            label=label,
                            text=text,
                            source_ids=source_ids,
                        )
                    )
        medications[item.item_id] = MedicationEvidence(
            item_id=item.item_id,
            product_name=item.product_name,
            facts=tuple(facts),
        )
    return medications, sources


def _related_item_ids(draft: IntakeReportDraft, names: list[str]) -> tuple[int, ...]:
    exact: dict[str, list[int]] = {}
    for item in draft.current_stack:
        exact.setdefault(item.product_name, []).append(item.item_id)
    return tuple(dict.fromkeys(item_id for name in names for item_id in exact.get(name, [])))


def _interaction_catalog(
    draft: IntakeReportDraft,
    medications: dict[int, MedicationEvidence],
) -> tuple[list[CatalogInteraction], list[CardSource]]:
    from ai_worker.schemas.intake_report import IntakeReportReviewCardType

    interactions: list[CatalogInteraction] = []
    sources: list[CardSource] = []
    for index, review in enumerate(draft.review_cards, start=1):
        if review.card_type != IntakeReportReviewCardType.INTERACTION:
            continue
        review_sources = [_source_from_review(source) for source in review.sources]
        sources.extend(review_sources)
        evidence_level = review.evidence_level.value
        interactions.append(
            CatalogInteraction(
                card_id=f"review-interaction:{index}",
                title=review.title,
                summary=review.summary,
                action=review.check_item,
                related_item_ids=_related_item_ids(draft, review.related_items),
                source_ids=tuple(_unique([source.id for source in review_sources])),
                evidence_level=evidence_level,
                action_level="WARNING" if evidence_level == "APPROVED_RULE" else "CHECK",
            )
        )

    guides = {guide.medication_guide_id: guide for guide in draft.guide_evidence}
    for item_id, medication in medications.items():
        guide_id = draft.guide_item_bindings.get(item_id)
        guide = guides.get(guide_id) if guide_id is not None else None
        if guide is None:
            continue
        fragments, _ = _fragments(guide.drug_food_interactions)
        if not fragments:
            continue
        source_ids = (f"guide:{guide.medication_guide_id}",)
        interactions.append(
            CatalogInteraction(
                card_id=f"guide-interaction:{item_id}",
                title=f"{medication.product_name}의 약·음식 상호작용 안내",
                summary=" ".join(fragments),
                action=(
                    "제품 안내의 일반 정보예요. 등록 목록 안의 특정 병용 조합으로 확인된 것은 "
                    "아니므로, 적용 여부를 전문가에게 확인하세요."
                ),
                related_item_ids=(item_id,),
                source_ids=source_ids,
                evidence_level="PUBLIC_GUIDE",
                action_level="CHECK",
            )
        )
    return interactions, sources


def _lifestyle_catalog(
    draft: IntakeReportDraft,
    medications: dict[int, MedicationEvidence],
) -> list[CatalogLifestyle]:
    lifestyle: list[CatalogLifestyle] = []
    for medication in medications.values():
        driving_facts = [
            fact
            for fact in medication.facts
            if fact.category == "caution" and any(marker in fact.text for marker in ("졸음", "어지러"))
        ]
        if driving_facts:
            lifestyle.append(
                CatalogLifestyle(
                    card_id=f"driving:{medication.item_id}",
                    category="운전",
                    title=f"{medication.product_name} 복용 후 운전 주의",
                    summary=" ".join(fact.text for fact in driving_facts),
                    action="졸리거나 어지러우면 운전하지 마세요.",
                    related_item_ids=(medication.item_id,),
                    source_ids=tuple(_unique([source_id for fact in driving_facts for source_id in fact.source_ids])),
                )
            )

    guides = {guide.medication_guide_id: guide for guide in draft.guide_evidence}
    for medication in medications.values():
        guide_id = draft.guide_item_bindings.get(medication.item_id)
        guide = guides.get(guide_id) if guide_id is not None else None
        if guide is None:
            continue
        interaction_fragments, _ = _fragments(guide.drug_food_interactions)
        scenario_fragments = [
            fragment
            for fragment in interaction_fragments
            if any(marker in fragment for marker in ("술", "알코올", "주스", "자몽", "오렌지", "사과", "음식", "식사"))
        ]
        if scenario_fragments:
            lifestyle.append(
                CatalogLifestyle(
                    card_id=f"food-drink:{medication.item_id}",
                    category="약과 음식·술 주의",
                    title=f"{medication.product_name}과 음식·음료",
                    summary=" ".join(scenario_fragments),
                    action="제품 안내의 조건과 실제 처방·복약 지시를 확인하세요.",
                    related_item_ids=(medication.item_id,),
                    source_ids=(f"guide:{guide.medication_guide_id}",),
                )
            )
    return lifestyle


def build_evidence_catalog(draft: IntakeReportDraft) -> V11EvidenceCatalog:
    """Build a complete, per-registration evidence boundary from a real draft."""
    medications, medication_sources = _medication_evidence(draft)
    interactions, review_sources = _interaction_catalog(draft, medications)
    guidance_cards, guidance_sources = build_lifestyle_guidance_cards(draft)
    lifestyle = [
        *_lifestyle_catalog(draft, medications),
        *(
            CatalogLifestyle(
                card_id=card.id,
                category=card.category,
                title=card.title,
                summary=card.summary,
                action=card.action,
                related_item_ids=tuple(card.related_item_ids),
                source_ids=tuple(card.source_ids),
            )
            for card in guidance_cards
        ),
    ]
    sources_by_id = {source.id: source for source in [*medication_sources, *review_sources, *guidance_sources]}
    return V11EvidenceCatalog(
        medications=medications,
        interactions=tuple(interactions),
        lifestyle=tuple(lifestyle),
        sources=tuple(sources_by_id.values()),
    )


def _require_exact_ids(actual: list[str], expected: list[str], issue: str) -> None:
    if len(actual) != len(expected) or set(actual) != set(expected):
        raise ValueError(f"{issue}: missing, duplicated or unknown identity")


def _fact_index(catalog: V11EvidenceCatalog) -> dict[str, EvidenceFact]:
    return {fact.evidence_id: fact for medication in catalog.medications.values() for fact in medication.facts}


PlanTextKey = tuple[str, ...]
PlanTextCache = dict[PlanTextKey, str]


@dataclass(frozen=True)
class _PlanTextIssue:
    code: str
    locator: str
    key: PlanTextKey

    @property
    def message(self) -> str:
        return f"{self.code}: {self.locator}"


def _text_issue(
    *,
    selected_text: str | None,
    canonical_text: str,
    locator: str,
    key: PlanTextKey,
) -> _PlanTextIssue | None:
    if selected_text is not None and _compact_text(selected_text) != _compact_text(canonical_text):
        return _PlanTextIssue("TEXT_MUTATION", locator, key)
    if selected_text is not None and _unsafe_new_whitespace_boundary(selected_text, canonical_text):
        return _PlanTextIssue("TEXT_UNSAFE_WHITESPACE", locator, key)
    if _needs_korean_spacing(canonical_text) and (selected_text is None or _needs_korean_spacing(selected_text)):
        return _PlanTextIssue("TEXT_SPACING_REQUIRED", locator, key)
    return None


def _validate_card_summary_structure(selection: object, card: object) -> None:
    expected_sources = list(card.source_ids)
    _require_exact_ids(selection.source_ids, expected_sources, "SOURCE_MISMATCH")


def _validate_medication_selection_structure(  # noqa: C901 - validates one fail-closed boundary
    selection: IntakeReportMedicationSelection,
    medication: MedicationEvidence,
    facts_by_id: dict[str, EvidenceFact],
) -> None:
    all_selected_ids: list[str] = []
    for category in ("efficacy", "caution", "contraindication"):
        section = getattr(selection, category)
        for evidence_id in section.evidence_ids:
            fact = facts_by_id.get(evidence_id)
            if fact is None:
                raise ValueError("UNKNOWN_EVIDENCE: evidence ID is not in the catalog")
            if fact.owner_item_id != selection.item_id:
                raise ValueError("EVIDENCE_OWNER: evidence belongs to another medication")
            if fact.category != category:
                raise ValueError("EVIDENCE_CATEGORY: evidence belongs to another safety category")
        expected_ids = [fact.evidence_id for fact in medication.facts if fact.category == category]
        _require_exact_ids(section.evidence_ids, expected_ids, "EVIDENCE_COVERAGE")
        selected_facts = [facts_by_id[evidence_id] for evidence_id in section.evidence_ids]
        expected_sources = _unique([source_id for fact in selected_facts for source_id in fact.source_ids])
        _require_exact_ids(section.source_ids, expected_sources, "SOURCE_MISMATCH")
        all_selected_ids.extend(section.evidence_ids)

    for evidence_id in selection.detail_ids:
        fact = facts_by_id.get(evidence_id)
        if fact is None:
            raise ValueError("UNKNOWN_EVIDENCE: detail ID is not in the catalog")
        if fact.owner_item_id != selection.item_id:
            raise ValueError("EVIDENCE_OWNER: detail belongs to another medication")
        if fact.category != "detail":
            raise ValueError("EVIDENCE_CATEGORY: core safety evidence cannot become a detail")
    expected_detail_ids = [fact.evidence_id for fact in medication.facts if fact.category == "detail"]
    _require_exact_ids(selection.detail_ids, expected_detail_ids, "EVIDENCE_COVERAGE")
    if selection.detail_texts and len(selection.detail_texts) != len(selection.detail_ids):
        raise ValueError("DETAIL_TEXT_COVERAGE: detail text count differs from evidence count")
    all_selected_ids.extend(selection.detail_ids)
    selected_facts = [facts_by_id[evidence_id] for evidence_id in all_selected_ids]
    expected_sources = _unique([source_id for fact in selected_facts for source_id in fact.source_ids])
    _require_exact_ids(selection.source_ids, expected_sources, "SOURCE_MISMATCH")


def _medication_text_issues(
    selection: IntakeReportMedicationSelection,
    medication: MedicationEvidence,
    facts_by_id: dict[str, EvidenceFact],
) -> list[_PlanTextIssue]:
    issues: list[_PlanTextIssue] = []
    for category in ("efficacy", "caution", "contraindication"):
        section = getattr(selection, category)
        canonical_text = " ".join(facts_by_id[evidence_id].text for evidence_id in section.evidence_ids)
        evidence_ids = ",".join(section.evidence_ids)
        locator = f"itemId={selection.item_id} category={category} evidenceIds={evidence_ids}"
        key = (
            "medication",
            str(selection.item_id),
            category,
            evidence_ids,
            _compact_text(canonical_text),
        )
        if section.text is not None and _compact_text(section.text) != key[-1]:
            proposed_compact = _compact_text(section.text)
            restore_ids = [
                evidence_id
                for evidence_id in section.evidence_ids
                if _compact_text(facts_by_id[evidence_id].text) not in proposed_compact
            ]
            if restore_ids:
                locator += f" restoreEvidenceIds={','.join(restore_ids)}"
        if issue := _text_issue(
            selected_text=section.text,
            canonical_text=canonical_text,
            locator=locator,
            key=key,
        ):
            issues.append(issue)
    for index, evidence_id in enumerate(selection.detail_ids):
        canonical_text = facts_by_id[evidence_id].text
        selected_text = selection.detail_texts[index] if selection.detail_texts else None
        locator = f"itemId={selection.item_id} detailIndex={index} evidenceId={evidence_id}"
        key = (
            "medication-detail",
            str(selection.item_id),
            str(index),
            evidence_id,
            _compact_text(canonical_text),
        )
        if issue := _text_issue(
            selected_text=selected_text,
            canonical_text=canonical_text,
            locator=locator,
            key=key,
        ):
            issues.append(issue)
    return issues


def _card_text_issue(*, scope: str, selection: object, card: object) -> _PlanTextIssue | None:
    return _text_issue(
        selected_text=selection.summary_text,
        canonical_text=card.summary,
        locator=f"scope={scope} cardId={selection.card_id}",
        key=(scope, selection.card_id, _compact_text(card.summary)),
    )


def _validate_plan_structure(
    plan: IntakeReportCardsPlan,
    catalog: V11EvidenceCatalog,
) -> None:
    medication_ids = [selection.item_id for selection in plan.medications]
    expected_medication_ids = list(catalog.medications)
    if len(medication_ids) != len(expected_medication_ids) or set(medication_ids) != set(expected_medication_ids):
        raise ValueError("MEDICATION_COVERAGE: missing, duplicated or unknown medication")
    facts_by_id = _fact_index(catalog)
    for selection in plan.medications:
        _validate_medication_selection_structure(
            selection,
            catalog.medications[selection.item_id],
            facts_by_id,
        )

    interactions_by_id = {card.card_id: card for card in catalog.interactions}
    _require_exact_ids(
        [selection.card_id for selection in plan.interactions],
        list(interactions_by_id),
        "INTERACTION_COVERAGE",
    )
    for selection in plan.interactions:
        _validate_card_summary_structure(selection, interactions_by_id[selection.card_id])
    interaction_ranks = {"WARNING": 0, "CHECK": 1, "INFORMATION": 2}
    selected_ranks = [
        interaction_ranks[interactions_by_id[selection.card_id].action_level] for selection in plan.interactions
    ]
    if selected_ranks != sorted(selected_ranks):
        raise ValueError("INTERACTION_ORDER: server-owned warning level must remain first")

    lifestyle_by_id = {card.card_id: card for card in catalog.lifestyle}
    _require_exact_ids(
        [selection.card_id for selection in plan.lifestyle],
        list(lifestyle_by_id),
        "LIFESTYLE_COVERAGE",
    )
    for selection in plan.lifestyle:
        _validate_card_summary_structure(selection, lifestyle_by_id[selection.card_id])


def _collect_text_issues(
    plan: IntakeReportCardsPlan,
    catalog: V11EvidenceCatalog,
) -> list[_PlanTextIssue]:
    facts_by_id = _fact_index(catalog)
    issues = [
        issue
        for selection in plan.medications
        for issue in _medication_text_issues(
            selection,
            catalog.medications[selection.item_id],
            facts_by_id,
        )
    ]
    for scope, selections, cards in (
        ("interaction", plan.interactions, catalog.interactions),
        ("lifestyle", plan.lifestyle, catalog.lifestyle),
    ):
        cards_by_id = {card.card_id: card for card in cards}
        issues.extend(
            issue
            for selection in selections
            if (
                issue := _card_text_issue(
                    scope=scope,
                    selection=selection,
                    card=cards_by_id[selection.card_id],
                )
            )
        )
    return issues


def card_plan_validation_issues(
    value: IntakeReportCardsPlan | dict[str, object],
    catalog: V11EvidenceCatalog,
) -> tuple[str, ...]:
    """Return every text issue after strict identity/source/category validation."""
    plan = value if isinstance(value, IntakeReportCardsPlan) else IntakeReportCardsPlan.model_validate(value)
    _validate_plan_structure(plan, catalog)
    return tuple(issue.message for issue in _collect_text_issues(plan, catalog))


def _project_plan_whitespace(  # noqa: C901 - applies the same projection to every schema text slot
    plan: IntakeReportCardsPlan,
    catalog: V11EvidenceCatalog,
) -> IntakeReportCardsPlan:
    """Apply bounded whitespace proposals after the plan's structure is trusted."""
    facts_by_id = _fact_index(catalog)
    raw = plan.model_dump(mode="python")
    for index, selection in enumerate(plan.medications):
        raw_medication = raw["medications"][index]
        for category in ("efficacy", "caution", "contraindication"):
            section = getattr(selection, category)
            if section.text is None:
                continue
            canonical_text = " ".join(facts_by_id[evidence_id].text for evidence_id in section.evidence_ids)
            if projected := _project_near_match_whitespace(section.text, canonical_text):
                raw_medication[category]["text"] = projected
        if selection.detail_texts:
            for detail_index, evidence_id in enumerate(selection.detail_ids):
                projected = _project_near_match_whitespace(
                    selection.detail_texts[detail_index],
                    facts_by_id[evidence_id].text,
                )
                if projected is not None:
                    raw_medication["detail_texts"][detail_index] = projected

    for field_name, selections, cards in (
        ("interactions", plan.interactions, catalog.interactions),
        ("lifestyle", plan.lifestyle, catalog.lifestyle),
    ):
        cards_by_id = {card.card_id: card for card in cards}
        for index, selection in enumerate(selections):
            if selection.summary_text is None:
                continue
            projected = _project_near_match_whitespace(
                selection.summary_text,
                cards_by_id[selection.card_id].summary,
            )
            if projected is not None:
                raw[field_name][index]["summary_text"] = projected
    return IntakeReportCardsPlan.model_validate(raw)


def retain_validated_plan_text(  # noqa: C901 - caches and restores every supported text slot together
    value: IntakeReportCardsPlan | dict[str, object],
    catalog: V11EvidenceCatalog,
    retained: PlanTextCache,
) -> tuple[IntakeReportCardsPlan, tuple[str, ...]]:
    """Retain only per-request text fields that already passed strict validation."""
    plan = value if isinstance(value, IntakeReportCardsPlan) else IntakeReportCardsPlan.model_validate(value)
    _validate_plan_structure(plan, catalog)
    plan = _project_plan_whitespace(plan, catalog)
    issues = _collect_text_issues(plan, catalog)
    bad_keys = {issue.key for issue in issues}
    facts_by_id = _fact_index(catalog)
    raw = plan.model_dump(mode="python")

    for index, selection in enumerate(plan.medications):
        raw_medication = raw["medications"][index]
        for category in ("efficacy", "caution", "contraindication"):
            section = getattr(selection, category)
            canonical_text = " ".join(facts_by_id[evidence_id].text for evidence_id in section.evidence_ids)
            key = (
                "medication",
                str(selection.item_id),
                category,
                ",".join(section.evidence_ids),
                _compact_text(canonical_text),
            )
            if key not in bad_keys and section.text is not None:
                retained.setdefault(key, section.text)
            elif key in retained:
                raw_medication[category]["text"] = retained[key]

        if selection.detail_texts:
            detail_texts = list(selection.detail_texts)
        else:
            detail_texts = [facts_by_id[evidence_id].text for evidence_id in selection.detail_ids]
        restored_detail = False
        for detail_index, evidence_id in enumerate(selection.detail_ids):
            canonical_text = facts_by_id[evidence_id].text
            selected_text = selection.detail_texts[detail_index] if selection.detail_texts else None
            key = (
                "medication-detail",
                str(selection.item_id),
                str(detail_index),
                evidence_id,
                _compact_text(canonical_text),
            )
            if key not in bad_keys and selected_text is not None:
                retained.setdefault(key, selected_text)
            elif key in retained:
                detail_texts[detail_index] = retained[key]
                restored_detail = True
        if restored_detail:
            raw_medication["detail_texts"] = detail_texts

    for scope, field_name, selections, cards in (
        ("interaction", "interactions", plan.interactions, catalog.interactions),
        ("lifestyle", "lifestyle", plan.lifestyle, catalog.lifestyle),
    ):
        cards_by_id = {card.card_id: card for card in cards}
        raw_selections = raw[field_name]
        for index, selection in enumerate(selections):
            card = cards_by_id[selection.card_id]
            key = (scope, selection.card_id, _compact_text(card.summary))
            if key not in bad_keys and selection.summary_text is not None:
                retained.setdefault(key, selection.summary_text)
            elif key in retained:
                raw_selections[index]["summary_text"] = retained[key]

    merged = IntakeReportCardsPlan.model_validate(raw)
    remaining = tuple(issue.message for issue in _collect_text_issues(merged, catalog))
    return merged, remaining


def validate_card_plan(
    value: IntakeReportCardsPlan | dict[str, object],
    catalog: V11EvidenceCatalog,
) -> IntakeReportCardsPlan:
    """Reject incomplete, recategorized, cross-owner or fabricated AI plans."""
    plan = value if isinstance(value, IntakeReportCardsPlan) else IntakeReportCardsPlan.model_validate(value)
    _validate_plan_structure(plan, catalog)
    if issues := _collect_text_issues(plan, catalog):
        raise ValueError(issues[0].message)
    return plan


def _section(
    selection: object,
    facts_by_id: dict[str, EvidenceFact],
) -> CardSection:
    evidence_ids = selection.evidence_ids
    facts = [facts_by_id[evidence_id] for evidence_id in evidence_ids]
    return CardSection(
        text=(selection.text.strip() if selection.text is not None else " ".join(fact.text for fact in facts)),
        source_ids=list(selection.source_ids),
    )


def _overlap_cards(totals: list[IntakeReportNutrientTotal]) -> list[OverlapCard]:
    cards: list[OverlapCard] = []
    for total in totals:
        product_names = _unique(total.included_product_names)
        if len(product_names) < 2:
            continue
        if total.amount is None:
            summary = f"{', '.join(product_names)}에 포함돼 있지만 확인된 합계는 계산할 수 없습니다."
        else:
            summary = f"{', '.join(product_names)}의 확인된 합계는 {total.daily_total}입니다."
        unknown_names = _unique(total.unknown_product_names)
        if unknown_names:
            summary += f" 함량을 확인할 수 없는 제품: {', '.join(unknown_names)}."
        cards.append(
            OverlapCard(
                nutrient_name=total.nutrient_name,
                title=f"{total.nutrient_name}가 {len(product_names)}개 제품에 들어 있어요",
                summary=summary,
                action=(
                    f"{total.nutrient_name} 제품을 더 추가하기 전에, 지금 먹는 제품의 함량과 복용량부터 확인하세요."
                ),
                product_names=product_names,
                product_count=len(product_names),
            )
        )
    return cards


def render_cards(
    plan: IntakeReportCardsPlan,
    catalog: V11EvidenceCatalog,
    draft: IntakeReportDraft,
) -> IntakeReportCards:
    """Project a validated plan into immutable public cards."""
    plan = validate_card_plan(plan, catalog)
    facts_by_id = _fact_index(catalog)
    medications: list[MedicationCard] = []
    for selection in plan.medications:
        medication = catalog.medications[selection.item_id]
        detail_facts = [facts_by_id[evidence_id] for evidence_id in selection.detail_ids]
        medications.append(
            MedicationCard(
                item_id=selection.item_id,
                product_name=medication.product_name,
                efficacy=_section(selection.efficacy, facts_by_id),
                caution=_section(selection.caution, facts_by_id),
                contraindication=_section(selection.contraindication, facts_by_id),
                details=[
                    CardDetail(
                        label=fact.label,
                        text=(selection.detail_texts[index].strip() if selection.detail_texts else fact.text),
                        source_ids=list(fact.source_ids),
                    )
                    for index, fact in enumerate(detail_facts)
                ],
                source_ids=list(selection.source_ids),
            )
        )

    interactions_by_id = {card.card_id: card for card in catalog.interactions}
    interactions = [
        InteractionCard(
            id=(card := interactions_by_id[selection.card_id]).card_id,
            title=card.title,
            summary=(selection.summary_text.strip() if selection.summary_text is not None else card.summary),
            action=card.action,
            related_item_ids=list(card.related_item_ids),
            source_ids=list(card.source_ids),
            evidence_level=card.evidence_level,
            action_level=card.action_level,
        )
        for selection in plan.interactions
    ]
    lifestyle_by_id = {card.card_id: card for card in catalog.lifestyle}
    lifestyle = [
        LifestyleCard(
            id=(card := lifestyle_by_id[selection.card_id]).card_id,
            category=card.category,
            title=card.title,
            summary=(selection.summary_text.strip() if selection.summary_text is not None else card.summary),
            action=card.action,
            related_item_ids=list(card.related_item_ids),
            source_ids=list(card.source_ids),
        )
        for selection in plan.lifestyle
    ]
    return IntakeReportCards(
        medications=medications,
        interactions=interactions,
        overlaps=_overlap_cards(draft.nutrient_totals),
        lifestyle=lifestyle,
        sources=list(catalog.sources),
    )


_MARKDOWN_LITERAL_ENTITIES = str.maketrans(
    {
        "[": "&#91;",
        "]": "&#93;",
        "(": "&#40;",
        ")": "&#41;",
        "*": "&#42;",
        "_": "&#95;",
        "#": "&#35;",
        "|": "&#124;",
        "`": "&#96;",
    }
)


def _literal(value: str) -> str:
    flattened = value.replace("\r", " ").replace("\n", " ")
    return html.escape(flattened, quote=True).translate(_MARKDOWN_LITERAL_ENTITIES)


def _table_cell(value: str) -> str:
    return _literal(value)


def _clinical_literal(value: str) -> str:
    """Match the UI's one-pass entity display, then escape all Markdown syntax."""
    decoded = re.sub(
        r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);",
        lambda match: html.unescape(match.group()),
        value,
    )
    return _literal(decoded)


def _normalized_action_key(action: str | None) -> str:
    """Match the UI's one-pass entity decode + whitespace normalization for grouping."""
    decoded = re.sub(
        r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);",
        lambda match: html.unescape(match.group()),
        action or "",
    )
    return _WHITESPACE_RE.sub(" ", decoded).strip()


def _grouped_action_lines(
    cards: list,
    *,
    context_key,
    card_lines: Callable[[object, bool], list[str]],
) -> list[str]:
    """Group cards sharing a context and a normalized action, common action first."""
    groups: list[dict[str, object]] = []
    group_by_key: dict[tuple[object, str], int] = {}
    for card in cards:
        normalized = _normalized_action_key(card.action)
        key = (context_key(card), normalized)
        existing = group_by_key.get(key) if normalized else None
        if existing is not None:
            groups[existing]["members"].append(card)  # type: ignore[union-attr]
        else:
            if normalized:
                group_by_key[key] = len(groups)
            groups.append({"action": normalized, "members": [card]})

    lines: list[str] = []
    for group in groups:
        members = group["members"]
        if len(members) > 1:
            lines.extend(
                (
                    "",
                    f"**공통 안내 · {len(members)}개 항목**",
                    "",
                    _literal(group["action"]),
                )
            )
            for card in members:
                lines.extend(card_lines(card, False))
        else:
            lines.extend(card_lines(members[0], True))
    return lines


def render_cards_markdown(  # noqa: C901 - section projection is deliberately linear and deterministic
    cards: IntakeReportCards,
    draft: IntakeReportDraft,
) -> str:
    """Render email Markdown from the same public cards used by the screen."""
    medication_count = sum(item.item_type.value == "MEDICATION" for item in draft.current_stack)
    supplement_count = sum(item.item_type.value == "SUPPLEMENT" for item in draft.current_stack)
    profile = draft.profile_label or "프로필 기준 확인 필요"
    lines = [
        "# 내 약, 꼭 알아둘 점",
        "",
        f"{_literal(profile)} · 약 {medication_count}종 · 영양제 {supplement_count}종",
    ]
    if draft.basis_note:
        lines.extend(("", _literal(draft.basis_note)))

    if cards.interactions:
        lines.extend(("", "## 함께 확인할 주의사항"))
        level_labels = {"WARNING": "중요 주의", "CHECK": "확인 필요", "INFORMATION": "안내"}
        sorted_interactions = sorted(cards.interactions, key=lambda card: card.action_level != "WARNING")

        def _interaction_lines(card: object, show_action: bool) -> list[str]:
            block = [
                "",
                f"### {_clinical_literal(card.title)}",
                f"**{level_labels[card.action_level]}**",
                "",
                _clinical_literal(card.summary),
            ]
            if show_action:
                block.extend(("", f"**할 일:** {_clinical_literal(card.action)}"))
            return block

        lines.extend(
            _grouped_action_lines(
                sorted_interactions,
                context_key=lambda card: (card.evidence_level, card.action_level),
                card_lines=_interaction_lines,
            )
        )

    if cards.overlaps:
        lines.extend(("", "## 영양제끼리 확인할 점"))

        def _overlap_lines(card: object, show_action: bool) -> list[str]:
            block = [
                "",
                f"### {_clinical_literal(card.title)}",
                _clinical_literal(card.summary),
            ]
            if show_action:
                block.extend(("", f"**할 일:** {_clinical_literal(card.action)}"))
            return block

        lines.extend(
            _grouped_action_lines(list(cards.overlaps), context_key=lambda card: "", card_lines=_overlap_lines)
        )

    if cards.lifestyle:
        lines.extend(("", "## 생활습관 가이드"))

        def _lifestyle_lines(card: object, show_action: bool) -> list[str]:
            block = [
                "",
                f"### {_clinical_literal(card.title)}",
                f"**{_literal(card.category)}**",
                "",
                _clinical_literal(card.summary),
            ]
            if show_action:
                block.extend(("", f"**할 일:** {_clinical_literal(card.action)}"))
            return block

        lines.extend(
            _grouped_action_lines(
                list(cards.lifestyle),
                context_key=lambda card: card.category,
                card_lines=_lifestyle_lines,
            )
        )

    if draft.unverified_items:
        lines.extend(("", "## 확인이 필요한 등록 정보"))
        for item in draft.unverified_items:
            lines.extend(
                (
                    "",
                    f"### {_literal(item.title)}",
                    _literal(item.message),
                    "",
                    f"**확인 방법:** {_literal(item.next_step)}",
                )
            )

    if draft.nutrient_totals:
        lines.extend(
            (
                "",
                "## 영양소 기준 비교",
                "",
                "| 영양소 | 확인된 합계 | 비교 기준 | 기준 대비 |",
                "| --- | --- | --- | --- |",
            )
        )
        for total in draft.nutrient_totals:
            reference = (
                f"{total.reference_kind} {total.reference_value} {total.unit or ''}".strip()
                if total.reference_kind and total.reference_value
                else "확인 필요"
            )
            percent = f"{total.reference_percent}%" if total.reference_percent is not None else "확인 필요"
            lines.append(
                "| "
                + " | ".join(
                    _table_cell(value) for value in (total.nutrient_name, total.daily_total, reference, percent)
                )
                + " |"
            )
        limitation_lines = [
            f"- {_literal(total.nutrient_name)}: 함량을 확인할 수 없는 제품 — "
            + ", ".join(_literal(name) for name in _unique(total.unknown_product_names))
            for total in draft.nutrient_totals
            if total.unknown_product_names
        ]
        if limitation_lines:
            lines.extend(("", "확인되지 않은 함량은 0으로 계산하지 않았습니다.", "", *limitation_lines))

    if cards.medications:
        lines.extend(("", "## 약 정보"))
        stack_by_id = {item.item_id: item for item in draft.current_stack if item.item_type.value == "MEDICATION"}
        for card in cards.medications:
            stack_item = stack_by_id[card.item_id]
            lines.extend(
                (
                    "",
                    f"### {_literal(card.product_name)}",
                    "",
                    "**등록 복용 정보**",
                    _literal(stack_item.registered_intake_info),
                    "",
                    "**효능**",
                    _clinical_literal(card.efficacy.text),
                    "",
                    "**주의**",
                    _clinical_literal(card.caution.text),
                    "",
                    "**금기**",
                    _clinical_literal(card.contraindication.text),
                )
            )
            for detail in card.details:
                lines.extend(("", f"**{_literal(detail.label)}**", _clinical_literal(detail.text)))

    supplements = [item for item in draft.current_stack if item.item_type.value == "SUPPLEMENT"]
    if supplements:
        lines.extend(("", "## 등록한 영양제", ""))
        lines.extend(
            f"- {_literal(item.product_name)} — {_literal(item.registered_intake_info)}" for item in supplements
        )

    lines.extend(("", "## 비교 기준과 출처", ""))
    if draft.basis_note:
        lines.append(_literal(draft.basis_note))
    else:
        lines.append("확인된 등록 정보와 제공된 근거만 사용했습니다.")
    for index, source in enumerate(cards.sources, start=1):
        organization = f" · {source.organization}" if source.organization else ""
        evidence_label = f" · {_EVIDENCE_LEVEL_LABELS.get(source.evidence_level, '근거 수준 미확인')}"
        if source.url:
            lines.append(
                f"- [{index}] [{_literal(source.title)}]({source.url})"
                f"{_literal(organization)}{_literal(evidence_label)}"
            )
        else:
            lines.append(f"- [{index}] {_literal(source.title)}{_literal(organization)}{_literal(evidence_label)}")
    lines.extend(
        (
            "",
            "이 리포트에서 전문가는 복약 상담이 가능한 의사·약사를 뜻해요.",
            "제품 설명서와 처방·복약 지시를 우선하세요.",
        )
    )
    return "\n".join(lines).strip()
