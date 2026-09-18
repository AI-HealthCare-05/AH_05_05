"""A malformed or rewritten neighbor must not erase a verified report claim."""

import asyncio
import json

import httpx
import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ai_worker.reports import report_rag_pipeline
from ai_worker.reports.report_rag_pipeline import ReportRagPipeline
from ai_worker.tests.reports.test_report_rag_pipeline import _chunk, _Retriever
from ai_worker.tests.reports.test_report_rag_review_regressions import _pipeline, _targets
from ai_worker.use_cases.generate_intake_report import _safe_rag_metrics

QUOTE = "비타민 C의 제품 안내를 확인하세요."


def test_rag_runtime_metrics_keep_only_known_integer_counters():
    metrics = _safe_rag_metrics(
        {
            "query_count": 3,
            "section_lifestyle_verified_card_count": 25,
            "section_lifestyle_split_chunk_count": 1,
            "claim_rejected_quote": 2,
            "unexpected_metric": 99,
            "section_lifestyle_unknown_count": 7,
            "section_lifestyle_drafted_claim_count": True,
        }
    )

    assert metrics == {
        "query_count": 3,
        "section_lifestyle_verified_card_count": 25,
        "section_lifestyle_split_chunk_count": 1,
        "claim_rejected_quote": 2,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [7, 19, 25])
async def test_all_verified_guidance_is_returned_without_card_count_truncation(count):
    quotes = [f"비타민 C 안내 항목 {i}를 확인하세요." for i in range(count)]
    claims = [
        claim(summary=quote, action=quote, evidence=[{"chunk_id": "chunk", "exact_quote": quote}]) for quote in quotes
    ]
    result = await _pipeline(lambda _: {"claims": claims}, content=" ".join(quotes)).run(targets=_targets())
    assert len(result.cards) == count
    assert len(result.sources) == count
    assert result.metrics["verified_claim_count"] == count
    assert result.metrics["section_lifestyle_retrieved_chunk_count"] == 1
    assert result.metrics["section_lifestyle_filtered_chunk_count"] == 1
    assert result.metrics["section_lifestyle_drafted_claim_count"] == count
    assert result.metrics["section_lifestyle_verifier_omitted_claim_count"] == 0
    assert result.metrics["section_lifestyle_verified_card_count"] == count


def claim(**changes):
    return {
        "section_id": "lifestyle",
        "target_ids": ["supplement:1"],
        "title": "유지할 안내",
        "summary": QUOTE,
        "action": "제품 안내를 확인하세요.",
        "evidence": [{"chunk_id": "chunk", "exact_quote": QUOTE}],
        "grounded": True,
        **changes,
    }


@pytest.mark.asyncio
async def test_every_context_batch_preserves_distinct_verified_guidance():
    chunks = []
    writer_batches = []
    for index in range(5):
        quote = f"비타민 C 배치 안내 {index}를 확인하세요."
        chunks.append(
            _chunk(
                point_id=f"batch-{index}",
                document_id=f"batch-doc-{index}",
                content=("x" * 5_900) + "|" + quote,
            )
        )

    def writer(value):
        writer_batches.append([chunk["chunk_id"] for chunk in value["chunks"]])
        return {
            "claims": [
                claim(
                    title="배치 안내",
                    summary=chunk["content"].rsplit("|", 1)[1],
                    action=chunk["content"].rsplit("|", 1)[1],
                    evidence=[{"chunk_id": chunk["chunk_id"], "exact_quote": chunk["content"].rsplit("|", 1)[1]}],
                )
                for chunk in value["chunks"]
            ]
        }

    pipeline = ReportRagPipeline(
        retriever=_Retriever(chunks),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "lifestyle", "target_ids": ["supplement:1"], "queries": ["비타민 C"]}]
        },
        claim_writer=writer,
        verifier=lambda value: value["candidate_claims"],
        source_registry={
            chunk.metadata.document_id: (chunk.metadata.source_id, chunk.metadata.provider) for chunk in chunks
        },
    )

    result = await pipeline.run(targets=_targets())

    assert len(result.cards) == 5
    assert writer_batches == [["batch-0", "batch-1", "batch-2"], ["batch-3", "batch-4"]]
    assert result.metrics["section_lifestyle_retrieved_chunk_count"] == 5
    assert result.metrics["section_lifestyle_filtered_chunk_count"] == 5
    assert result.metrics["section_lifestyle_drafted_claim_count"] == 5
    assert result.metrics["section_lifestyle_verified_card_count"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "exception"])
async def test_completed_context_batch_survives_a_slower_batch_timeout(failure):
    fast_quote = "비타민 C 빠른 배치 안내를 확인하세요."
    slow_quote = "비타민 C 느린 배치 안내를 확인하세요."
    chunks = [
        _chunk(point_id="fast", document_id="fast-doc", content=("x" * 11_900) + "|" + fast_quote),
        _chunk(point_id="slow", document_id="slow-doc", content=("y" * 11_900) + "|" + slow_quote),
    ]
    cancelled = asyncio.Event()

    async def writer(value):
        chunk = value["chunks"][0]
        if chunk["chunk_id"] == "slow":
            if failure == "exception":
                raise RuntimeError("synthetic batch failure")
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.set()
        quote = chunk["content"].rsplit("|", 1)[1]
        return {
            "claims": [
                claim(summary=quote, action=quote, evidence=[{"chunk_id": chunk["chunk_id"], "exact_quote": quote}])
            ]
        }

    pipeline = ReportRagPipeline(
        retriever=_Retriever(chunks),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "lifestyle", "target_ids": ["supplement:1"], "queries": ["비타민 C"]}]
        },
        claim_writer=writer,
        verifier=lambda value: value["candidate_claims"],
        source_registry={
            chunk.metadata.document_id: (chunk.metadata.source_id, chunk.metadata.provider) for chunk in chunks
        },
    )

    result = await pipeline.run(targets=_targets(), remaining_seconds=0.3)

    assert [card.summary for card in result.cards] == [fast_quote]
    assert cancelled.is_set() is (failure == "timeout")
    assert result.metrics["section_lifestyle_verified_card_count"] == 1
    metric = "batch_incomplete_count" if failure == "timeout" else "batch_failed_count"
    assert result.metrics[f"section_lifestyle_{metric}"] == 1
    assert result.section_statuses[1].status == "partial"
    assert result.section_statuses[1].reason == (
        "일부 근거 배치 검증 시간 초과" if failure == "timeout" else "일부 근거 배치 검증 실패"
    )


@pytest.mark.asyncio
async def test_long_evidence_chunk_is_split_without_losing_its_ending_claim():
    ending_quote = "비타민 C 긴 원문의 마지막 안내를 확인하세요."
    content = "시작-" + ("중간 문장. " * 8_000) + ending_quote
    chunk = _chunk(point_id="long", document_id="long-doc", content=content)
    seen_contents = []

    def writer(value):
        seen_contents.extend(item["content"] for item in value["chunks"])
        return (
            {
                "claims": [
                    claim(
                        summary=ending_quote,
                        action=ending_quote,
                        evidence=[{"chunk_id": "long", "exact_quote": ending_quote}],
                    )
                ]
            }
            if any(ending_quote in item["content"] for item in value["chunks"])
            else {"claims": []}
        )

    pipeline = ReportRagPipeline(
        retriever=_Retriever([chunk]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "lifestyle", "target_ids": ["supplement:1"], "queries": ["비타민 C"]}]
        },
        claim_writer=writer,
        verifier=lambda value: value["candidate_claims"],
        source_registry={"long-doc": (chunk.metadata.source_id, chunk.metadata.provider)},
    )

    result = await pipeline.run(targets=_targets())

    assert len(seen_contents) > 1
    assert content[:100] in seen_contents[0]
    assert content[len(content) // 2 : len(content) // 2 + 100] in "\n".join(seen_contents)
    assert ending_quote in seen_contents[-1]
    assert [card.summary for card in result.cards] == [ending_quote]
    assert result.metrics["section_lifestyle_split_chunk_count"] == 1
    assert result.metrics["section_lifestyle_batch_forwarded_chunk_count"] == len(seen_contents)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["draft", "verify"])
async def test_malformed_claim_does_not_erase_valid_neighbor(stage):
    good = claim()
    bad = claim(title="잘못된 근거", evidence=[{"chunk_id": "chunk"}])

    def writer(_):
        return {"claims": [good, bad] if stage == "draft" else [good]}

    def verifier(value):
        return {"claims": [good, bad]} if stage == "verify" else value["candidate_claims"]

    result = await _pipeline(writer, verifier=verifier).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert result.sources[0].quote == QUOTE
    assert result.metrics[f"claim_rejected_{stage}_schema"] == 1


@pytest.mark.asyncio
async def test_omission_does_not_reverify_or_restore_rejected_neighbor():
    calls = []
    good, bad = claim(), claim(title="제외할 안내")

    def verifier(value):
        calls.append(value)
        return {"claims": [good]}

    result = await _pipeline(lambda _: {"claims": [good, bad]}, verifier=verifier).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert len(calls) == 1
    assert result.metrics["section_lifestyle_drafted_claim_count"] == 2
    assert result.metrics["section_lifestyle_verifier_omitted_claim_count"] == 1
    assert result.metrics["section_lifestyle_verified_card_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_failure", ["exception", "malformed", "rewrite"])
async def test_repair_failure_preserves_already_verified_claim(repair_failure):
    good, bad = claim(), claim(title="수정 전")
    calls = []

    def verifier(value):
        calls.append(value)
        if len(calls) == 1:
            return {"claims": [good, claim(title="수정 후")]}
        if repair_failure == "exception":
            raise RuntimeError("synthetic failure")
        if repair_failure == "malformed":
            return {"claims": [claim(title="수정 후", evidence=[])]}
        return {"claims": [claim(title="다시 수정")]}

    result = await _pipeline(lambda _: {"claims": [good, bad]}, verifier=verifier).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert len(calls) == 2
    assert [item["title"] for item in calls[1]["candidate_claims"]["claims"]] == ["수정 후"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"evidence": [{"chunk_id": "chunk", "exact_quote": "없는 인용"}]}, "quote"),
        ({"evidence": [{"chunk_id": "missing", "exact_quote": QUOTE}]}, "source"),
        ({"target_ids": ["medication:1"]}, "target"),
        ({"grounded": False}, "ungrounded"),
    ],
)
async def test_invalid_evidence_is_rejected_individually_with_reason(changes, reason):
    result = await _pipeline(lambda _: {"claims": [claim(), claim(title="제외", **changes)]}).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert result.metrics[f"claim_rejected_{reason}"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("repair_quote", [True, False])
async def test_verifier_receives_quote_mismatch_without_dropping_valid_neighbor(repair_quote):
    bad_quote = "비타민 C의 제품 안내를 확인하세요. 함께 확인하세요."
    content = QUOTE + " 원문의 중간 문장입니다. 함께 확인하세요."
    good = claim()
    candidate = claim(title="인용 교정 대상", evidence=[{"chunk_id": "chunk", "exact_quote": bad_quote}])
    calls = []

    def verifier(value):
        calls.append(value)
        if len(calls) == 1:
            assert value.get("server_checks") == [{"claim_index": 1, "evidence_index": 0, "code": "quote_not_in_chunk"}]
            if repair_quote:
                return {"claims": [good, {**candidate, "evidence": [{"chunk_id": "chunk", "exact_quote": QUOTE}]}]}
        return value["candidate_claims"]

    result = await _pipeline(lambda _: {"claims": [good, candidate]}, verifier=verifier, content=content).run(
        targets=_targets()
    )
    # Same instruction/source is intentionally deduplicated after both claims
    # pass. The stage count proves correction, not a restored rejected claim.
    assert result.metrics["section_lifestyle_verified_card_count"] == (2 if repair_quote else 1)
    assert len(calls) == (2 if repair_quote else 1)
    assert all(source.quote in content for source in result.sources)
    assert result.cards[0].title == good["title"]


@pytest.mark.asyncio
async def test_legacy_mismatched_arrays_are_not_silently_zipped():
    old = claim(title="구형 불일치")
    old.pop("evidence")
    old.update(chunk_ids=["chunk"], exact_quotes=[QUOTE, "다른 인용"])
    result = await _pipeline(lambda _: {"claims": [claim(), old]}).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert result.metrics["claim_rejected_draft_schema"] == 1


@pytest.mark.asyncio
async def test_blank_text_does_not_abort_valid_neighbor():
    result = await _pipeline(lambda _: {"claims": [claim(), claim(title="  ")]}).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]


@pytest.mark.asyncio
async def test_each_section_has_at_most_one_repair():
    calls = {}

    def writer(value):
        return {"claims": [claim(section_id=value["plan"][0]["section_id"])]}

    def verifier(value):
        item = value["candidate_claims"]["claims"][0]
        section = item["section_id"]
        calls[section] = calls.get(section, 0) + 1
        return {"claims": [{**item, "title": "수정된 안내"}]}

    result = await _pipeline(writer, verifier=verifier, sections=("food_drink", "lifestyle")).run(targets=_targets())
    assert len(result.cards) == 1  # identical verified guidance is displayed once across sections
    assert calls == {"food_drink": 2, "lifestyle": 2}


@pytest.mark.asyncio
async def test_repair_timeout_preserves_verified_neighbor_and_drains_call():
    good, pending = claim(), claim(title="수정 전")
    calls = 0
    drained = asyncio.Event()

    async def verifier(value):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"claims": [good, claim(title="수정 후")]}
        try:
            await asyncio.sleep(10)
        finally:
            drained.set()

    result = await _pipeline(lambda _: {"claims": [good, pending]}, verifier=verifier).run(
        targets=_targets(),
        remaining_seconds=0.2,
    )
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert calls == 2
    assert drained.is_set()
    assert result.metrics["claim_rejected_repair_failed"] == 1


@pytest.mark.asyncio
async def test_real_lcel_json_parser_preserves_good_claim_beside_malformed_response(monkeypatch):
    """Exercise the real structured-output adapter, replacing only HTTP I/O."""

    def check_required_fields(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert set(node["required"]) == set(node["properties"])
                assert node["additionalProperties"] is False
            for child in node.values():
                check_required_fields(child)
        elif isinstance(node, list):
            for child in node:
                check_required_fields(child)

    def respond(request):
        body = json.loads(request.content)
        check_required_fields(body["response_format"]["json_schema"]["schema"])
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"claims": [claim(), claim(evidence=[])]}),
                        },
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        monkeypatch.setattr(report_rag_pipeline, "ChatOpenAI", lambda **kw: ChatOpenAI(**kw, http_async_client=http))
        monkeypatch.setattr(report_rag_pipeline, "load_report_rag_source_registry", lambda: {})
        live_chain = report_rag_pipeline.build_openai_report_rag_pipeline(
            retriever=None,
            dataset_version="test",
            model="gpt-4o",
            api_key=SecretStr("synthetic-test-key"),
        )._claim_writer
        result = await _pipeline(live_chain).run(targets=_targets())
    assert [card.title for card in result.cards] == ["유지할 안내"]
    assert result.metrics["claim_rejected_draft_schema"] == 1
