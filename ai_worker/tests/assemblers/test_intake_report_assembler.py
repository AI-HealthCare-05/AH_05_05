from datetime import date

from ai_worker.assemblers.intake_report_assembler import IntakeReportAssembler
from ai_worker.schemas.intake_report import (
    IntakeReportEvidenceLevel,
    IntakeReportReviewCardType,
    IntakeReportUnverifiedItemType,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
    InteractionRuleFact,
)


def _context_with_active_intakes() -> ActiveIntakeContext:
    return ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(
                medication_id=10,
                care_episode_id=100,
                name="와파린정",
                dose="1정",
                times_per_day=1,
                scheduled_slots=["BEDTIME"],
            ),
        ],
        supplements=[
            ActiveSupplement(
                registration_id=20,
                supplement_nutrient_id=30,
                name="비타민 K",
                dose_amount="1",
                dose_unit="캡슐",
                start_date=date(2026, 9, 1),
                scheduled_slots=["MORNING"],
            ),
        ],
    )


def _approved_rule() -> InteractionRuleFact:
    return InteractionRuleFact(
        interaction_rule_id=1,
        pair_key="warfarin::vitamin_k",
        pair_type="DRUG_SUPPLEMENT",
        left_name="와파린",
        right_name="비타민 K",
        risk_level="CAUTION",
        effect_texts=["비타민 K 섭취 변화는 와파린 효과에 영향을 줄 수 있습니다."],
        source_titles=["승인 규칙 출처"],
        source_urls=["https://example.com/rule"],
    )


def test_assembler_prioritizes_approved_interaction_rules() -> None:
    draft = IntakeReportAssembler().assemble(
        context=_context_with_active_intakes(),
        guide_lookups=[],
        approved_rules=[_approved_rule()],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.review_cards[0].card_type == IntakeReportReviewCardType.INTERACTION
    assert (
        draft.review_cards[0].evidence_level
        == IntakeReportEvidenceLevel.APPROVED_RULE
    )
    assert draft.executive_summary.interaction_check_count == 1


def test_assembler_marks_missing_amount_without_total() -> None:
    context = _context_with_active_intakes()
    context.supplements[0].dose_amount = ""

    draft = IntakeReportAssembler().assemble(
        context=context,
        guide_lookups=[],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.nutrient_totals == []
    assert (
        draft.unverified_items[0].item_type
        == IntakeReportUnverifiedItemType.MISSING_AMOUNT
    )
