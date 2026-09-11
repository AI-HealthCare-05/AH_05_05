"""Public and model-plan schemas for evidence-locked v11 intake reports."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class _CardModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class CardSection(_CardModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class CardDetail(_CardModel):
    label: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class MedicationCard(_CardModel):
    item_id: int = Field(ge=1)
    product_name: str = Field(min_length=1)
    efficacy: CardSection
    caution: CardSection
    contraindication: CardSection
    details: list[CardDetail] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class InteractionCard(_CardModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    action: str = Field(min_length=1)
    related_item_ids: list[int] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    evidence_level: str = Field(min_length=1)
    action_level: Literal["WARNING", "CHECK", "INFORMATION"]


class OverlapCard(_CardModel):
    nutrient_name: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    action: str = Field(min_length=1)
    product_names: list[str] = Field(min_length=2)
    product_count: int = Field(ge=2)
    source_ids: list[str] = Field(default_factory=list)


class LifestyleCard(_CardModel):
    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    action: str = Field(min_length=1)
    related_item_ids: list[int] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class CardSource(_CardModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organization: str | None = None
    url: str | None = None
    evidence_level: str = Field(min_length=1)


class OriginalCardText(_CardModel):
    """Server-owned original retained when a display-only rewrite is accepted."""

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)


class IntakeReportCards(_CardModel):
    medications: list[MedicationCard] = Field(default_factory=list)
    interactions: list[InteractionCard] = Field(default_factory=list)
    overlaps: list[OverlapCard] = Field(default_factory=list)
    lifestyle: list[LifestyleCard] = Field(default_factory=list)
    sources: list[CardSource] = Field(default_factory=list)
    original_texts: list[OriginalCardText] = Field(default_factory=list)


class IntakeReportEvidenceSelection(_CardModel):
    """AI may order evidence and adjust whitespace, but may not rewrite it."""

    evidence_ids: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    text: str | None = None


class IntakeReportMedicationSelection(_CardModel):
    item_id: int = Field(ge=1)
    efficacy: IntakeReportEvidenceSelection
    caution: IntakeReportEvidenceSelection
    contraindication: IntakeReportEvidenceSelection
    detail_ids: list[str] = Field(default_factory=list)
    detail_texts: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class IntakeReportCardSelection(_CardModel):
    card_id: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    summary_text: str | None = None


class IntakeReportCardsPlan(_CardModel):
    """The complete, evidence-ID-only structured output requested from the AI."""

    medications: list[IntakeReportMedicationSelection] = Field(default_factory=list)
    interactions: list[IntakeReportCardSelection] = Field(default_factory=list)
    lifestyle: list[IntakeReportCardSelection] = Field(default_factory=list)
