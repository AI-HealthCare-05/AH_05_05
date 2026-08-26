from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
    RetrievedKnowledgeChunk,
)


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def embed_query(self, query: str) -> list[float]:
        self.queries.append(query)
        return [0.1, 0.2, 0.3]


class FakeKnowledgeStore:
    def __init__(self, responses: list[list[RetrievedKnowledgeChunk]]) -> None:
        self.responses = list(responses)
        self.queries = []

    async def search(self, *, query_vector, search_query):
        self.queries.append(search_query)
        return self.responses.pop(0)


def build_chunk(
    score: float = 0.8,
    *,
    chunk_id: str = "a" * 64,
    ingredient_names: list[str] | None = None,
    section_type: KnowledgeSectionType = KnowledgeSectionType.CAUTION,
    content: str | None = None,
    title: str = "건강기능식품 기능성 안내",
    document_type: KnowledgeDocumentType = (KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE),
    document_id: str = "supplement-guide",
) -> RetrievedKnowledgeChunk:
    return RetrievedKnowledgeChunk(
        point_id="point-1",
        chunk_id=chunk_id,
        content=content or "비타민 D 섭취 시 개인 상태와 다른 복용 제품을 확인합니다.",
        embedding_text="비타민 D 섭취 주의",
        token_count=20,
        similarity_score=score,
        metadata=KnowledgeChunkMetadata(
            source_id="MFDS",
            document_id=document_id,
            title=title,
            provider="식품의약품안전처",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=document_type,
            dataset_version="knowledge-baseline-v1",
            ingredient_names=ingredient_names or [],
            section_type=section_type,
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=chunk_id,
        ),
    )


async def test_search_retries_without_entity_filters_when_filtered_search_is_empty() -> None:
    store = FakeKnowledgeStore(responses=[[], [build_chunk()]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="비타민 D 주의사항을 알려줘",
        medication_names=[],
        supplement_names=["비타민 D"],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [build_chunk()]
    assert store.queries[0].ingredient_names == ["비타민 D"]
    assert store.queries[1].ingredient_names == []


async def test_search_excludes_results_below_minimum_score() -> None:
    store = FakeKnowledgeStore(
        responses=[[build_chunk(0.64), build_chunk(0.8)]],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="비타민 D",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert [result.similarity_score for result in results] == [0.8]


async def test_search_requests_twenty_candidates_for_final_five() -> None:
    store = FakeKnowledgeStore(responses=[[build_chunk()]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    await retriever.search(
        question="마그네슘의 효능",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert store.queries[0].limit == 20


async def test_search_reranks_exact_ingredient_and_section_match() -> None:
    generic = build_chunk(
        0.8,
        chunk_id="a" * 64,
        section_type=KnowledgeSectionType.OVERVIEW,
    )
    exact = build_chunk(
        0.76,
        chunk_id="c" * 64,
        ingredient_names=["마그네슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    store = FakeKnowledgeStore(responses=[[generic, exact]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="마그네슘의 효능",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [exact, generic]


async def test_search_accepts_strong_entity_and_section_match_after_boost() -> None:
    exact_match = build_chunk(
        0.59,
        ingredient_names=["마그네슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    store = FakeKnowledgeStore(responses=[[exact_match]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="마그네슘의 효능",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [exact_match]


async def test_search_does_not_rescue_weak_exact_match() -> None:
    weak_match = build_chunk(
        0.54,
        ingredient_names=["마그네슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    store = FakeKnowledgeStore(responses=[[weak_match]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="마그네슘의 효능",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == []


async def test_search_accepts_population_name_contained_in_metadata_entity() -> None:
    population_caution = build_chunk(
        0.575,
        chunk_id="d" * 64,
        section_type=KnowledgeSectionType.CAUTION,
    )
    population_caution.metadata.drug_names = ["임산부 비염약"]
    store = FakeKnowledgeStore(responses=[[population_caution]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-baseline-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="임산부는 무슨 약을 조심해야 해?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [population_caution]


async def test_search_merges_separate_english_pair_query_results() -> None:
    target = build_chunk(
        0.69,
        chunk_id="e" * 64,
        title="Calcium and Iron Absorption",
        content=(
            "Studies in humans report that calcium can inhibit iron absorption, while long-term iron status may adapt."
        ),
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        section_type=KnowledgeSectionType.SUMMARY,
    )
    embedding_provider = FakeEmbeddingProvider()
    store = FakeKnowledgeStore(responses=[[], [target]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=embedding_provider,
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="칼슘과 철분을 같이 먹으면 철분 흡수가 떨어지나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [target]
    assert embedding_provider.queries == [
        "칼슘과 철분을 같이 먹으면 철분 흡수가 떨어지나요? 칼슘 철분 상호작용 병용 주의",
        "calcium iron absorption interaction",
    ]


async def test_search_rejects_single_ingredient_chunk_for_pair_question() -> None:
    generic_zinc = build_chunk(
        0.82,
        chunk_id="f" * 64,
        ingredient_names=["아연"],
        title="아연",
        content="아연은 정상적인 면역기능에 필요합니다.",
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    store = FakeKnowledgeStore(responses=[[generic_zinc], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="아연을 복용하면 철분 수치가 낮아질 수 있나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == []


async def test_search_limits_results_from_one_document_to_two_chunks() -> None:
    results_from_one_paper = [
        build_chunk(
            0.80 - index * 0.01,
            chunk_id=marker * 64,
            document_id="paper-a",
        )
        for index, marker in enumerate(("a", "b", "c"))
    ]
    other_paper = build_chunk(
        0.75,
        chunk_id="d" * 64,
        document_id="paper-b",
    )
    store = FakeKnowledgeStore(
        responses=[[*results_from_one_paper, other_paper]],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="비타민 D 주의사항",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert [result.metadata.document_id for result in results] == [
        "paper-a",
        "paper-a",
        "paper-b",
    ]
