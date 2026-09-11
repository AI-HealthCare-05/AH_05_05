from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field

from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportCurrentStackItem,
    IntakeReportDataAvailability,
    IntakeReportExecutiveSummary,
    IntakeReportNutrientTotal,
    IntakeReportProductGuide,
    IntakeReportResult,
    IntakeReportReviewCard,
    IntakeReportSource,
    IntakeReportUnverifiedItem,
)
from ai_worker.schemas.intake_report_cards import IntakeReportCards
from app.dtos.base import CamelModel


class GenerateIntakeReportRequest(CamelModel):
    """버튼 호출은 빈 객체만 허용하며, 분석 범위는 인증 사용자로 고정한다."""

    model_config = ConfigDict(extra="forbid")


class SendIntakeReportEmailRequest(CamelModel):
    """A server-issued encrypted report snapshot; no recipient or HTML is accepted."""

    model_config = ConfigDict(extra="forbid")
    email_token: str = Field(min_length=1, max_length=900_000)


class IntakeReportEmailJobResponse(CamelModel):
    job_id: int
    status: str


class IntakeReportErrorResponse(CamelModel):
    code: str
    message: str


class IntakeReportDataAvailabilityResponse(CamelModel):
    active_medication_count: int
    active_supplement_count: int
    approved_interaction_rule_available: bool
    rag_evidence_available: bool

    @classmethod
    def from_schema(
        cls,
        data: IntakeReportDataAvailability,
    ) -> "IntakeReportDataAvailabilityResponse":
        return cls(**data.model_dump())


class IntakeReportSummaryCardResponse(CamelModel):
    key: Literal[
        "reviewedProductCount",
        "potentialRedundancyCount",
        "interactionCheckCount",
    ]
    label: str
    value: int
    unit: Literal["개", "건"]


class IntakeReportExecutiveSummaryResponse(CamelModel):
    reviewed_product_count: int
    potential_redundancy_count: int
    interaction_check_count: int
    summary: str
    summary_cards: list[IntakeReportSummaryCardResponse]

    @classmethod
    def from_schema(
        cls,
        summary: IntakeReportExecutiveSummary,
    ) -> "IntakeReportExecutiveSummaryResponse":
        return cls(
            **summary.model_dump(),
            summary_cards=[
                IntakeReportSummaryCardResponse(
                    key="reviewedProductCount",
                    label="검토한 제품",
                    value=summary.reviewed_product_count,
                    unit="개",
                ),
                IntakeReportSummaryCardResponse(
                    key="potentialRedundancyCount",
                    label="중복 확인 항목",
                    value=summary.potential_redundancy_count,
                    unit="건",
                ),
                IntakeReportSummaryCardResponse(
                    key="interactionCheckCount",
                    label="상호작용 확인 항목",
                    value=summary.interaction_check_count,
                    unit="건",
                ),
            ],
        )


class IntakeReportCurrentStackItemResponse(CamelModel):
    item_type: str
    item_id: int
    product_name: str
    ingredient_name: str | None = None
    registered_intake_info: str
    scheduled_slots: list[str]
    evidence_level: str

    @classmethod
    def from_schema(
        cls,
        item: IntakeReportCurrentStackItem,
    ) -> "IntakeReportCurrentStackItemResponse":
        return cls(**item.model_dump(mode="json"))


class IntakeReportSourceResponse(CamelModel):
    title: str
    organization: str | None = None
    url: str | None = None
    evidence_level: str

    @classmethod
    def from_schema(cls, source: IntakeReportSource) -> "IntakeReportSourceResponse":
        return cls(**source.model_dump(mode="json"))


class IntakeReportReviewCardResponse(CamelModel):
    card_type: str
    title: str
    summary: str
    related_items: list[str]
    check_item: str
    evidence_level: str
    sources: list[IntakeReportSourceResponse]

    @classmethod
    def from_schema(cls, card: IntakeReportReviewCard) -> "IntakeReportReviewCardResponse":
        return cls(
            card_type=card.card_type.value,
            title=card.title,
            summary=card.summary,
            related_items=card.related_items,
            check_item=card.check_item,
            evidence_level=card.evidence_level.value,
            sources=[IntakeReportSourceResponse.from_schema(source) for source in card.sources],
        )


class IntakeReportNutrientTotalResponse(CamelModel):
    nutrient_name: str
    daily_total: str
    included_product_names: list[str]
    calculation_status: str
    amount: str | None = None
    unit: str | None = None
    reference_value: str | None = None
    reference_kind: Literal["RNI", "AI"] | None = None
    reference_percent: str | None = None
    unknown_product_names: list[str] = Field(default_factory=list)

    @classmethod
    def from_schema(cls, total: IntakeReportNutrientTotal) -> "IntakeReportNutrientTotalResponse":
        return cls(**total.model_dump(mode="json"))


class IntakeReportChartDataResponse(CamelModel):
    medication_count: int
    supplement_count: int
    interaction_card_count: int
    redundancy_card_count: int
    caution_card_count: int
    missing_info_card_count: int

    @classmethod
    def from_schema(cls, data: IntakeReportChartData) -> "IntakeReportChartDataResponse":
        return cls(**data.model_dump())


class IntakeReportProductGuideResponse(CamelModel):
    product_name: str
    one_line_summary: str
    general_role: str | None = None
    check_item: str
    sources: list[IntakeReportSourceResponse]

    @classmethod
    def from_schema(cls, guide: IntakeReportProductGuide) -> "IntakeReportProductGuideResponse":
        return cls(
            product_name=guide.product_name,
            one_line_summary=guide.one_line_summary,
            general_role=guide.general_role,
            check_item=guide.check_item,
            sources=[IntakeReportSourceResponse.from_schema(source) for source in guide.sources],
        )


class IntakeReportUnverifiedItemResponse(CamelModel):
    item_type: str
    title: str
    message: str
    related_items: list[str]
    next_step: str

    @classmethod
    def from_schema(
        cls,
        item: IntakeReportUnverifiedItem,
    ) -> "IntakeReportUnverifiedItemResponse":
        return cls(**item.model_dump(mode="json"))


class IntakeReportResponse(CamelModel):
    report_status: Literal["COMPLETED", "PARTIAL", "EMPTY"]
    generated_at: datetime
    data_availability: IntakeReportDataAvailabilityResponse
    executive_summary: IntakeReportExecutiveSummaryResponse
    current_stack: list[IntakeReportCurrentStackItemResponse]
    review_cards: list[IntakeReportReviewCardResponse]
    nutrient_totals: list[IntakeReportNutrientTotalResponse]
    chart_data: IntakeReportChartDataResponse
    product_guides: list[IntakeReportProductGuideResponse]
    unverified_items: list[IntakeReportUnverifiedItemResponse]
    report_markdown: str
    presentation_version: Literal["ai-report-v2", "ai-report-v11"] | None = None
    cards: IntakeReportCards | None = None
    profile_label: str | None = None
    basis_note: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    email_token: str | None = None

    @classmethod
    def from_result(cls, result: IntakeReportResult) -> "IntakeReportResponse":
        return cls(
            report_status=result.status.value,
            generated_at=result.generated_at,
            data_availability=IntakeReportDataAvailabilityResponse.from_schema(
                result.data_availability,
            ),
            executive_summary=IntakeReportExecutiveSummaryResponse.from_schema(
                result.executive_summary,
            ),
            current_stack=[IntakeReportCurrentStackItemResponse.from_schema(item) for item in result.current_stack],
            review_cards=[IntakeReportReviewCardResponse.from_schema(card) for card in result.review_cards],
            nutrient_totals=[IntakeReportNutrientTotalResponse.from_schema(total) for total in result.nutrient_totals],
            chart_data=IntakeReportChartDataResponse.from_schema(result.chart_data),
            product_guides=[IntakeReportProductGuideResponse.from_schema(guide) for guide in result.product_guides],
            unverified_items=[IntakeReportUnverifiedItemResponse.from_schema(item) for item in result.unverified_items],
            report_markdown=result.report_markdown,
            presentation_version=result.presentation_version,
            cards=result.cards,
            profile_label=result.profile_label,
            basis_note=result.basis_note,
            fallback_used=result.fallback_used,
            fallback_reason=result.fallback_reason,
        )
