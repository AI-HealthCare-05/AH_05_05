import asyncio

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
