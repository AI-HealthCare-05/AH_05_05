from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntakeReportStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    EMPTY = "EMPTY"


class IntakeReportReviewCardType(StrEnum):
    INTERACTION = "INTERACTION"
    REDUNDANCY = "REDUNDANCY"
    CAUTION = "CAUTION"
    MISSING_INFO = "MISSING_INFO"


class IntakeReportEvidenceLevel(StrEnum):
    APPROVED_RULE = "APPROVED_RULE"
    PUBLIC_GUIDE = "PUBLIC_GUIDE"
    RESEARCH = "RESEARCH"
    REGISTERED_INTAKE = "REGISTERED_INTAKE"
    UNVERIFIED = "UNVERIFIED"


class IntakeReportItemType(StrEnum):
    MEDICATION = "MEDICATION"
    SUPPLEMENT = "SUPPLEMENT"


class IntakeReportUnverifiedItemType(StrEnum):
    MISSING_AMOUNT = "MISSING_AMOUNT"
    MISSING_SCHEDULE = "MISSING_SCHEDULE"
    AMBIGUOUS_PRODUCT = "AMBIGUOUS_PRODUCT"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"


class IntakeReportFallbackReason(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CLIENT_ERROR = "CLIENT_ERROR"


class IntakeReportDataAvailability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_medication_count: int = Field(default=0, ge=0)
    active_supplement_count: int = Field(default=0, ge=0)
    approved_interaction_rule_available: bool = False
    rag_evidence_available: bool = False


class IntakeReportExecutiveSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewed_product_count: int = Field(default=0, ge=0)
    potential_redundancy_count: int = Field(default=0, ge=0)
    interaction_check_count: int = Field(default=0, ge=0)
    summary: str = Field(min_length=1)


class IntakeReportCurrentStackItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_type: IntakeReportItemType
    item_id: int = Field(ge=1)
    product_name: str = Field(min_length=1)
    ingredient_name: str | None = None
    registered_intake_info: str = Field(min_length=1)
    scheduled_slots: list[str] = Field(default_factory=list)
    evidence_level: IntakeReportEvidenceLevel


class IntakeReportSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    organization: str | None = None
    url: str | None = None
    evidence_level: IntakeReportEvidenceLevel


class IntakeReportReviewCard(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    card_type: IntakeReportReviewCardType
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    related_items: list[str] = Field(default_factory=list)
    check_item: str = Field(min_length=1)
    evidence_level: IntakeReportEvidenceLevel
    sources: list[IntakeReportSource] = Field(default_factory=list)


class IntakeReportNutrientTotal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    nutrient_name: str = Field(min_length=1)
    daily_total: str = Field(min_length=1)
    included_product_names: list[str] = Field(default_factory=list)
    calculation_status: str = Field(min_length=1)


class IntakeReportChartData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    medication_count: int = Field(default=0, ge=0)
    supplement_count: int = Field(default=0, ge=0)
    interaction_card_count: int = Field(default=0, ge=0)
    redundancy_card_count: int = Field(default=0, ge=0)
    caution_card_count: int = Field(default=0, ge=0)
    missing_info_card_count: int = Field(default=0, ge=0)


class IntakeReportProductGuide(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    product_name: str = Field(min_length=1)
    one_line_summary: str = Field(min_length=1)
    general_role: str | None = None
    check_item: str = Field(min_length=1)
    sources: list[IntakeReportSource] = Field(default_factory=list)


class IntakeReportUnverifiedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_type: IntakeReportUnverifiedItemType
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    related_items: list[str] = Field(default_factory=list)
    next_step: str = Field(min_length=1)


class IntakeReportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_availability: IntakeReportDataAvailability
    executive_summary: IntakeReportExecutiveSummary
    current_stack: list[IntakeReportCurrentStackItem] = Field(default_factory=list)
    review_cards: list[IntakeReportReviewCard] = Field(default_factory=list)
    nutrient_totals: list[IntakeReportNutrientTotal] = Field(default_factory=list)
    chart_data: IntakeReportChartData
    product_guides: list[IntakeReportProductGuide] = Field(default_factory=list)
    unverified_items: list[IntakeReportUnverifiedItem] = Field(default_factory=list)
    sources: list[IntakeReportSource] = Field(default_factory=list)
    deterministic_markdown: str = Field(min_length=1)

    def to_result(
        self,
        *,
        status: IntakeReportStatus,
        report_markdown: str,
    ) -> "IntakeReportResult":
        return IntakeReportResult(
            status=status,
            generated_at=datetime.now(UTC),
            data_availability=self.data_availability,
            executive_summary=self.executive_summary,
            current_stack=self.current_stack,
            review_cards=self.review_cards,
            nutrient_totals=self.nutrient_totals,
            chart_data=self.chart_data,
            product_guides=self.product_guides,
            unverified_items=self.unverified_items,
            report_markdown=report_markdown,
        )


class IntakeReportMarkdownPayload(BaseModel):
    """LLM이 반환하는 제한된 Markdown 보고서 출력."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_markdown: str = Field(min_length=1)


class IntakeReportGenerationOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_markdown: str = Field(min_length=1)
    fallback_used: bool
    fallback_reason: IntakeReportFallbackReason | None = None


class IntakeReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: IntakeReportStatus
    generated_at: datetime
    data_availability: IntakeReportDataAvailability
    executive_summary: IntakeReportExecutiveSummary
    current_stack: list[IntakeReportCurrentStackItem] = Field(default_factory=list)
    review_cards: list[IntakeReportReviewCard] = Field(default_factory=list)
    nutrient_totals: list[IntakeReportNutrientTotal] = Field(default_factory=list)
    chart_data: IntakeReportChartData
    product_guides: list[IntakeReportProductGuide] = Field(default_factory=list)
    unverified_items: list[IntakeReportUnverifiedItem] = Field(default_factory=list)
    report_markdown: str = Field(min_length=1)

    @classmethod
    def empty(cls, *, user_id: int) -> "IntakeReportResult":
        del user_id
        return cls(
            status=IntakeReportStatus.EMPTY,
            generated_at=datetime.now(UTC),
            data_availability=IntakeReportDataAvailability(),
            executive_summary=IntakeReportExecutiveSummary(
                summary="현재 복용 중으로 등록된 약·영양제가 없습니다.",
            ),
            chart_data=IntakeReportChartData(),
            report_markdown=(
                "# 약·영양제 생활관리 보고서\n\n"
                "현재 복용 중으로 등록된 약·영양제가 없습니다. "
                "등록 정보를 확인한 뒤 다시 이용해 주세요."
            ),
        )
