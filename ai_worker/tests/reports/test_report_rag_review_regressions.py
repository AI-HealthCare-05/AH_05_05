"""Regression cases from the independent report RAG review."""

import asyncio

import pytest
from langchain_core.runnables import RunnableLambda
from langsmith import get_tracing_context, tracing_context

from ai_worker.reports.report_rag_pipeline import ReportRagPipeline, ReportRagTarget
from ai_worker.reports.v11_cards import render_cards_markdown
from ai_worker.tests.reports.test_rag_guidance_acceptance import _draft
from ai_worker.tests.reports.test_report_rag_email import rag_email_fixture
from ai_worker.tests.reports.test_report_rag_pipeline import _chunk, _Retriever


def _claim(section, quote, summary=None):
    return {
        "section_id": section,
        "target_ids": ["supplement:1"],
        "title": "자료 안내",
        "summary": summary or quote,
        "action": "제품 안내를 확인하세요.",
        "evidence": [{"chunk_id": "chunk", "exact_quote": quote}],
        "grounded": True,
    }


def _pipeline(writer, *, verifier=None, sections=("lifestyle",), content="비타민 C의 제품 안내를 확인하세요."):
    return ReportRagPipeline(
        retriever=_Retriever([_chunk(point_id="chunk", document_id="doc", content=content)]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [
                {"section_id": section, "target_ids": ["supplement:1"], "queries": ["비타민 C"]} for section in sections
            ]
        },
        claim_writer=writer,
        verifier=verifier or (lambda value: value["candidate_claims"]),
        source_registry={"doc": ("source-doc", "Verified publisher")},
    )


def _targets():
    return [ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "비타민 C")]


def test_markdown_preserves_card_evidence_without_internal_section_status():
    cards = rag_email_fixture().cards
    markdown = render_cards_markdown(cards, _draft())
    source_index = next(index for index, source in enumerate(cards.sources, 1) if source.id == "rag-source")
    assert f"**근거:** [{source_index}]" in markdown
    assert "추가 안내 확인 상태" not in markdown
    assert "청크: fixture-chunk" in markdown
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in markdown


def test_reverification_keeps_unchanged_claim_when_same_quote_neighbor_is_removed():
    good = _claim("lifestyle", "비타민 C의 제품 안내를 확인하세요.")
    neighbor = {**good, "title": "제거할 다른 주장"}
    result = ReportRagPipeline._retain_unchanged_reverified_claims({"claims": [good, neighbor]}, {"claims": [good]})
    assert len(result.claims) == 1
    assert result.claims[0].title == good["title"]


@pytest.mark.asyncio
async def test_same_chunk_different_section_quotes_remain_bound_to_each_card():
    quotes = {"food_drink": "비타민 C의 음식 안내입니다.", "lifestyle": "비타민 C의 생활 안내입니다."}
    pipeline = _pipeline(
        lambda value: {"claims": [_claim(value["plan"][0]["section_id"], quotes[value["plan"][0]["section_id"]])]},
        sections=tuple(quotes),
        content=" ".join(quotes.values()),
    )
    result = await pipeline.run(targets=_targets())
    assert len(result.cards) == len(result.sources) == 2
    sources = {source.id: source for source in result.sources}
    for card in result.cards:
        assert sources[card.source_ids[0]].quote == card.summary


@pytest.mark.asyncio
async def test_same_guidance_in_two_sections_is_displayed_once():
    quote = "비타민 C의 제품 안내를 확인하세요."
    pipeline = _pipeline(
        lambda value: {"claims": [_claim(value["plan"][0]["section_id"], quote)]},
        sections=("lifestyle", "additional_precautions"),
        content=quote,
    )
    result = await pipeline.run(targets=_targets())
    assert len(result.cards) == 1
    assert len(result.sources) == 1
    assert result.metrics["verified_claim_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quote",
    [
        "비타민 C는 과량 섭취하지 않도록 주의할 것",
        "비타민 C는 신장질환이 있는 경우 섭취 전 전문가와 상담할 것",
        "비타민 C는 이상사례 발생 시 섭취를 중단하고 전문가와 상담할 것",
    ],
)
@pytest.mark.parametrize("section", ["food_drink", "lifestyle"])
async def test_nonclinical_sections_reject_general_precautions_even_when_model_approves(quote, section):
    result = await _pipeline(
        lambda _: {"claims": [_claim(section, quote)]},
        sections=(section,),
        content=quote,
    ).run(targets=_targets())
    assert not result.cards
    assert result.metrics["claim_rejected_section"] == 1


@pytest.mark.asyncio
async def test_planner_omitted_registered_target_never_marks_section_verified():
    quote = "비타민 C의 제품 안내를 확인하세요."
    result = await _pipeline(lambda _: {"claims": [_claim("lifestyle", quote)]}).run(
        targets=[*_targets(), ReportRagTarget("medication:1", 1, "MEDICATION", "다른 약")]
    )
    assert result.cards
    assert result.section_statuses[1].status == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize("summary", ["비타민 C는 4시간 간격입니다.", "비타민 C는 2일 간격입니다."])
async def test_changed_quantity_or_unit_cannot_pass_even_with_grounded_flag(summary):
    quote = "비타민 C는 2시간 간격입니다."
    result = await _pipeline(lambda _: {"claims": [_claim("lifestyle", quote, summary)]}, content=quote).run(
        targets=_targets()
    )
    assert not result.cards


@pytest.mark.asyncio
@pytest.mark.parametrize("vitamin,expected", [("B12", 1), ("B13", 0)])
async def test_vitamin_identifier_is_not_misread_as_quantity_with_korean_particle(vitamin, expected):
    quote = "파모티딘을 장기간 복용하는 경우 비타민 B12의 흡수가 감소되어 결핍될 수 있다."
    candidate = {
        **_claim("additional_precautions", quote),
        "title": f"파모티딘 장기 복용 시 비타민 {vitamin} 결핍 가능성",
        "summary": f"파모티딘을 장기간 복용하면 비타민 {vitamin}의 흡수가 감소하여 결핍될 수 있어요.",
        "action": f"파모티딘을 장기간 복용할 경우 비타민 {vitamin} 결핍에 주의하세요.",
    }
    pipeline = _pipeline(lambda _: {"claims": [candidate]}, sections=("additional_precautions",), content=quote)
    result = await pipeline.run(targets=[ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "파모티딘")])
    assert len(result.cards) == expected


@pytest.mark.asyncio
async def test_second_verifier_edit_is_not_published():
    quote = "비타민 C의 제품 안내를 확인하세요."
    calls = 0

    def edit(value):
        nonlocal calls
        calls += 1
        claim = {**value["candidate_claims"]["claims"][0], "title": f"수정 {calls}"}
        return {"claims": [claim]}

    result = await _pipeline(lambda _: {"claims": [_claim("lifestyle", quote)]}, verifier=edit).run(targets=_targets())
    assert calls == 2
    assert not result.cards


@pytest.mark.asyncio
async def test_lcel_payload_tracing_is_disabled_inside_parent_trace():
    observed = []

    async def writer(value):
        observed.append(get_tracing_context()["enabled"])
        return {"claims": []}

    with tracing_context(enabled=True):
        await _pipeline(RunnableLambda(writer)).run(targets=_targets())
    assert observed == [False]


@pytest.mark.asyncio
async def test_completed_section_survives_other_section_deadline():
    quote = "비타민 C의 음식 안내를 확인하세요."

    async def writer(value):
        section = value["plan"][0]["section_id"]
        if section == "lifestyle":
            await asyncio.sleep(10)
        return {"claims": [_claim(section, quote)]}

    result = await _pipeline(writer, sections=("food_drink", "lifestyle"), content=quote).run(
        targets=_targets(), remaining_seconds=0.05
    )
    assert len(result.cards) == 1
    assert result.section_statuses[0].status == "verified"
    assert result.section_statuses[1].status == "unverified"


@pytest.mark.asyncio
async def test_external_cancellation_drains_section_work():
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def writer(value):
        entered.set()
        try:
            await asyncio.sleep(10)
        finally:
            cleaned.set()

    task = asyncio.create_task(_pipeline(writer).run(targets=_targets()))
    await asyncio.wait_for(entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
