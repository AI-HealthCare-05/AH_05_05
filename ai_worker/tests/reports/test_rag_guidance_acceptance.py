"""Acceptance coverage for the opt-in, source-locked report guidance RAG mode.

These tests use deterministic planner/claim/verifier/retriever doubles, but
exercise the public RAG pipeline, the established card generator, and the
production Markdown renderer together.  No network or live model is used.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda

from ai_worker.core.config import Config
from ai_worker.llm.generators.intake_report_cards_generator import OpenAIIntakeReportCardsGenerator
from ai_worker.reports.report_rag_pipeline import (
    RagIntakeReportCardsGenerator,
    ReportRagPipeline,
    ReportRagTarget,
)
from ai_worker.reports.v11_cards import (
    build_canonical_card_plan,
    build_evidence_catalog,
    render_cards,
    render_cards_markdown,
)
from ai_worker.schemas.intake_report import (
    IntakeReportChartData,
    IntakeReportCurrentStackItem,
    IntakeReportDataAvailability,
    IntakeReportDraft,
    IntakeReportEvidenceLevel,
    IntakeReportExecutiveSummary,
    IntakeReportItemType,
    IntakeReportNutrientTotal,
    IntakeReportReviewCard,
    IntakeReportReviewCardType,
    IntakeReportSource,
    IntakeReportUnverifiedItem,
    IntakeReportUnverifiedItemType,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeSearchMode,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
    RetrievedKnowledgeChunk,
)
from ai_worker.schemas.medication_chat import MedicationGuideFact

DATASET_VERSION = "rag-acceptance-v1"
TARGET_ID = "supplement:202"
TARGET_NAME = "비타민 D"


def _guide() -> MedicationGuideFact:
    return MedicationGuideFact(
        medication_guide_id=1101,
        item_seq="acceptance-medication",
        product_name="아세트아미노펜",
        manufacturer_name="검증 제조사",
        efficacy="통증을 완화합니다.",
        usage_instructions="식후 물과 함께 복용하세요.",
        pre_use_warning="복용 전 의사와 상담하세요.",
        precautions="졸음이 올 수 있습니다.",
        drug_food_interactions="",
        adverse_reactions="메스꺼움이 나타날 수 있습니다.",
        storage_instructions="실온 보관하세요.",
    )


def _draft() -> IntakeReportDraft:
    return IntakeReportDraft(
        data_availability=IntakeReportDataAvailability(
            active_medication_count=1,
            active_supplement_count=1,
            approved_interaction_rule_available=True,
        ),
        executive_summary=IntakeReportExecutiveSummary(
            reviewed_product_count=2,
            interaction_check_count=1,
            summary="등록한 제품과 확인 가능한 근거를 검토했습니다.",
        ),
        current_stack=[
            IntakeReportCurrentStackItem(
                item_type=IntakeReportItemType.MEDICATION,
                item_id=101,
                product_name="아세트아미노펜",
                registered_intake_info="1정 · 1일 1회",
                evidence_level=IntakeReportEvidenceLevel.REGISTERED_INTAKE,
            ),
            IntakeReportCurrentStackItem(
                item_type=IntakeReportItemType.SUPPLEMENT,
                item_id=202,
                product_name=TARGET_NAME,
                ingredient_summary="칼슘 50mg · 비타민 D",
                registered_intake_info="1정 · 1일 1회",
                evidence_level=IntakeReportEvidenceLevel.REGISTERED_INTAKE,
            ),
        ],
        review_cards=[
            IntakeReportReviewCard(
                card_type=IntakeReportReviewCardType.INTERACTION,
                title="승인된 상호작용 확인",
                summary="등록한 약과 영양제의 병용을 확인하세요.",
                related_items=["아세트아미노펜", TARGET_NAME],
                check_item="전문가에게 병용 가능 여부를 확인하세요.",
                evidence_level=IntakeReportEvidenceLevel.APPROVED_RULE,
                sources=[
                    IntakeReportSource(
                        title="승인 상호작용 규칙",
                        organization="검증 기관",
                        url="https://rules.acceptance.test/interaction",
                        evidence_level=IntakeReportEvidenceLevel.APPROVED_RULE,
                    )
                ],
            )
        ],
        nutrient_totals=[
            IntakeReportNutrientTotal(
                nutrient_name="칼슘",
                daily_total="50 mg",
                included_product_names=[TARGET_NAME],
                calculation_status="LABEL_SCHEDULE",
                amount="50",
                unit="mg",
                reference_value="100",
                reference_kind="RNI",
                reference_percent="50",
            )
        ],
        chart_data=IntakeReportChartData(
            medication_count=1,
            supplement_count=1,
            interaction_card_count=1,
        ),
        unverified_items=[
            IntakeReportUnverifiedItem(
                item_type=IntakeReportUnverifiedItemType.MISSING_AMOUNT,
                title="함량 확인 필요",
                message="등록한 제품의 일부 함량은 확인하지 못했습니다.",
                related_items=[TARGET_NAME],
                next_step="제품 라벨의 1회 함량을 확인하세요.",
            )
        ],
        deterministic_markdown="# 이전 보고서",
        guide_evidence=[_guide()],
        guide_item_bindings={101: 1101},
        profile_label="성인 기준",
        basis_note="확인된 등록 정보와 제품 안내 기준",
    )


def _chunk(
    *,
    point_id: str = "chunk-safe",
    document_id: str = "doc-safe",
    content: str = "비타민 D는 식사와 함께 섭취할 수 있습니다.",
    source_url: str | None = "https://sources.acceptance.test/doc-safe",
    source_id: str | None = None,
    provider: str = "공개 검증 기관",
    dataset_version: str = DATASET_VERSION,
    score: float = 0.95,
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        chunk_id=(point_id + "x" * 64)[:64],
        point_id=point_id,
        content=content,
        embedding_text=content,
        token_count=4,
        similarity_score=score,
        search_mode=KnowledgeSearchMode.DENSE,
        metadata=KnowledgeChunkMetadata(
            source_id=source_id or f"source-{document_id}",
            document_id=document_id,
            title=f"{document_id} 공개 안내",
            provider=provider,
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version=dataset_version,
            source_url=source_url,
            evidence_level=KnowledgeEvidenceLevel.SYSTEMATIC_REVIEW,
            study_population=KnowledgeStudyPopulation.HUMAN,
            section_type=KnowledgeSectionType.CONCLUSION,
            content_kind=KnowledgeContentKind.TEXT,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=(point_id + "h" * 64)[:64],
        ),
    )


class _RecordingRetriever:
    def __init__(
        self,
        chunks: list[RetrievedKnowledgeChunk],
        *,
        delay_seconds: float = 0,
        fail_queries: frozenset[str] = frozenset(),
    ) -> None:
        self.chunks = chunks
        self.delay_seconds = delay_seconds
        self.fail_queries = fail_queries
        self.plans = []
        self.active = 0
        self.max_active = 0

    async def search_with_diagnostics(self, *, execution_plan):
        self.plans.append(execution_plan)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            if execution_plan.query_plan.original_query in self.fail_queries:
                raise RuntimeError("deterministic retrieval failure")
            return SimpleNamespace(chunks=list(self.chunks))
        finally:
            self.active -= 1


class _NoOpSpacingClient:
    async def ainvoke(self, messages):
        fields = json.loads(messages[1].content)["fields"]
        return {
            "repairs": [
                {
                    "key": field["key"],
                    "chunks": [{"index": chunk["index"], "spaceAfter": []} for chunk in field["chunks"]],
                }
                for field in fields
            ]
        }


def _valid_claim(
    *,
    target_ids: list[str] | None = None,
    summary: str = "비타민 D는 식사와 함께 섭취할 수 있습니다.",
    quote: str | None = None,
    chunk_id: str = "chunk-safe",
    grounded: bool = True,
) -> dict[str, object]:
    return {
        "section_id": "lifestyle",
        "target_ids": target_ids or [TARGET_ID],
        "title": "식사와 함께 확인",
        "summary": summary,
        "action": "제품 안내를 확인하세요.",
        "evidence": [{"chunk_id": chunk_id, "exact_quote": quote if quote is not None else summary}],
        "grounded": grounded,
    }


def _pipeline(
    *,
    chunk: RetrievedKnowledgeChunk,
    claim: dict[str, object],
    retriever: _RecordingRetriever | None = None,
    planner: object | None = None,
    timeout_seconds: float = 1.0,
    source_registry: dict[str, tuple[str, str]] | None = None,
) -> tuple[ReportRagPipeline, _RecordingRetriever]:
    retriever = retriever or _RecordingRetriever([chunk])
    planner = planner or (
        lambda _input: {
            "sections": [
                {
                    "section_id": "lifestyle",
                    "target_ids": [TARGET_ID],
                    "queries": ["비타민 D 생활관리"],
                }
            ]
        }
    )
    registry = source_registry or {chunk.metadata.document_id: (chunk.metadata.source_id, chunk.metadata.provider)}
    planner_chain = planner if hasattr(planner, "ainvoke") else RunnableLambda(planner)
    claim_chain = RunnableLambda(lambda _input: {"claims": [claim]})
    verifier_chain = RunnableLambda(lambda value: value["candidate_claims"])
    return (
        ReportRagPipeline(
            retriever=retriever,
            dataset_version=DATASET_VERSION,
            planner=planner_chain,
            claim_writer=claim_chain,
            verifier=verifier_chain,
            timeout_seconds=timeout_seconds,
            source_registry=registry,
        ),
        retriever,
    )


def _targets(*, include_medication: bool = True) -> list[ReportRagTarget]:
    targets = [ReportRagTarget(id=TARGET_ID, item_id=202, item_type="SUPPLEMENT", name=TARGET_NAME)]
    if include_medication:
        targets.insert(
            0,
            ReportRagTarget(
                id="medication:101",
                item_id=101,
                item_type="MEDICATION",
                name="아세트아미노펜",
            ),
        )
    return targets


def _base_generator() -> OpenAIIntakeReportCardsGenerator:
    return OpenAIIntakeReportCardsGenerator(
        model="offline-acceptance",
        spacing_client=_NoOpSpacingClient(),
        include_fixed_lifestyle_guidance=False,
    )


def test_rag_is_opt_in_and_disabling_fixed_guidance_preserves_legacy_cards() -> None:
    draft = _draft()

    assert Config(_env_file=None).INTAKE_REPORT_RAG_ENABLED is False

    legacy_catalog = build_evidence_catalog(draft)
    rag_catalog = build_evidence_catalog(draft, include_fixed_lifestyle_guidance=False)
    legacy_cards = render_cards(build_canonical_card_plan(legacy_catalog), legacy_catalog, draft)
    rag_base_cards = render_cards(build_canonical_card_plan(rag_catalog), rag_catalog, draft)

    assert "food:calcium" in {card.id for card in legacy_cards.lifestyle}
    assert "food:calcium" not in {card.id for card in rag_base_cards.lifestyle}
    assert [card.product_name for card in rag_base_cards.medications] == ["아세트아미노펜"]
    assert "통증을 완화합니다." in rag_base_cards.medications[0].efficacy.text
    assert rag_base_cards.interactions[0].evidence_level == "APPROVED_RULE"
    markdown = render_cards_markdown(rag_base_cards, draft)
    assert "50 mg" in markdown
    assert "승인된 상호작용 확인" in markdown
    assert "함량 확인 필요" in markdown
    assert "두부" not in markdown


@pytest.mark.asyncio
async def test_generator_preserves_confirmed_medication_ingredients_for_rag(monkeypatch) -> None:
    draft = _draft()
    medication = next(item for item in draft.current_stack if item.item_type.value == "MEDICATION")
    draft = draft.model_copy(
        update={
            "current_stack": [
                item.model_copy(update={"ingredient_aliases": ["확정 성분 A", "확정 성분 B"]})
                if item is medication
                else item
                for item in draft.current_stack
            ]
        }
    )
    pipeline, _ = _pipeline(chunk=_chunk(), claim=_valid_claim())
    original_run = pipeline.run
    observed = []

    async def capture(**kwargs):
        observed.extend(kwargs["targets"])
        return await original_run(**kwargs)

    monkeypatch.setattr(pipeline, "run", capture)
    generator = RagIntakeReportCardsGenerator(pipeline=pipeline, base_generator=_base_generator())
    await generator.generate(draft=draft, remaining_seconds=2.0)
    target = next(target for target in observed if target.item_type == "MEDICATION")
    assert "확정 성분 A" in target.aliases
    assert "확정 성분 B" in target.aliases


@pytest.mark.asyncio
async def test_enabled_mode_renders_verified_cited_guidance_without_dropping_registered_output() -> None:
    draft = _draft()
    chunk = _chunk()
    pipeline, retriever = _pipeline(chunk=chunk, claim=_valid_claim())
    generator = RagIntakeReportCardsGenerator(pipeline=pipeline, base_generator=_base_generator())

    outcome = await generator.generate(draft=draft, remaining_seconds=2.0)

    assert outcome.cards is not None
    assert outcome.rag_evidence_available is True
    assert outcome.rag_partial is True  # medication/other guidance sections remain unverified
    assert [card.product_name for card in outcome.cards.medications] == ["아세트아미노펜"]
    assert "통증을 완화합니다." in outcome.report_markdown
    assert "승인된 상호작용 확인" in outcome.report_markdown
    assert "50 mg" in outcome.report_markdown
    assert "함량 확인 필요" in outcome.report_markdown
    assert "두부" not in outcome.report_markdown

    rag_cards = [card for card in outcome.cards.lifestyle if card.id.startswith("rag:")]
    assert len(rag_cards) == 1
    assert rag_cards[0].summary == "비타민 D는 식사와 함께 섭취할 수 있습니다."
    assert rag_cards[0].related_item_ids == [202]
    source = next(source for source in outcome.cards.sources if source.id == "rag:source-doc-safe:chunk-safe:4b5afb5f")
    assert source.quote == chunk.content
    assert source.chunk_id == "chunk-safe"
    assert source.dataset_version == DATASET_VERSION
    assert any(
        status.section_id == "lifestyle"
        and status.status == "partial"
        and status.reason == "일부 등록 항목의 근거만 확인됨"
        for status in outcome.cards.section_statuses
    )
    assert retriever.plans[0].include_patient_context is False
    assert outcome.report_markdown == render_cards_markdown(outcome.cards, draft)


@pytest.mark.asyncio
async def test_partial_target_coverage_keeps_verified_card_and_marks_section_partial() -> None:
    chunk = _chunk()
    claim = _valid_claim(target_ids=[TARGET_ID])
    pipeline, _retriever = _pipeline(
        chunk=chunk,
        claim=claim,
        planner=lambda _input: {
            "sections": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["medication:101", TARGET_ID],
                    "queries": ["등록 목록 생활관리"],
                }
            ]
        },
    )

    result = await pipeline.run(targets=_targets(include_medication=True))

    assert len(result.cards) == 1
    lifestyle_status = next(status for status in result.section_statuses if status.section_id == "lifestyle")
    assert lifestyle_status.status == "partial"
    assert lifestyle_status.reason == "일부 등록 항목의 근거만 확인됨"
    assert lifestyle_status.target_item_ids == [101, 202]
    assert result.rag_evidence_available is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["fake_source", "wrong_target", "bad_quote", "numeric_injection"],
)
async def test_rag_rejects_untrusted_claim_variants(case: str) -> None:
    if case == "fake_source":
        chunk = _chunk(source_id="source-not-in-registry")
        source_registry = {chunk.metadata.document_id: ("source-trusted", chunk.metadata.provider)}
        claim = _valid_claim()
    elif case == "wrong_target":
        chunk = _chunk()
        source_registry = None
        claim = _valid_claim(target_ids=["supplement:999"])
    elif case == "bad_quote":
        chunk = _chunk()
        source_registry = None
        claim = _valid_claim(quote="문서에 없는 문장입니다.")
    else:
        chunk = _chunk(content="비타민 D 정보: 매일 5000mg으로 늘리세요.")
        source_registry = None
        claim = _valid_claim(summary="매일 5000mg으로 늘리세요.")

    pipeline, _retriever = _pipeline(
        chunk=chunk,
        claim=claim,
        source_registry=source_registry,
    )
    result = await pipeline.run(
        targets=[ReportRagTarget(id=TARGET_ID, item_id=202, item_type="SUPPLEMENT", name=TARGET_NAME)]
    )

    assert result.cards == []
    assert result.sources == []
    assert result.rag_evidence_available is False
    assert all(status.status != "verified" for status in result.section_statuses)


@pytest.mark.asyncio
async def test_rag_rejects_malformed_source_url_even_when_registry_identity_matches() -> None:
    chunk = _chunk(source_url="javascript:alert(1)")
    pipeline, _retriever = _pipeline(chunk=chunk, claim=_valid_claim())

    result = await pipeline.run(targets=_targets(include_medication=False))

    assert result.cards == []
    assert result.sources == []
    assert result.rag_evidence_available is False


@pytest.mark.asyncio
async def test_rag_timeout_returns_partial_outcome_without_losing_base_cards() -> None:
    chunk = _chunk()

    async def slow_planner(_input):
        await asyncio.sleep(0.05)
        return {"sections": [{"section_id": "lifestyle", "target_ids": [TARGET_ID], "queries": ["비타민 D 생활관리"]}]}

    pipeline, _retriever = _pipeline(
        chunk=chunk,
        claim=_valid_claim(),
        planner=slow_planner,
        timeout_seconds=0.005,
    )
    generator = RagIntakeReportCardsGenerator(pipeline=pipeline, base_generator=_base_generator())

    outcome = await generator.generate(draft=_draft(), remaining_seconds=1.0)

    assert outcome.rag_evidence_available is False
    assert outcome.rag_partial is True
    assert outcome.cards is not None
    assert [card.product_name for card in outcome.cards.medications] == ["아세트아미노펜"]
    assert outcome.cards.lifestyle == []
    assert "통증을 완화합니다." in outcome.report_markdown
    assert "승인된 상호작용 확인" in outcome.report_markdown
    assert "두부" not in outcome.report_markdown
    assert all(status.status == "unverified" for status in outcome.cards.section_statuses)


@pytest.mark.asyncio
async def test_rag_queries_only_current_user_targets_and_never_adds_global_context() -> None:
    chunk = _chunk()
    pipeline, retriever = _pipeline(chunk=chunk, claim=_valid_claim())

    result = await pipeline.run(targets=_targets(include_medication=False))

    assert result.rag_evidence_available is True
    assert retriever.plans
    for plan in retriever.plans:
        assert plan.query_plan.entity_names == [TARGET_NAME]
        assert plan.patient_supplement_names == [TARGET_NAME]
        assert plan.patient_medication_names == []
        assert plan.include_patient_context is False
        assert "다른 사용자" not in plan.query_plan.original_query


@pytest.mark.asyncio
async def test_planner_runs_three_bounded_section_pipelines_concurrently() -> None:
    sections = [
        {
            "section_id": section_id,
            "target_ids": [TARGET_ID],
            "queries": [f"{TARGET_NAME} {section_id} {index}" for index in range(3)],
        }
        for section_id in ("food_drink", "lifestyle", "additional_precautions")
    ]
    retriever = _RecordingRetriever([], delay_seconds=0.01)
    pipeline, _ = _pipeline(
        chunk=_chunk(),
        claim=_valid_claim(),
        retriever=retriever,
        planner=lambda _input: {"sections": sections},
    )

    result = await pipeline.run(targets=_targets(include_medication=False))

    assert result.cards == []
    assert result.metrics["query_count"] == 9
    assert len(retriever.plans) == 9
    assert all(plan.limit == 6 and not plan.include_all_eligible for plan in retriever.plans)
    assert retriever.max_active >= 3


@pytest.mark.asyncio
async def test_each_section_receives_all_verified_retrieved_chunks() -> None:
    chunks = [
        _chunk(
            point_id=f"chunk-{index}",
            document_id=f"doc-{index // 3}",
            content=f"비타민 D 근거 문장 {index}입니다.",
            score=0.99 - index / 100,
        )
        for index in range(8)
    ]
    source_registry = {
        chunk.metadata.document_id: (chunk.metadata.source_id, chunk.metadata.provider) for chunk in chunks
    }
    retriever = _RecordingRetriever(chunks)
    trusted_inputs: list[dict[str, object]] = []
    planner = RunnableLambda(
        lambda _input: {
            "sections": [{"section_id": "lifestyle", "target_ids": [TARGET_ID], "queries": ["비타민 D 생활관리"]}]
        }
    )
    claim_writer = RunnableLambda(lambda value: trusted_inputs.append(value) or {"claims": []})
    verifier = RunnableLambda(lambda value: value["candidate_claims"])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version=DATASET_VERSION,
        planner=planner,
        claim_writer=claim_writer,
        verifier=verifier,
        source_registry=source_registry,
    )

    result = await pipeline.run(targets=_targets(include_medication=False))

    assert result.cards == []
    assert len(trusted_inputs) == 1
    trusted_chunks = trusted_inputs[0]["chunks"]
    assert isinstance(trusted_chunks, list)
    assert len(trusted_chunks) == 8
    assert len({chunk["chunk_id"] for chunk in trusted_chunks}) == 8
    documents = [chunk["source"] for chunk in trusted_chunks]
    assert max(documents.count(document) for document in set(documents)) == 3
