"""Lifestyle guidance keeps each registered product's cards together in every export."""

from ai_worker.reports.guidance_groups import (
    COMMON_INGREDIENT_DISCLAIMER,
    group_lifestyle_guidance_cards,
    product_guidance_display,
)
from ai_worker.reports.v11_cards import render_cards_markdown
from ai_worker.schemas.intake_report_cards import CardSource, IntakeReportCards, LifestyleCard
from ai_worker.tests.reports.test_rag_guidance_acceptance import _draft


def test_markdown_groups_product_guidance_without_interleaving_or_losing_rag_references() -> None:
    """Would fail if lifestyle action sharing crossed a registered-product boundary."""
    draft = _draft()
    second_medication = draft.current_stack[0].model_copy(update={"item_id": 303, "product_name": "이부프로펜"})
    colliding_supplement = draft.current_stack[1].model_copy(update={"item_id": 101, "product_name": "동일번호 영양제"})
    draft = draft.model_copy(
        update={"current_stack": [draft.current_stack[0], colliding_supplement, second_medication]}
    )
    shared_action = "제품 설명서를 확인하세요."
    cards = IntakeReportCards(
        lifestyle=[
            LifestyleCard(
                id="rag:lifestyle:medication:101:1",
                category="생활 관리",
                title="첫 약 안내",
                summary=f"{COMMON_INGREDIENT_DISCLAIMER} 첫 약 설명",
                action=shared_action,
                related_item_ids=[101],
                source_ids=["rag-a"],
            ),
            LifestyleCard(
                id="rag:lifestyle:supplement:101:1",
                category="생활 관리",
                title="영양제 안내",
                summary="영양제 설명",
                action=shared_action,
                related_item_ids=[101],
                source_ids=["rag-b"],
            ),
            LifestyleCard(
                id="rag:lifestyle:medication:101:2",
                category="생활 관리",
                title="둘째 약 안내",
                summary=f"{COMMON_INGREDIENT_DISCLAIMER} 둘째 약 설명",
                action=shared_action,
                related_item_ids=[101],
                source_ids=["rag-c"],
            ),
            LifestyleCard(
                id="habit:two-drugs",
                category="생활 관리",
                title="두 약 함께 안내",
                summary="두 약의 조합 설명",
                action="두 제품을 함께 확인하세요.",
                related_item_ids=[303, 101],
                source_ids=["rag-d"],
            ),
            LifestyleCard(
                id="habit:two-drugs-reversed",
                category="생활 관리",
                title="두 약 순서 반대 안내",
                summary="두 약 순서 반대 설명",
                action="두 제품을 함께 확인하세요.",
                related_item_ids=[101, 303],
                source_ids=["rag-e"],
            ),
        ],
        sources=[
            CardSource(
                id=source_id,
                title=source_title,
                evidence_level="PUBLIC_GUIDE",
                quote=f"{source_title} 인용",
                chunk_id=source_id,
            )
            for source_id, source_title in [
                ("rag-a", "첫 약 근거"),
                ("rag-b", "영양제 근거"),
                ("rag-c", "둘째 약 근거"),
                ("rag-d", "두 약 근거"),
                ("rag-e", "두 약 순서 반대 근거"),
            ]
        ],
    )

    markdown = render_cards_markdown(cards, draft)

    assert "## 약·영양제별 주의사항 및 가이드" in markdown
    assert "#### 첫 약 안내" not in markdown
    assert "#### 둘째 약 안내" not in markdown
    assert markdown.index("### 아세트아미노펜\n") < markdown.index("첫 약 설명")
    assert markdown.index("첫 약 설명") < markdown.index("둘째 약 설명") < markdown.index("### 동일번호 영양제")
    assert markdown.index("### 공통 안내") < markdown.index("두 약의 조합 설명")
    assert markdown.count(COMMON_INGREDIENT_DISCLAIMER) == 1
    assert markdown.index(COMMON_INGREDIENT_DISCLAIMER) < markdown.index("첫 약 설명")
    assert markdown.count(shared_action) == 2
    assert markdown.count("두 제품을 함께 확인하세요.") == 1
    for source_title in ("첫 약 근거", "영양제 근거", "둘째 약 근거", "두 약 근거", "두 약 순서 반대 근거"):
        assert source_title in markdown
    assert markdown.count("**근거:**") == 3


def test_email_groups_product_guidance_without_interleaving() -> None:
    """Would fail if the HTML export displayed cards by category instead of registered product."""
    from ai_worker.tests.reports.test_intake_email_parity import sample_email_report
    from app.core.email.intake_report_renderer import render_intake_report_email
    from app.dtos.intake_reports import IntakeReportResponse

    data = sample_email_report().model_dump()
    data["current_stack"].append(
        {
            **data["current_stack"][0],
            "item_id": 3,
            "product_name": "두 번째 약",
        }
    )
    data["cards"]["lifestyle"] = [
        {
            "id": "habit:1:first",
            "category": "생활 관리",
            "title": "첫 약 안내",
            "summary": f"{COMMON_INGREDIENT_DISCLAIMER} 첫 약 설명",
            "action": "제품 설명서를 확인하세요.",
            "related_item_ids": [1],
            "source_ids": ["rag-a"],
        },
        {
            "id": "rag:lifestyle:medication:3:1",
            "category": "생활 관리",
            "title": "두 번째 약 안내",
            "summary": "두 번째 약 설명",
            "action": "제품 설명서를 확인하세요.",
            "related_item_ids": [3],
            "source_ids": ["rag-b"],
        },
        {
            "id": "rag:lifestyle:medication:1:2",
            "category": "생활 관리",
            "title": "둘째 첫 약 안내",
            "summary": f"{COMMON_INGREDIENT_DISCLAIMER} 둘째 약의 추가 설명",
            "action": "제품 설명서를 확인하세요.",
            "related_item_ids": [1],
            "source_ids": ["rag-c"],
        },
    ]
    data["cards"]["sources"].extend(
        [
            {
                "id": source_id,
                "title": source_title,
                "evidence_level": "PUBLIC_GUIDE",
                "quote": f"{source_title} 인용",
                "chunk_id": source_id,
            }
            for source_id, source_title in [
                ("rag-a", "첫 약 근거"),
                ("rag-b", "두 번째 약 근거"),
                ("rag-c", "둘째 첫 약 근거"),
            ]
        ]
    )

    markup, plain = render_intake_report_email(IntakeReportResponse.model_validate(data))

    guidance = plain.split("약·영양제별 주의사항 및 가이드", maxsplit=1)[1]
    assert guidance.index("등록한 약") < guidance.index("첫 약 설명") < guidance.index("둘째 약의 추가 설명")
    assert guidance.index("둘째 약의 추가 설명") < guidance.index("두 번째 약") < guidance.index("두 번째 약 설명")
    assert "첫 약 안내" not in guidance
    assert "둘째 첫 약 안내" not in guidance
    assert plain.count(COMMON_INGREDIENT_DISCLAIMER) == 1
    assert markup.count(COMMON_INGREDIENT_DISCLAIMER) == 1
    assert "공통 안내 · 2개 항목" not in markup.split("약·영양제별 주의사항 및 가이드", maxsplit=1)[1]
    assert "<h4" not in markup.split("약·영양제별 주의사항 및 가이드", maxsplit=1)[1]
    for source_title in ("첫 약 근거", "두 번째 약 근거", "둘째 첫 약 근거"):
        assert source_title in plain


def test_group_resolver_uses_declared_card_type_and_never_guesses_a_collision() -> None:
    """Fixed card IDs and typed RAG IDs beat colliding numeric stack IDs."""
    draft = _draft()
    colliding_supplement = draft.current_stack[1].model_copy(update={"item_id": 101, "product_name": "동일번호 영양제"})
    draft = draft.model_copy(update={"current_stack": [draft.current_stack[0], colliding_supplement]})
    cards = [
        LifestyleCard(
            id="food-drink:101",
            category="음식",
            title="약 음식 주의",
            summary="약 설명",
            action="약 & 행동",
            related_item_ids=[101],
            source_ids=["med-food"],
        ),
        LifestyleCard(
            id="driving:101",
            category="운전",
            title="약 음식 주의",
            summary="약 운전 설명",
            action="약  &amp;  행동",
            related_item_ids=[101],
            source_ids=["med-driving"],
        ),
        LifestyleCard(
            id="timing:calcium",
            category="복용 시점",
            title="영양제 시점 안내",
            summary="영양제 설명",
            action="영양제 행동",
            related_item_ids=[101, 999],
            source_ids=["supp-timing"],
        ),
        LifestyleCard(
            id="habit:unknown-owner",
            category="생활 관리",
            title="소유자 미확정 안내",
            summary="공통 설명",
            action="공통 행동",
            related_item_ids=[101],
            source_ids=["ambiguous"],
        ),
        LifestyleCard(
            id="rag:lifestyle:medication:multiple",
            category="생활 관리",
            title="RAG 다중 제품 안내",
            summary="다중 제품 설명",
            action="다중 제품 행동",
            related_item_ids=[101, 999],
            source_ids=["rag-multi"],
        ),
        LifestyleCard(
            id="food:calcium",
            category="식품",
            title="일반 식품 안내",
            summary="식품 설명",
            action="식품 행동",
            source_ids=["food"],
        ),
    ]

    groups = group_lifestyle_guidance_cards(cards, draft.current_stack)

    assert [group.title for group in groups] == [
        "아세트아미노펜",
        "동일번호 영양제",
        "공통 안내",
        "공통 안내",
        "공통 안내",
    ]
    medication_display = product_guidance_display(groups[0])
    assert medication_display.categories == ("음식", "운전")
    assert medication_display.warning_titles == ("약 음식 주의",)
    assert medication_display.actions == ("약 & 행동",)
    assert medication_display.source_ids == ("med-food", "med-driving")
