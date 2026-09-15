import asyncio
from types import SimpleNamespace

import pytest

from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.rag.retrievers import candidate_retrieval
from ai_worker.rag.retrievers.candidate_retrieval import (
    MedicationKnowledgeCandidateRetriever,
)
from ai_worker.schemas.medication_search import MedicationSearchExecutionPlan


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.6, 0.8]


class FakeKnowledgeStore:
    def __init__(self) -> None:
        self.queries = []

    async def search(self, *, query_vector, search_query):
        self.queries.append(search_query)
        return []


class PairCoverageKnowledgeStore(FakeKnowledgeStore):
    def __init__(self, pair_keys: list[str]) -> None:
        super().__init__()
        self.pair_keys = pair_keys

    async def search(self, *, query_vector, search_query):
        self.queries.append(search_query)
        return [SimpleNamespace(metadata=SimpleNamespace(interaction_pair_keys=self.pair_keys))]


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


def test_overview_does_not_stop_at_previously_known_drug_pairs() -> None:
    plan = build_execution_plan().model_copy(
        update={
            "query_plan": build_execution_plan().query_plan.model_copy(update={"interaction_overview": True}),
            "approved_rule_pair_keys": ["a" * 64],
        }
    )
    tiers = MedicationKnowledgeCandidateRetriever.search_tiers(plan)
    assert [tier.name.value for tier in tiers] == ["ENTITY", "SEMANTIC"]


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


@pytest.mark.asyncio
async def test_complete_exact_pair_evidence_skips_entity_and_semantic_search_tiers() -> None:
    query_plan = MedicationKnowledgeQueryBuilder().build("마그네슘, 아연, 칼슘 같이 먹어도 돼?")
    store = PairCoverageKnowledgeStore(query_plan.interaction_pair_keys)
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v16",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )
    execution_plan = build_execution_plan().model_copy(update={"query_plan": query_plan})

    result = await retriever.retrieve(execution_plan=execution_plan)

    assert result.attempted_search_tiers == [candidate_retrieval.KnowledgeSearchTier.EXACT_PAIR]
    assert len(store.queries) == len({query_plan.expanded_query, *query_plan.alternate_queries})


@pytest.mark.asyncio
async def test_incomplete_exact_pair_evidence_continues_to_entity_and_semantic_tiers() -> None:
    query_plan = MedicationKnowledgeQueryBuilder().build("마그네슘, 아연, 칼슘 같이 먹어도 돼?")
    store = PairCoverageKnowledgeStore(query_plan.interaction_pair_keys[:1])
    retriever = MedicationKnowledgeCandidateRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v16",
        eligibility_evaluator=lambda _result, _plan: "ELIGIBLE",
        section_coverage_evaluator=lambda _results, _plan: True,
    )
    execution_plan = build_execution_plan().model_copy(update={"query_plan": query_plan})

    result = await retriever.retrieve(execution_plan=execution_plan)

    assert result.attempted_search_tiers == [
        candidate_retrieval.KnowledgeSearchTier.EXACT_PAIR,
        candidate_retrieval.KnowledgeSearchTier.ENTITY,
    ]
