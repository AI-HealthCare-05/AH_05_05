import asyncio

import pytest

from ai_worker.reports.report_rag_pipeline import (
    ReportRagPipeline,
    ReportRagPlanner,
    ReportRagSectionPlan,
    ReportRagTarget,
    _ClaimsPayload,
    _json_data,
    load_report_rag_source_registry,
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


def _chunk(*, point_id: str, document_id: str, content: str, score: float = 0.9) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        chunk_id=(point_id * 64)[:64],
        point_id=point_id,
        content=content,
        embedding_text=content,
        token_count=3,
        similarity_score=score,
        search_mode=KnowledgeSearchMode.DENSE,
        metadata=KnowledgeChunkMetadata(
            source_id=f"source-{document_id}",
            document_id=document_id,
            title=f"{document_id} title",
            provider="Verified publisher",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version="knowledge-test-v1",
            source_url=f"https://example.test/{document_id}",
            evidence_level=KnowledgeEvidenceLevel.SYSTEMATIC_REVIEW,
            study_population=KnowledgeStudyPopulation.HUMAN,
            section_type=KnowledgeSectionType.CONCLUSION,
            content_kind=KnowledgeContentKind.TEXT,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="a" * 64,
        ),
    )


class _Retriever:
    def __init__(self, chunks: list[RetrievedKnowledgeChunk]) -> None:
        self.chunks = chunks
        self.plans = []

    async def search_with_diagnostics(self, *, execution_plan):
        self.plans.append(execution_plan)
        return type("Result", (), {"chunks": self.chunks})()


def test_multi_product_evidence_does_not_starve_lower_scoring_ingredients():
    chunks = [
        _chunk(point_id=str(i), document_id=f"doc-{i}", content="비타민 C 안내", score=0.95 - i * 0.01)
        for i in range(6)
    ]
    chunks.append(_chunk(point_id="acet", document_id="acet", content="아세트아미노펜 안내", score=0.7))
    pipeline = ReportRagPipeline(
        retriever=_Retriever([]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={c.metadata.document_id: (c.metadata.source_id, c.metadata.provider) for c in chunks},
    )
    selected = pipeline._filter_chunks(
        chunks,
        targets=[
            ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "비타민 C"),
            ReportRagTarget("medication:2", 2, "MEDICATION", "아세트아미노펜"),
        ],
    )
    assert any(c.point_id == "acet" for c in selected)
    assert len(selected) == len(chunks)


def test_claim_input_exposes_only_matching_planned_targets_without_extra_retrieval():
    pipeline = ReportRagPipeline(
        retriever=_Retriever([]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    targets = [
        ReportRagTarget("medication:1", 1, "MEDICATION", "가상약갑"),
        ReportRagTarget("medication:2", 2, "MEDICATION", "가상약을"),
        ReportRagTarget("supplement:1", 1, "SUPPLEMENT", "가상약갑"),
    ]
    plan = ReportRagPlanner().validate_or_fallback({}, targets=targets[:2])
    chunks = [
        _chunk(point_id="a", document_id="a", content="가상약갑 주의사항"),
        _chunk(point_id="b", document_id="b", content="가상약을 주의사항"),
        _chunk(point_id="c", document_id="c", content="연결 없는 자료"),
    ]
    payload = pipeline._claims_input(plan, chunks, targets, [])
    assert [chunk["matched_target_ids"] for chunk in payload["chunks"]] == [["medication:1"], ["medication:2"], []]
    assert payload["chunks"][0]["source_section"] == KnowledgeSectionType.CONCLUSION.value
    assert [chunk["content"] for chunk in payload["chunks"]] == [chunk.content for chunk in chunks]
    assert pipeline._retriever.plans == []


def test_report_planner_falls_back_when_more_than_three_queries_are_proposed():
    targets = [ReportRagTarget("medication:1", 1, "MEDICATION", "등록약")]
    queries = [f"등록약 주의사항 {index}" for index in range(8)]
    sections = ReportRagPlanner().validate_or_fallback(
        {"sections": [{"section_id": "additional_precautions", "target_ids": ["medication:1"], "queries": queries}]},
        targets=targets,
    )
    assert len(sections) == 3
    assert all(len(section.queries) <= 3 for section in sections)


@pytest.mark.asyncio
async def test_report_uses_bounded_queries_and_six_result_retrieval():
    queries = [f"등록약 주의사항 {index}" for index in range(8)]
    retriever = _Retriever([])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "additional_precautions", "target_ids": ["medication:1"], "queries": queries}]
        },
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    result = await pipeline.run(targets=[ReportRagTarget("medication:1", 1, "MEDICATION", "등록약")])
    assert result.metrics["query_count"] == 3
    assert all(plan.limit == 6 and not plan.include_all_eligible for plan in retriever.plans)


def test_report_registry_includes_approved_demo_sources_but_not_disabled_sources():
    registry = load_report_rag_source_registry()
    assert registry["kpicia_drug_encyclopedia-33898a903b6cbca7"] == ("kpicia_drug_encyclopedia", "약학정보원")
    assert not any(source == "unknown_supplement_interaction_monograph" for source, _ in registry.values())


@pytest.mark.parametrize(
    "title,drug_names,expected",
    [
        ("아세트아미노펜(acetaminophen)", ["아세트아미노펜", "acetaminophen", "아세트아미노펜(acetaminophen)"], 1),
        ("탁센 아세트아미노펜", ["아세트아미노펜", "탁센"], 0),
        ("아세트아미노펜(acetaminophen)", ["아세트아미노펜", "탁센"], 0),
    ],
)
def test_legacy_demo_encyclopedia_matches_exact_ingredient_title(title, drug_names, expected):
    chunk = _chunk(point_id="a", document_id="legacy", content="아세트아미노펜 중복 복용에 주의하세요.")
    chunk = chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "title": title,
                    "drug_names": drug_names,
                    "ingredient_names": [],
                    "access_scope": KnowledgeAccessScope.DEMO_RESTRICTED,
                    "study_population": KnowledgeStudyPopulation.UNKNOWN,
                    "document_type": KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
                }
            )
        }
    )
    pipeline = ReportRagPipeline(
        retriever=_Retriever([]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={"legacy": ("source-legacy", "Verified publisher")},
    )
    target = ReportRagTarget(
        "medication:1", 1, "MEDICATION", "아세트아미노펜정500mg", ("아세트아미노펜", "탁센"), ingredient_only=True
    )
    assert len(pipeline._filter_chunks([chunk], targets=[target])) == expected
    animal = chunk.model_copy(
        update={"metadata": chunk.metadata.model_copy(update={"study_population": KnowledgeStudyPopulation.ANIMAL})}
    )
    assert pipeline._filter_chunks([animal], targets=[target]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "product_label,dose_text,brand_tag,expected",
    [
        (False, "", False, 1),
        (True, "", False, 0),
        (False, "1회 2정을 복용하세요.", False, 0),
        (False, "하루 2번 복용하세요.", False, 0),
        (False, "매일 두 번 복용하세요.", False, 0),
        (False, "매 네 시간 복용하세요.", False, 0),
        (False, "하루 한 알씩 복용하세요.", False, 0),
        (False, "매일 두 차례 복용하세요.", False, 0),
        (False, "", True, 0),
    ],
)
async def test_unresolved_product_uses_only_ingredient_common_guidance(product_label, dose_text, brand_tag, expected):
    quote = "아세트아미노펜은 " + (dose_text or "음주 시 주의하세요.")
    chunk = _chunk(point_id="a", document_id="ingredient", content=quote)
    chunk = chunk.model_copy(
        update={
            "metadata": chunk.metadata.model_copy(
                update={
                    "ingredient_names": ["아세트아미노펜"],
                    "drug_names": ["탁센"] if brand_tag else [],
                    "document_type": KnowledgeDocumentType.REGULATORY_DRUG_LABEL
                    if product_label
                    else KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
                }
            )
        }
    )
    retriever = _Retriever([chunk])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [
                {"section_id": "lifestyle", "target_ids": ["medication:1"], "queries": ["아세트아미노펜 주의사항"]}
            ]
        },
        claim_writer=lambda _: {
            "claims": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["medication:1"],
                    "title": "성분 주의",
                    "summary": quote,
                    "action": quote,
                    "grounded": True,
                    "evidence": [{"chunk_id": "a", "exact_quote": quote}],
                }
            ]
        },
        verifier=lambda value: value["candidate_claims"],
        source_registry={"ingredient": ("source-ingredient", "Verified publisher")},
    )
    result = await pipeline.run(
        targets=[
            ReportRagTarget(
                "medication:1", 1, "MEDICATION", "아세트아미노펜정500mg", ("아세트아미노펜",), ingredient_only=True
            )
        ]
    )
    assert len(result.cards) == expected
    assert all("아세트아미노펜정500mg" not in plan.query_plan.entity_names for plan in retriever.plans)
    assert all(
        entity.entity_type.value == "INGREDIENT_NAME" for plan in retriever.plans for entity in plan.query_plan.entities
    )
    if not expected:
        assert result.sources == []
    if expected:
        assert "성분 공통 안내" in result.cards[0].summary
        assert "정확한 제품" in result.cards[0].summary
        assert result.sources[0].quote == quote


@pytest.mark.asyncio
async def test_pipeline_uses_safe_fallback_plan_and_emits_only_exact_quote_claims() -> None:
    retriever = _Retriever(
        [
            _chunk(
                point_id="a",
                document_id="doc-a",
                content="비타민 D는 식사와 함께 복용할 수 있습니다.",
            ),
            _chunk(
                point_id="b",
                document_id="doc-b",
                content="비타민 D의 복용량 변경은 의료진과 상의해야 합니다.",
            ),
        ]
    )
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {"unexpected": "untrusted shape"},
        claim_writer=lambda _: {
            "claims": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["supplement:7"],
                    "title": "식사와 함께 확인",
                    "summary": "비타민 D는 식사와 함께 복용할 수 있습니다.",
                    "action": "등록한 복용 방법과 함께 확인하세요.",
                    "evidence": [{"chunk_id": "a", "exact_quote": "비타민 D는 식사와 함께 복용할 수 있습니다."}],
                    "grounded": True,
                },
                {
                    "section_id": "lifestyle",
                    "target_ids": ["supplement:7"],
                    "title": "제외되어야 함",
                    "summary": "매일 5000IU로 늘리세요.",
                    "action": "용량을 변경하세요.",
                    "evidence": [
                        {"chunk_id": "b", "exact_quote": "비타민 D의 복용량 변경은 의료진과 상의해야 합니다."}
                    ],
                    "grounded": True,
                },
            ]
        },
        verifier=lambda value: value["candidate_claims"],
        source_registry={
            "doc-a": ("source-doc-a", "Verified publisher"),
            "doc-b": ("source-doc-b", "Verified publisher"),
        },
    )

    result = await pipeline.run(
        targets=[ReportRagTarget(id="supplement:7", item_id=7, item_type="SUPPLEMENT", name="비타민 D")]
    )

    assert len(result.cards) == 1
    assert result.cards[0].id == "rag:lifestyle:supplement:7:1"
    assert result.cards[0].source_ids == ["rag:source-doc-a:a:34dccc6a"]
    assert result.sources[0].chunk_id == "a"
    assert result.sources[0].quote == "비타민 D는 식사와 함께 복용할 수 있습니다."
    assert result.rag_evidence_available is True
    assert result.section_statuses[1].status == "verified"
    assert retriever.plans[0].query_plan.entity_names == ["비타민 D"]


def test_planner_replaces_unknown_targets_and_overlong_queries_with_server_plan() -> None:
    planner = ReportRagPlanner()
    targets = [ReportRagTarget(id="medication:1", item_id=1, item_type="MEDICATION", name="약 A")]

    plan = planner.validate_or_fallback(
        {"sections": [{"section_id": "food_drink", "target_ids": ["unknown"], "queries": ["a", "b", "c", "d"]}]},
        targets=targets,
    )

    assert plan == [
        ReportRagSectionPlan(
            section_id="food_drink", target_ids=("medication:1",), queries=("약 A 음식·음료 주의사항",)
        ),
        ReportRagSectionPlan(section_id="lifestyle", target_ids=("medication:1",), queries=("약 A 생활관리 참고사항",)),
        ReportRagSectionPlan(
            section_id="additional_precautions", target_ids=("medication:1",), queries=("약 A 주의사항",)
        ),
    ]


def test_nested_structured_claims_are_sent_as_json_not_pydantic_repr() -> None:
    payload = _ClaimsPayload.model_validate(
        {
            "claims": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["supplement:7"],
                    "title": "제목",
                    "summary": "요약",
                    "action": "확인",
                    "evidence": [{"chunk_id": "chunk", "exact_quote": "원문"}],
                    "grounded": False,
                }
            ]
        }
    )

    serialized = _json_data({"candidate_claims": payload})

    assert '"candidate_claims":{"claims":[' in serialized
    assert "claims=[" not in serialized


def test_planner_restores_omitted_targets_and_searches_their_known_aliases() -> None:
    targets = [
        ReportRagTarget("medication:1", 1, "MEDICATION", "제품 A", ("성분 A",)),
        ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "제품 B", ("비타민 C",)),
    ]
    plan = ReportRagPlanner().validate_or_fallback(
        {"sections": [{"section_id": "lifestyle", "target_ids": ["medication:1"], "queries": ["제품 A 보관"]}]},
        targets=targets,
    )
    assert plan[0].target_ids == ("medication:1", "supplement:2")
    assert any("비타민 C" in query for query in plan[0].queries)
    assert any("제품 A" in query for query in plan[0].queries)
    assert len(plan[0].queries) <= 3


def test_fallback_keeps_every_registered_target_in_three_queries() -> None:
    targets = [ReportRagTarget(f"medication:{i}", i, "MEDICATION", f"제품{i}") for i in range(14)]
    plan = ReportRagPlanner.fallback(targets=targets)
    assert len(plan) == 3
    for section in plan:
        assert len(section.queries) == 3
        assert all(any(target.name in query for query in section.queries) for target in targets)
        assert all(sum(target.name + " " in query for target in targets) <= 5 for query in section.queries)


def test_planner_does_not_count_ids_as_searched_when_queries_omit_the_product() -> None:
    targets = [
        ReportRagTarget("medication:1", 1, "MEDICATION", "제품 A"),
        ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "제품 B", ("비타민 C",)),
    ]
    plan = ReportRagPlanner().validate_or_fallback(
        {
            "sections": [
                {"section_id": "lifestyle", "target_ids": [target.id for target in targets], "queries": ["제품 A 보관"]}
            ]
        },
        targets=targets,
    )
    assert any("비타민 C" in query for query in plan[0].queries)


def test_medication_ingredient_alias_is_searched_as_ingredient_not_product() -> None:
    from ai_worker.schemas.medication_search import MedicationQueryEntityType

    pipeline = ReportRagPipeline(
        retriever=_Retriever([]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    plan = pipeline._execution_plan(
        query="성분 A 주의", targets=[ReportRagTarget("medication:1", 1, "MEDICATION", "제품 A", ("성분 A",))]
    )
    assert plan.query_plan.entities[0].entity_type == MedicationQueryEntityType.PRODUCT_NAME
    assert plan.query_plan.entities[1].entity_type == MedicationQueryEntityType.INGREDIENT_NAME


@pytest.mark.asyncio
async def test_retrieval_failure_is_not_hidden_by_planner_target_omission() -> None:
    class FailingRetriever:
        async def search_with_diagnostics(self, *, execution_plan):
            raise RuntimeError("unavailable")

    pipeline = ReportRagPipeline(
        retriever=FailingRetriever(),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "lifestyle", "target_ids": ["medication:1"], "queries": ["제품 A"]}]
        },
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    result = await pipeline.run(
        targets=[
            ReportRagTarget("medication:1", 1, "MEDICATION", "제품 A"),
            ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "제품 B"),
        ]
    )
    assert result.section_statuses[1].reason == "자료 검색 실패"
    assert not result.cards


@pytest.mark.asyncio
async def test_grouped_queries_do_not_append_the_whole_stack_to_each_embedding() -> None:
    retriever = _Retriever([])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    await pipeline.run(
        targets=[
            ReportRagTarget("medication:1", 1, "MEDICATION", "등록약 A"),
            ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "등록제품 B", ("비타민 C",)),
        ]
    )
    assert len(retriever.plans) == 7  # six grouped queries plus one cached ingredient rescue
    assert all(len(plan.patient_medication_names + plan.patient_supplement_names) == 1 for plan in retriever.plans)


@pytest.mark.asyncio
async def test_compound_product_recovers_ingredient_evidence_without_diluted_query() -> None:
    quote = "비타민 C는 신장질환이 있는 경우 전문가와 상담할 것"
    chunk = _chunk(point_id="c", document_id="doc-c", content=quote)

    class FocusedRetriever(_Retriever):
        async def search_with_diagnostics(self, *, execution_plan):
            self.plans.append(execution_plan)
            # Reproduces the real retriever: a many-product embedding has no
            # eligible results; a focused known-ingredient query finds evidence.
            found = execution_plan.query_plan.entity_names == ["비타민 C"]
            return type("Result", (), {"chunks": [chunk] if found else []})()

    retriever = FocusedRetriever([])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda value: {
            "claims": [
                {
                    "section_id": "additional_precautions",
                    "target_ids": ["supplement:2"],
                    "title": "신장질환이 있는 경우 확인",
                    "summary": quote,
                    "action": quote,
                    "evidence": [{"chunk_id": "c", "exact_quote": quote}],
                    "grounded": True,
                }
            ]
        }
        if value["plan"][0]["section_id"] == "additional_precautions"
        else {"claims": []},
        verifier=lambda value: value["candidate_claims"],
        source_registry={"doc-c": ("source-doc-c", "Verified publisher")},
    )
    result = await pipeline.run(
        targets=[
            ReportRagTarget("medication:1", 1, "MEDICATION", "등록약 A"),
            ReportRagTarget("supplement:2", 2, "SUPPLEMENT", "복합제품 B", ("나트륨", "비타민 C", "비타민 D")),
        ]
    )
    assert len(result.cards) == 1
    assert result.cards[0].related_item_ids == [2]
    assert result.sources[0].quote == quote
    assert sum(plan.query_plan.entity_names == ["비타민 C"] for plan in retriever.plans) == 1
    assert result.metrics["focused_query_count"] == 3


@pytest.mark.asyncio
async def test_focused_rescue_caps_aliases_at_twenty_four_and_preserves_entity_kind() -> None:
    class ConcurrentRetriever(_Retriever):
        active = 0
        peak = 0

        async def search_with_diagnostics(self, *, execution_plan):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0)
                return await super().search_with_diagnostics(execution_plan=execution_plan)
            finally:
                self.active -= 1

    retriever = ConcurrentRetriever([])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    result = await pipeline.run(
        targets=[
            ReportRagTarget(
                "medication:1", 1, "MEDICATION", "약 A", ("공통 성분", *[f"약 성분 {i}" for i in range(30)])
            ),
            ReportRagTarget(
                "supplement:2", 2, "SUPPLEMENT", "제품 B", ("공통 성분", *[f"영양 성분 {i}" for i in range(30)])
            ),
        ]
    )
    focused = [plan for plan in retriever.plans if len(plan.query_plan.entity_names) == 1]
    assert result.metrics["focused_query_count"] == len(focused) == 24
    assert result.metrics["query_count"] == len(retriever.plans) == 30
    assert retriever.peak <= 3
    shared = [plan for plan in focused if plan.query_plan.entity_names == ["공통 성분"]]
    assert len(shared) == 2
    assert {plan.query_plan.entities[0].kind.value for plan in shared} == {"DRUG", "SUPPLEMENT"}
    assert all(plan.query_plan.entities[0].entity_type.value == "INGREDIENT_NAME" for plan in focused)


@pytest.mark.asyncio
async def test_focused_query_budget_is_shared_across_sections_with_different_missing_targets():
    retriever = _Retriever([])
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {},
        claim_writer=lambda _: {},
        verifier=lambda _: {},
        source_registry={},
    )
    cache = {}
    semaphore = asyncio.Semaphore(3)
    for index in range(3):
        await pipeline._retrieve_focused_aliases(
            [
                ReportRagTarget(
                    f"medication:{index}",
                    index,
                    "MEDICATION",
                    f"제품 {index}",
                    tuple(f"성분 {index}-{i}" for i in range(12)),
                )
            ],
            cache,
            semaphore,
        )
    assert len(retriever.plans) == 24


def test_reverification_keeps_unchanged_claim_when_it_omits_a_bad_neighbor() -> None:
    first = {
        "claims": [
            {
                "section_id": "lifestyle",
                "target_ids": ["supplement:7"],
                "title": "유지",
                "summary": "요약",
                "action": "확인",
                "evidence": [{"chunk_id": "chunk-a", "exact_quote": "원문 A"}],
                "grounded": True,
            },
            {
                "section_id": "lifestyle",
                "target_ids": ["supplement:8"],
                "title": "제외",
                "summary": "부정확한 요약",
                "action": "확인",
                "evidence": [{"chunk_id": "chunk-b", "exact_quote": "원문 B"}],
                "grounded": True,
            },
        ]
    }

    retained = ReportRagPipeline._retain_unchanged_reverified_claims(first, {"claims": [first["claims"][0]]})

    assert [claim.title for claim in retained.claims] == ["유지"]


@pytest.mark.asyncio
async def test_pipeline_rejects_claim_when_every_target_is_not_bound_to_a_quoted_chunk() -> None:
    retriever = _Retriever(
        [_chunk(point_id="c", document_id="doc-c", content="비타민 D는 식사와 함께 복용할 수 있습니다.")]
    )
    pipeline = ReportRagPipeline(
        retriever=retriever,
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [
                {"section_id": "lifestyle", "target_ids": ["supplement:7", "supplement:8"], "queries": ["test"]}
            ]
        },
        claim_writer=lambda _: {
            "claims": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["supplement:7", "supplement:8"],
                    "title": "함께 확인",
                    "summary": "비타민 D는 식사와 함께 복용할 수 있습니다.",
                    "action": "등록한 방법을 확인하세요.",
                    "evidence": [{"chunk_id": "c", "exact_quote": "비타민 D는 식사와 함께 복용할 수 있습니다."}],
                    "grounded": True,
                }
            ]
        },
        verifier=lambda value: value["candidate_claims"],
        source_registry={"doc-c": ("source-doc-c", "Verified publisher")},
    )

    result = await pipeline.run(
        targets=[
            ReportRagTarget(id="supplement:7", item_id=7, item_type="SUPPLEMENT", name="비타민 D"),
            ReportRagTarget(id="supplement:8", item_id=8, item_type="SUPPLEMENT", name="오메가3"),
        ]
    )

    assert result.cards == []
    assert result.section_statuses[1].status == "unverified"


@pytest.mark.asyncio
async def test_pipeline_rejects_changed_korean_quantity_unit_even_when_the_number_matches() -> None:
    quote = "비타민 D는 2주 간격으로 확인합니다."
    pipeline = ReportRagPipeline(
        retriever=_Retriever([_chunk(point_id="d", document_id="doc-d", content=quote)]),
        dataset_version="knowledge-test-v1",
        planner=lambda _: {
            "sections": [{"section_id": "lifestyle", "target_ids": ["supplement:7"], "queries": ["test"]}]
        },
        claim_writer=lambda _: {
            "claims": [
                {
                    "section_id": "lifestyle",
                    "target_ids": ["supplement:7"],
                    "title": "간격",
                    "summary": "비타민 D는 2개월 간격으로 확인합니다.",
                    "action": "제품 안내를 확인하세요.",
                    "evidence": [{"chunk_id": "d", "exact_quote": quote}],
                    "grounded": True,
                }
            ]
        },
        verifier=lambda value: value["candidate_claims"],
        source_registry={"doc-d": ("source-doc-d", "Verified publisher")},
    )

    result = await pipeline.run(
        targets=[ReportRagTarget(id="supplement:7", item_id=7, item_type="SUPPLEMENT", name="비타민 D")]
    )

    assert result.cards == []
