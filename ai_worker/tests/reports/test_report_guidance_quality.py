"""Report guidance output rules: one heading, merged duplicates, bounded body, grouped evidence.

Every fixture here is synthetic. No patient data, no network, and no model call:
the preview, the merge, the upper-limit gate, and the evidence grouping are all
pure functions over hand-written cards.
"""

from __future__ import annotations

import pathlib
import re
from importlib.resources import files

from ai_worker.core.config import Config
from ai_worker.llm.prompts.prompt_assets import load_prompt_asset
from ai_worker.reports.guidance_groups import (
    BODY_PREVIEW_LIMIT,
    COMMON_INGREDIENT_DISCLAIMER,
    GuidanceProductGroup,
    group_guidance_evidence,
    product_guidance_display,
    summarize_guidance_body,
)
from ai_worker.reports.report_rag_pipeline import _filter_generic_overconsumption_cards
from ai_worker.schemas.intake_report import IntakeReportNutrientTotal
from ai_worker.schemas.intake_report_cards import LifestyleCard
from ai_worker.tests.reports.test_intake_email_parity import sample_email_report
from app.core.email.intake_report_renderer import render_intake_report_email
from app.dtos.intake_reports import IntakeReportResponse

_SENTENCE_TERMINATORS = (".", "!", "?", "。")


def _card(**overrides: object) -> LifestyleCard:
    return LifestyleCard(
        **{
            "id": "rag:lifestyle:supplement:202:1",
            "category": "생활관리 참고",
            "title": "기본 제목",
            "summary": "기본 설명입니다.",
            "action": "기본 행동입니다.",
            "related_item_ids": [202],
            "source_ids": [],
            **overrides,
        }
    )


def _total(**overrides: object) -> IntakeReportNutrientTotal:
    return IntakeReportNutrientTotal(
        **{
            "nutrient_name": "칼슘",
            "daily_total": "3000mg",
            "included_product_names": ["등록한 영양제"],
            "calculation_status": "LABEL_SCHEDULE",
            "amount": "3000",
            "unit": "mg",
            "upper_limit_value": "2500",
            **overrides,
        }
    )


# --- 200-character body rule ------------------------------------------------


def test_body_at_or_under_the_limit_is_shown_directly_without_a_preview() -> None:
    """Would fail if a body that already fits were needlessly hidden behind a toggle."""
    exactly_at_limit = "가" * (BODY_PREVIEW_LIMIT - 1) + "."
    assert len(exactly_at_limit) == BODY_PREVIEW_LIMIT
    assert summarize_guidance_body([exactly_at_limit]) is None
    assert summarize_guidance_body(["짧은 안내입니다."]) is None


def test_long_body_is_previewed_within_the_limit_and_only_on_a_sentence_boundary() -> None:
    """Would fail if the preview overran 200 characters or ended mid-sentence."""
    paragraphs = [f"{index}번째 주의사항을 자세히 설명하는 문장입니다." for index in range(1, 12)]
    preview = summarize_guidance_body(paragraphs)
    assert preview is not None
    assert len(preview) <= BODY_PREVIEW_LIMIT
    assert preview.endswith(_SENTENCE_TERMINATORS)
    # The preview is a real prefix of the body, never a paraphrase or a re-ordering.
    assert " ".join(paragraphs).startswith(preview)


def test_preview_ends_on_a_paragraph_break_when_the_body_has_no_closing_punctuation() -> None:
    """Would fail if punctuation-free paragraphs collapsed into one unsplittable run."""
    paragraphs = ["주의사항 " + "가" * 60] * 5
    preview = summarize_guidance_body(paragraphs)
    assert preview is not None
    assert len(preview) <= BODY_PREVIEW_LIMIT
    assert preview in " ".join(paragraphs)


def test_one_over_long_sentence_is_kept_whole_rather_than_cut_mid_sentence() -> None:
    """Documents the single case where the preview may exceed the limit, by design."""
    sentence = "한 문장이 매우 길어 " + "가" * (BODY_PREVIEW_LIMIT + 50) + "."
    preview = summarize_guidance_body([sentence, "뒤 문장입니다."])
    assert preview == sentence
    assert preview.endswith(".")


def test_display_preview_never_replaces_the_full_summaries_it_is_drawn_from() -> None:
    """Would fail if the toggle target lost any of the original body text."""
    bodies = [f"{index}번째 주의 설명 문장입니다." for index in range(1, 15)]
    group = GuidanceProductGroup(
        key="k",
        title="등록한 영양제",
        cards=[
            _card(id=f"rag:lifestyle:supplement:202:{index}", title=f"제목 {index}", summary=body, action=" ")
            for index, body in enumerate(bodies, start=1)
        ],
    )
    display = product_guidance_display(group)
    assert display.body_preview is not None
    assert len(display.body_preview) <= BODY_PREVIEW_LIMIT
    assert display.summaries == tuple(bodies)


# --- one heading, merged duplicates, one disclaimer -------------------------


def test_repeated_titles_categories_bodies_and_actions_are_merged_once_each() -> None:
    """Would fail if the product box repeated an identical warning title or body list."""
    group = GuidanceProductGroup(
        key="k",
        title="등록한 영양제",
        cards=[
            _card(
                id="c1",
                category="생활관리 참고",
                title="같은 제목",
                summary="같은 설명입니다.",
                action="같은 행동입니다.",
            ),
            _card(
                id="c2",
                category="생활관리 참고",
                title="같은  제목",
                summary="같은  설명입니다.",
                action="같은  행동입니다.",
            ),
            _card(
                id="c3",
                category="음식·음료 참고",
                title="다른 제목",
                summary="다른 설명입니다.",
                action="다른 행동입니다.",
            ),
        ],
    )
    display = product_guidance_display(group)
    assert display.title == "등록한 영양제"
    assert display.categories == ("생활관리 참고", "음식·음료 참고")
    # Whitespace-only variants merge; genuinely different wording is preserved.
    assert display.warning_titles == ("같은 제목", "다른 제목")
    assert display.summaries == ("같은 설명입니다.", "다른 설명입니다.")
    assert display.actions == ("같은 행동입니다.", "다른 행동입니다.")


def test_ingredient_disclaimer_is_emitted_once_and_stripped_from_every_body() -> None:
    """Would fail if the ingredient-only notice repeated per card inside the bodies."""
    group = GuidanceProductGroup(
        key="k",
        title="확인된 성분",
        cards=[
            _card(id="c1", title="첫 주의", summary=f"{COMMON_INGREDIENT_DISCLAIMER} 첫 설명입니다."),
            _card(id="c2", title="둘째 주의", summary=f"{COMMON_INGREDIENT_DISCLAIMER} 둘째 설명입니다."),
        ],
    )
    display = product_guidance_display(group)
    assert display.common_ingredient_disclaimer == COMMON_INGREDIENT_DISCLAIMER
    assert display.summaries == ("첫 설명입니다.", "둘째 설명입니다.")
    assert all(COMMON_INGREDIENT_DISCLAIMER not in summary for summary in display.summaries)


def test_distinct_specific_warnings_are_never_collapsed_into_one_entry() -> None:
    """Would fail if merging dropped a separate condition-specific caution."""
    group = GuidanceProductGroup(
        key="k",
        title="등록한 영양제",
        cards=[
            _card(id="c1", title="고칼슘혈증 주의", summary="고칼슘혈증이 있으면 상담하세요."),
            _card(id="c2", title="신장질환 주의", summary="신장질환이 있으면 상담하세요."),
        ],
    )
    display = product_guidance_display(group)
    assert display.warning_titles == ("고칼슘혈증 주의", "신장질환 주의")
    assert display.summaries == ("고칼슘혈증이 있으면 상담하세요.", "신장질환이 있으면 상담하세요.")


def test_body_merges_summary_and_action_paraphrases_without_losing_specific_facts() -> None:
    """Would fail if the UI kept duplicate summary/action boxes or dropped symptoms."""
    group = GuidanceProductGroup(
        key="k",
        title="비타민 C",
        cards=[
            _card(
                summary="비타민 C는 신장질환이 있는 경우 섭취 전 전문가와 상담할 필요가 있습니다.",
                action="신장질환이라면 비타민 C 섭취 전에 전문가와 상담하세요.",
            ),
            _card(
                summary="아세트아미노펜 복용 시 메스꺼움과 구토가 나타날 수 있습니다.",
                action="메스꺼움, 구토, 식욕 저하 또는 위장관 출혈이 나타나면 복용을 중단하고 상담하세요.",
            ),
        ],
    )
    display = product_guidance_display(group)
    assert len(display.body) == 3
    assert display.body[0] == "신장질환이라면 비타민 C 섭취 전에 전문가와 상담하세요."
    assert "아세트아미노펜" in display.body[1]
    assert "메스꺼움" in display.body[2]
    assert "구토" in display.body[2]
    assert "식욕 저하" in display.body[2]
    assert "위장관 출혈" in display.body[2]


def test_body_preserves_complementary_condition_and_medication_facts() -> None:
    """Would fail if near-duplicate heuristics discarded a distinct medication caveat."""
    group = GuidanceProductGroup(
        key="k",
        title="비타민 D",
        cards=[
            _card(summary="비타민 D를 과다 섭취하면 고칼슘혈증 위험이 있습니다.", action=" "),
            _card(summary=" ", action="고칼슘혈증 위험이 있거나 약을 복용 중이면 전문가와 상담하세요."),
        ],
    )
    display = product_guidance_display(group)
    assert display.body == (
        "비타민 D를 과다 섭취하면 고칼슘혈증 위험이 있습니다.",
        "고칼슘혈증 위험이 있거나 약을 복용 중이면 전문가와 상담하세요.",
    )


def test_body_deduplicates_the_c_and_d_consultation_paraphrases() -> None:
    """The screenshot-shaped consultation variants collapse to one body each."""
    group = GuidanceProductGroup(
        key="k",
        title="확인된 성분",
        cards=[
            _card(
                summary="비타민 C를 섭취하기 전에 신장질환이 있는 경우 전문가와 상담해야 합니다.",
                action="신장질환이 있는 경우 비타민 C 섭취 전에 전문가와 상담하십시오.",
            ),
            _card(
                summary="비타민 D를 섭취할 때 고칼슘혈증이 있는 경우 전문가와 상담해야 합니다.",
                action="고칼슘혈증이 있거나 의약품을 복용 중이라면 비타민 D 섭취 전에 전문가와 상담하십시오.",
            ),
        ],
    )
    display = product_guidance_display(group)
    assert display.body == (
        "신장질환이 있는 경우 비타민 C 섭취 전에 전문가와 상담하십시오.",
        "고칼슘혈증이 있거나 의약품을 복용 중이라면 비타민 D 섭취 전에 전문가와 상담하십시오.",
    )


# --- evidence grouped by source --------------------------------------------


def test_one_source_cited_for_two_quotes_shows_one_heading_with_both_quotes() -> None:
    """Would fail if a source's title and link repeated once per quote."""
    groups = group_guidance_evidence(
        [
            {"title": "공개 안내", "organization": "검증 기관", "safe_url": "https://e.test/a", "quote": "첫 인용"},
            {"title": "공개 안내", "organization": "검증 기관", "safe_url": "https://e.test/a", "quote": "둘째 인용"},
        ]
    )
    assert len(groups) == 1
    assert groups[0].title == "공개 안내"
    assert groups[0].url == "https://e.test/a"
    assert groups[0].quotes == ("첫 인용", "둘째 인용")


def test_distinct_urls_stay_separate_and_duplicate_or_empty_quotes_are_dropped() -> None:
    """Would fail if grouping merged two different documents from one organization."""
    groups = group_guidance_evidence(
        [
            {"title": "안내", "organization": "기관", "safe_url": "https://e.test/a", "quote": "인용"},
            {"title": "안내", "organization": "기관", "safe_url": "https://e.test/b", "quote": "다른 인용"},
            {"title": "안내", "organization": "기관", "safe_url": "https://e.test/a", "quote": "인용"},
            {"title": "안내", "organization": "기관", "safe_url": "https://e.test/a", "quote": "  "},
        ]
    )
    assert [group.url for group in groups] == ["https://e.test/a", "https://e.test/b"]
    assert groups[0].quotes == ("인용",)


def test_a_source_without_a_prevalidated_safe_url_is_grouped_without_any_link() -> None:
    """Would fail if a raw, unvalidated URL leaked into the rendered evidence link."""
    groups = group_guidance_evidence([{"title": "안내", "url": "javascript:alert(1)", "quote": "인용"}])
    assert len(groups) == 1
    assert groups[0].url is None


# --- generic overconsumption gate ------------------------------------------


_GENERIC_CARD = _card(
    id="rag:additional_precautions:supplement:202:1",
    title="칼슘 과다 섭취 주의",
    summary="칼슘을 과다 섭취하지 않도록 주의하세요.",
    action="섭취량을 확인하세요.",
)


def test_generic_overconsumption_card_is_kept_only_when_a_known_total_exceeds_the_limit() -> None:
    """Would fail if a generic 'too much' warning appeared without a computed excess."""
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(amount="3000")]) == [_GENERIC_CARD]


def test_generic_overconsumption_card_is_withheld_when_the_total_only_meets_the_limit() -> None:
    """Would fail if the comparison were >= instead of the required strict >."""
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(amount="2500")]) == []


def test_generic_overconsumption_card_is_withheld_when_the_total_or_limit_is_unknown() -> None:
    """Would fail if missing data were treated as a reason to warn anyway."""
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], []) == []
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(amount=None)]) == []
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(upper_limit_value=None)]) == []
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(unit=None)]) == []
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(calculation_status="UNAVAILABLE")]) == []
    # Two rows for one nutrient are ambiguous, so they are not a single known total.
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD], [_total(), _total(amount="10")]) == []


def test_withholding_only_removes_the_card_and_never_emits_a_safety_claim() -> None:
    """Would fail if an unknown total produced reassuring wording instead of silence."""
    other = _card(id="keep", title="보관 안내", summary="서늘한 곳에 보관하세요.", action="보관 상태를 확인하세요.")
    assert _filter_generic_overconsumption_cards([_GENERIC_CARD, other], []) == [other]


def test_specific_condition_and_interaction_warnings_survive_an_unknown_total() -> None:
    """Would fail if the upper-limit gate silenced a disease or combination caution."""
    hypercalcemia = _card(
        id="h",
        title="고칼슘혈증 주의",
        summary="칼슘을 과다 섭취하면 고칼슘혈증이 나타날 수 있습니다.",
        action="증상이 있으면 상담하세요.",
    )
    kidney = _card(
        id="k",
        title="신장질환 주의",
        summary="신장질환이 있으면 칼슘 과다 섭취에 주의하세요.",
        action="의사와 상담하세요.",
    )
    interaction = _card(
        id="i",
        title="병용 주의",
        summary="다른 제품과 함께 복용하면 칼슘을 과다 섭취할 수 있습니다.",
        action="병용 여부를 확인하세요.",
    )
    kept = _filter_generic_overconsumption_cards([hypercalcemia, kidney, interaction], [])
    assert kept == [hypercalcemia, kidney, interaction]


def test_a_card_that_never_mentions_overconsumption_is_not_touched_by_the_gate() -> None:
    """Would fail if the gate filtered ordinary guidance that it does not govern."""
    cards = [_card(id="a", title="복용 시점", summary="식사와 함께 드세요.", action="식사 시간을 확인하세요.")]
    assert _filter_generic_overconsumption_cards(cards, [_total(amount="1")]) == cards


# --- the same rules in the rendered email and HTML attachment ---------------

_LONG_BODIES = [f"{index}번째 주의 설명을 충분히 길게 적은 문장입니다." for index in range(1, 12)]


def _guidance_email_report() -> IntakeReportResponse:
    data = sample_email_report().model_dump()
    data["cards"]["lifestyle"] = [
        {
            "id": f"rag:lifestyle:supplement:2:{index}",
            "category": "생활관리 참고",
            "title": "같은 제목" if index < 3 else f"제목 {index}",
            "summary": body,
            "action": "같은 행동입니다." if index < 3 else f"행동 {index}입니다.",
            "related_item_ids": [2],
            "source_ids": ["rag-one", "rag-two"] if index == 1 else [],
        }
        for index, body in enumerate(_LONG_BODIES, start=1)
    ]
    data["cards"]["sources"] += [
        {
            "id": "rag-one",
            "title": "같은 문서",
            "organization": "검증 기관",
            "url": "https://guidance.test/doc",
            "evidence_level": "PUBLIC_GUIDE",
            "quote": "첫 번째 인용문입니다.",
            "chunk_id": "chunk-1",
        },
        {
            "id": "rag-two",
            "title": "같은 문서",
            "organization": "검증 기관",
            "url": "https://guidance.test/doc",
            "evidence_level": "PUBLIC_GUIDE",
            "quote": "두 번째 인용문입니다.",
            "chunk_id": "chunk-2",
        },
    ]
    return IntakeReportResponse.model_validate(data)


def test_attachment_shows_one_bounded_preview_and_keeps_the_full_body_behind_the_toggle() -> None:
    """Would fail if the HTML attachment lost body text or dropped the 200-character rule."""
    report = _guidance_email_report()
    markup, plain = render_intake_report_email(report, standalone=True)
    preview = product_guidance_display(
        GuidanceProductGroup(key="k", title="등록한 영양제", cards=report.cards.lifestyle)  # type: ignore[union-attr]
    ).body_preview
    assert preview is not None and len(preview) <= BODY_PREVIEW_LIMIT
    assert preview in markup
    assert "자세히 펼쳐보기" in markup
    # Every original paragraph survives the toggle untouched.
    assert all(body in markup for body in _LONG_BODIES)
    assert all(body in plain for body in _LONG_BODIES)


def test_inline_mail_body_keeps_the_full_text_because_it_cannot_rely_on_a_toggle() -> None:
    """Would fail if a mail client that drops <details> hid the guidance body."""
    markup, _ = render_intake_report_email(_guidance_email_report(), standalone=False)
    assert "<details" not in markup
    assert "자세히 펼쳐보기" not in markup
    assert all(body in markup for body in _LONG_BODIES)


def _guidance_section(markup: str) -> str:
    """The guidance section only, so nutrient and medication styling never masks a result."""
    start = markup.index("약·영양제별 주의사항 및 가이드")
    return markup[start : markup.index("<h2", start + 1)]


def test_email_renders_one_product_heading_merged_duplicates_and_grouped_evidence() -> None:
    """Would fail if the email repeated a title, an action, or a source heading per quote."""
    markup, plain = render_intake_report_email(_guidance_email_report(), standalone=True)
    guidance = _guidance_section(markup)
    # Exactly one product heading, at normal weight, and no bold weight in the group at all.
    assert guidance.count('font-weight:400">등록한 영양제</h3>') == 1
    assert guidance.count("</h3>") == 1
    assert "font-weight:700" not in guidance and "font-weight:600" not in guidance
    assert "같은 제목" not in guidance
    assert plain.count("같은 제목") == 0
    assert "같은 행동입니다." in guidance
    assert "할 일" not in guidance
    # One source heading and link inside the guidance evidence block, with each
    # distinct quote as its own bullet. The separate reference section is unchanged.
    start = guidance.index("<summary>근거 확인</summary>")
    evidence_block = guidance[start : guidance.index("</details>", start)]
    assert evidence_block.count('href="https://guidance.test/doc"') == 1
    assert evidence_block.count("<blockquote") == 2
    assert "첫 번째 인용문입니다." in plain and "두 번째 인용문입니다." in plain


# --- the editable docs stay true to the code -------------------------------


def _report_prompt_guide() -> str:
    return (files("ai_worker.llm.prompts") / "assets" / "REPORT_PROMPTS.md").read_text(encoding="utf-8")


def test_prompt_guide_states_the_real_report_rag_default() -> None:
    """Would fail if the default flipped and the editing guide kept the old value."""
    default = Config(_env_file=None).INTAKE_REPORT_RAG_ENABLED
    assert f"INTAKE_REPORT_RAG_ENABLED: bool = {default}" in _report_prompt_guide()


def test_prompt_guide_only_names_paths_that_exist() -> None:
    """Would fail if the guide pointed at a renamed or deleted owner of an output rule."""
    guide = _report_prompt_guide()
    repository_root = pathlib.Path(__file__).resolve().parents[3]
    referenced = set(re.findall(r"`((?:ai_worker|app|frontend)/[\w/.]+?\.\w+)`", guide))
    assert referenced, "the guide should name the files that own each output rule"
    assert [path for path in sorted(referenced) if not (repository_root / path).exists()] == []


def test_generic_consult_exclusion_stays_in_the_claims_prompt_with_its_exceptions() -> None:
    """Would fail if the boilerplate rule lost the carve-out that keeps real warnings."""
    claims = load_prompt_asset("intake_report_claims.md")
    assert "일반 상담 안내만 담고 있으면 그 문장만으로는 claim을 만들지 않습니다" in claims
    # Named reactions, named conditions, and severity wording are explicitly retained.
    for retained in ("고칼슘혈증", "신장질환", "중대", "중증", "응급"):
        assert retained in claims
