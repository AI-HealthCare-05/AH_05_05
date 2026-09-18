from datetime import date

import pytest

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


def test_no_candidate_medications_share_one_notice_without_losing_names() -> None:
    from ai_worker.schemas.medication_chat import MedicationGuideLookup

    names = [f"등록약{index}정" for index in range(7)]
    context = ActiveIntakeContext(
        user_id=1,
        medications=[
            ActiveMedication(medication_id=index + 1, care_episode_id=1, name=name) for index, name in enumerate(names)
        ],
    )
    lookups = [
        MedicationGuideLookup(is_ambiguous=True, original_name=name, candidate_names=[f"후보{index}정"])
        for index, name in enumerate(names[:4])
    ] + [MedicationGuideLookup() for _ in range(3)]
    draft = IntakeReportAssembler().assemble(
        context=context, guide_lookups=lookups, approved_rules=[], knowledge_chunks=[], rag_available=True
    )

    assert len(draft.unverified_items) == 5
    missing = [
        item for item in draft.unverified_items if item.item_type == IntakeReportUnverifiedItemType.MISSING_EVIDENCE
    ]
    assert len(missing) == 1
    assert missing[0].related_items == names[4:]
    assert all(name in missing[0].message for name in names[4:])
    assert all("제품명 후보" not in item.message for item in missing)
    assert all(name in draft.deterministic_markdown for name in names)


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
    assert draft.review_cards[0].evidence_level == IntakeReportEvidenceLevel.APPROVED_RULE
    assert draft.executive_summary.interaction_check_count == 1


def test_assembler_preserves_confirmed_medication_ingredient_aliases() -> None:
    context = _context_with_active_intakes()
    context.medications[0].interaction_names = [" 와파린정 ", "와파린", "아세트아미노펜", "", "와파린"]

    draft = IntakeReportAssembler().assemble(
        context=context,
        guide_lookups=[],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.current_stack[0].ingredient_aliases == ["와파린", "아세트아미노펜"]
    assert draft.current_stack[0].product_name == "와파린정"


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
    assert draft.unverified_items[0].item_type == IntakeReportUnverifiedItemType.MISSING_AMOUNT


@pytest.mark.parametrize(
    ("stored", "display"),
    [
        ("2.000", "2"),
        ("1.000", "1"),
        ("1.500", "1.5"),
        ("0.050", "0.05"),
        ("0.005", "0.005"),
        ("2000", "2000"),
        ("2000.000", "2000"),
        ("확인 필요", "확인 필요"),
    ],
)
def test_report_trims_only_insignificant_dose_zeros(stored: str, display: str) -> None:
    context = _context_with_active_intakes()
    context.supplements[0].dose_amount = stored
    draft = IntakeReportAssembler().assemble(
        context=context,
        guide_lookups=[],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )
    assert draft.current_stack[1].registered_intake_info == f"{display}캡슐"
    assert f"{display}캡슐" in draft.deterministic_markdown
    assert context.supplements[0].dose_amount == stored


@pytest.mark.parametrize(
    ("stored", "display"),
    [
        ("1.00", "1"),
        ("1.500", "1.5"),
        ("0.005", "0.005"),
        ("2000.00", "2000"),
        (" 2.00 ", "2"),
        ("1정", "1정"),
        ("필요 시", "필요 시"),
    ],
)
def test_report_trims_medication_dose_zeros_without_changing_source(stored: str, display: str) -> None:
    context = _context_with_active_intakes()
    context.medications[0].dose = stored
    context.medications[0].name = "코아프로벨 300/12.5밀리그램"
    draft = IntakeReportAssembler().assemble(
        context=context,
        guide_lookups=[],
        approved_rules=[],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert draft.current_stack[0].registered_intake_info == f"{display} · 1일 1회"
    assert f"{display} · 1일 1회" in draft.deterministic_markdown
    assert draft.current_stack[0].product_name == "코아프로벨 300/12.5밀리그램"
    assert context.medications[0].dose == stored


def test_assembler_preserves_nullable_urls_for_repeated_source_titles() -> None:
    rule = InteractionRuleFact(
        interaction_rule_id=2,
        pair_key="warfarin::vitamin_k::sources",
        pair_type="DRUG_SUPPLEMENT",
        left_name="와파린",
        right_name="비타민 K",
        risk_level="CAUTION",
        effect_texts=["출처 연결을 확인합니다."],
        source_references=[
            {"title": "승인 규칙 출처", "url": None},
            {"title": "승인 규칙 출처", "url": "https://example.com/rule"},
            {"title": "제품 라벨", "url": "https://example.com/label"},
        ],
    )

    draft = IntakeReportAssembler().assemble(
        context=_context_with_active_intakes(),
        guide_lookups=[],
        approved_rules=[rule],
        knowledge_chunks=[],
        rag_available=True,
    )

    assert [source.model_dump(include={"title", "url"}) for source in draft.sources] == [
        {"title": "승인 규칙 출처", "url": None},
        {"title": "승인 규칙 출처", "url": "https://example.com/rule"},
        {"title": "제품 라벨", "url": "https://example.com/label"},
    ]
