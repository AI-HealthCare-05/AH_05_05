import asyncio

import pytest

from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.rag.retrievers import candidate_retrieval
from ai_worker.rag.retrievers.candidate_retrieval import (
    MedicationKnowledgeCandidateRetriever,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_search import MedicationSearchExecutionPlan


def test_overview_does_not_limit_search_to_existing_drug_rule_pairs() -> None:
    plan = build_execution_plan()
    query = plan.query_plan.model_copy(
        update={"entity_names": ["와파린"], "section_types": [KnowledgeSectionType.INTERACTION]}
    )
    plan = plan.model_copy(update={"query_plan": query, "approved_rule_pair_keys": ["c" * 64]})
    assert all(tier.name.value != "EXACT_PAIR" for tier in MedicationKnowledgeCandidateRetriever.search_tiers(plan))


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.6, 0.8]


@pytest.mark.asyncio
async def test_overview_continues_semantic_search_after_entity_coverage() -> None:
    class PopulatedStore(FakeKnowledgeStore):
        async def search(self, *, query_vector, search_query):
            self.queries.append(search_query)
            return [object()]

    plan = build_execution_plan()
    query = plan.query_plan.model_copy(
        update={"entity_names": ["와파린"], "section_types": [KnowledgeSectionType.INTERACTION]}
    )
    store = PopulatedStore()
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v17",
        eligibility_evaluator=lambda *_: "ELIGIBLE",
        section_coverage_evaluator=lambda *_: True,
    )
    result = await retriever.retrieve(execution_plan=plan.model_copy(update={"query_plan": query}))
    assert [tier.value for tier in result.attempted_search_tiers] == ["ENTITY", "SEMANTIC"]


class FakeKnowledgeStore:
    def __init__(self) -> None:
        self.queries = []

    async def search(self, *, query_vector, search_query):
        self.queries.append(search_query)
        return []


def build_execution_plan() -> MedicationSearchExecutionPlan:
    query_plan = (
        MedicationKnowledgeQueryBuilder()
        .build(
            "마그네슘은 왜 먹나요?",
        )
        .model_copy(
            update={
                "alternate_queries": ["마그네슘 기능성"],
            },
        )
    )
    return MedicationSearchExecutionPlan(
        query_plan=query_plan,
        patient_medication_names=[],
        patient_supplement_names=[],
        approved_rule_pair_keys=[],
        context_hash="a" * 64,
        approved_rules_hash="b" * 64,
        limit=5,
    )


@pytest.mark.asyncio
async def test_retrieve_uses_runnable_parallel_for_each_candidate_search_fan_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parallel_calls: list[tuple[str, ...]] = []

    class TrackingRunnableParallel:
        def __init__(self, **steps) -> None:
            self._steps = steps

        async def ainvoke(self, input_value):
            parallel_calls.append(tuple(self._steps))
            values = await asyncio.gather(
                *(step.ainvoke(input_value) for step in self._steps.values()),
            )
            return dict(zip(self._steps, values, strict=True))

    monkeypatch.setattr(
        candidate_retrieval,
        "RunnableParallel",
        TrackingRunnableParallel,
        raising=False,
    )
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=FakeKnowledgeStore(),
        dataset_version="knowledge-full-v14",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )

    result = await retriever.retrieve(execution_plan=build_execution_plan())

    assert parallel_calls == [
        ("query_0", "query_1"),
    ] * (1 + len(result.attempted_search_tiers))


@pytest.mark.asyncio
async def test_retrieve_embeds_query_with_resolved_entities_and_requested_sections() -> None:
    embedding_provider = FakeEmbeddingProvider()
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=embedding_provider,
        vector_store=FakeKnowledgeStore(),
        dataset_version="knowledge-full-v16",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )

    await retriever.retrieve(execution_plan=build_execution_plan())

    assert embedding_provider.queries[0].startswith("[질문] 마그네슘은 왜 먹나요?")
    assert "[대상] 마그네슘" in embedding_provider.queries[0]
    assert "[요청 섹션] FUNCTION" in embedding_provider.queries[0]


@pytest.mark.asyncio
async def test_interaction_overview_embeds_query_for_approved_therapeutic_class() -> None:
    embedding_provider = FakeEmbeddingProvider()
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=embedding_provider,
        vector_store=FakeKnowledgeStore(),
        dataset_version="knowledge-full-v17",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )
    plan = build_execution_plan()
    query_plan = plan.query_plan.model_copy(
        update={"entity_names": ["와파린"], "section_types": [KnowledgeSectionType.INTERACTION]}
    )
    plan = plan.model_copy(update={"query_plan": query_plan, "approved_therapeutic_class_names": ["항응고제"]})

    await retriever.retrieve(execution_plan=plan)

    assert any("항응고제" in query and "상호작용" in query for query in embedding_provider.queries)


@pytest.mark.asyncio
async def test_retrieve_keeps_functional_goal_expansion_in_embedding_query() -> None:
    embedding_provider = FakeEmbeddingProvider()
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=embedding_provider,
        vector_store=FakeKnowledgeStore(),
        dataset_version="knowledge-full-v16",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )
    execution_plan = MedicationSearchExecutionPlan(
        query_plan=MedicationKnowledgeQueryBuilder().build(
            "잠 잘자기 위해 어떤걸 먹으면 좋아?",
        ),
        patient_medication_names=[],
        patient_supplement_names=[],
        approved_rule_pair_keys=[],
        context_hash="a" * 64,
        approved_rules_hash="b" * 64,
        limit=5,
    )

    await retriever.retrieve(execution_plan=execution_plan)

    assert "건강기능식품" in embedding_provider.queries[0]
    assert "기능성" in embedding_provider.queries[0]
