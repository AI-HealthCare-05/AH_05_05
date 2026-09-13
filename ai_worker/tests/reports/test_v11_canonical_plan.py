"""Tests for the server-owned v11 card-plan projection."""

from ai_worker.reports.v11_cards import (
    CatalogInteraction,
    CatalogLifestyle,
    EvidenceFact,
    MedicationEvidence,
    V11EvidenceCatalog,
    build_canonical_card_plan,
    card_plan_validation_issues,
    validate_card_plan,
)
from ai_worker.schemas.intake_report_cards import CardSource, IntakeReportCardsPlan


def _fact(
    evidence_id: str,
    owner_item_id: int,
    category: str,
    text: str,
    source_ids: tuple[str, ...],
) -> EvidenceFact:
    return EvidenceFact(
        evidence_id=evidence_id,
        owner_item_id=owner_item_id,
        category=category,  # type: ignore[arg-type]  # Small fixture covers every valid literal below.
        label=category,
        text=text,
        source_ids=source_ids,
    )


def _catalog() -> V11EvidenceCatalog:
    medication_ten = MedicationEvidence(
        item_id=10,
        product_name="열 번 약",
        facts=(
            _fact("med:10:efficacy:1", 10, "efficacy", "통증을줄입니다.", ("source:a",)),
            _fact("med:10:efficacy:2", 10, "efficacy", "열을내립니다.", ("source:b", "source:a")),
            _fact("med:10:caution:1", 10, "caution", "식후에복용하세요.", ("source:c",)),
            _fact("med:10:contra:1", 10, "contraindication", "임부는복용하지마세요.", ("source:d",)),
            _fact(
                "med:10:detail:1",
                10,
                "detail",
                "이약을복용하기전에반드시의사또는약사와상의하십시오.",
                ("source:e",),
            ),
        ),
    )
    medication_twenty = MedicationEvidence(
        item_id=20,
        product_name="스무 번 약",
        facts=(
            _fact("med:20:efficacy:1", 20, "efficacy", "증상을완화합니다.", ("source:f",)),
            _fact("med:20:caution:1", 20, "caution", "졸릴수있습니다.", ("source:g",)),
            _fact("med:20:contra:1", 20, "contraindication", "알레르기가있으면복용하지마세요.", ("source:h",)),
        ),
    )
    return V11EvidenceCatalog(
        # Deliberately reverse insertion order: the server projection must be stable.
        medications={20: medication_twenty, 10: medication_ten},
        interactions=(
            CatalogInteraction(
                card_id="check-z",
                title="확인",
                summary="두약을함께복용하기전에확인하세요.",
                action="확인",
                related_item_ids=(10, 20),
                source_ids=("source:i",),
                evidence_level="PUBLIC_GUIDE",
                action_level="CHECK",
            ),
            CatalogInteraction(
                card_id="warning-a",
                title="경고",
                summary="출혈위험을확인하세요.",
                action="확인",
                related_item_ids=(10,),
                source_ids=("source:j",),
                evidence_level="PUBLIC_GUIDE",
                action_level="WARNING",
            ),
        ),
        lifestyle=(
            CatalogLifestyle(
                card_id="z-card",
                category="식사",
                title="식사",
                summary="식사와함께복용하세요.",
                action="확인",
                related_item_ids=(10,),
                source_ids=("source:k",),
            ),
            CatalogLifestyle(
                card_id="a-card",
                category="생활",
                title="생활",
                summary="수분을충분히섭취하세요.",
                action="확인",
                related_item_ids=(20,),
                source_ids=("source:l",),
            ),
        ),
        sources=(CardSource(id="source:a", title="source", evidence_level="PUBLIC_GUIDE"),),
    )


def test_build_canonical_card_plan_owns_all_identity_source_and_text_fields() -> None:
    plan = build_canonical_card_plan(_catalog())

    assert [selection.item_id for selection in plan.medications] == [10, 20]
    first = plan.medications[0]
    assert first.efficacy.evidence_ids == ["med:10:efficacy:1", "med:10:efficacy:2"]
    assert first.efficacy.source_ids == ["source:a", "source:b"]
    assert first.efficacy.text == "통증을줄입니다. 열을내립니다."
    assert first.caution.text == "식후에복용하세요."
    assert first.contraindication.text == "임부는복용하지마세요."
    assert first.detail_ids == ["med:10:detail:1"]
    assert first.detail_texts == ["이약을복용하기전에반드시의사또는약사와상의하십시오."]
    assert first.source_ids == ["source:a", "source:b", "source:c", "source:d", "source:e"]
    assert [(selection.card_id, selection.source_ids, selection.summary_text) for selection in plan.interactions] == [
        ("warning-a", ["source:j"], "출혈위험을확인하세요."),
        ("check-z", ["source:i"], "두약을함께복용하기전에확인하세요."),
    ]
    assert [(selection.card_id, selection.source_ids, selection.summary_text) for selection in plan.lifestyle] == [
        ("a-card", ["source:l"], "수분을충분히섭취하세요."),
        ("z-card", ["source:k"], "식사와함께복용하세요."),
    ]


def test_build_canonical_card_plan_retains_dense_text_for_spacing_stage_after_structure_validation() -> None:
    plan = build_canonical_card_plan(_catalog())

    issues = card_plan_validation_issues(plan, _catalog())

    assert issues
    assert all(not issue.startswith("TEXT_MUTATION") for issue in issues)
    assert any(issue.startswith("TEXT_SPACING_REQUIRED") for issue in issues)


def test_build_canonical_card_plan_supports_an_empty_catalog() -> None:
    catalog = V11EvidenceCatalog(medications={}, interactions=(), lifestyle=(), sources=())

    plan = build_canonical_card_plan(catalog)

    assert plan == IntakeReportCardsPlan()
    assert validate_card_plan(plan, catalog) == plan
