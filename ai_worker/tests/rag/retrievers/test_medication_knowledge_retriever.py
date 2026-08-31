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


async def test_search_with_diagnostics_counts_fallback_and_rejection_reasons() -> None:
    accepted = build_chunk(
        0.8,
        chunk_id="a" * 64,
        ingredient_names=["마그네슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    below_score = build_chunk(
        0.54,
        chunk_id="b" * 64,
        ingredient_names=["마그네슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    entity_mismatch = build_chunk(
        0.59,
        chunk_id="c" * 64,
        ingredient_names=["칼슘"],
        section_type=KnowledgeSectionType.FUNCTION,
    )
    store = FakeKnowledgeStore(
        responses=[[], [accepted, below_score, entity_mismatch]],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search_with_diagnostics(
        question="마그네슘은 왜 먹나요?",
        medication_names=[],
        supplement_names=["마그네슘"],
        interaction_pair_keys=[],
        limit=5,
    )

    assert result.chunks == [accepted]
    assert result.diagnostics.model_dump() == {
        "raw_candidate_count": 3,
        "entity_filtered_count": 0,
        "broad_candidate_count": 3,
        "fallback_used": True,
        "eligible_candidate_count": 1,
        "rejected_below_score_count": 1,
        "rejected_entity_mismatch_count": 1,
        "rejected_pair_mismatch_count": 0,
        "accepted_count": 1,
        "max_raw_score": 0.8,
        "max_score": 0.8,
    }


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


async def test_search_reranks_verified_bilingual_drug_alias_above_substring_match() -> None:
    exact_family = build_chunk(
        0.70,
        chunk_id="a" * 64,
        title="로사르탄(losartan)",
        content="로사르탄 단일제의 주의사항입니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.CAUTION,
    )
    exact_family.metadata.drug_names = ["로사르탄(losartan)"]
    substring_only = build_chunk(
        0.70,
        chunk_id="z" * 64,
        title="로사르탄 복합제(losartan combination)",
        content="로사르탄 복합제의 주의사항입니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.CAUTION,
    )
    substring_only.metadata.drug_names = [
        "로사르탄 복합제(losartan combination)",
    ]
    store = FakeKnowledgeStore(
        responses=[[substring_only, exact_family], []],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="losartan 주의사항",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [exact_family, substring_only]


async def test_search_does_not_rescue_low_score_alias_from_wrong_section() -> None:
    wrong_section = build_chunk(
        0.55,
        title="로사르탄(losartan)",
        content="로사르탄의 효능을 설명합니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    wrong_section.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[wrong_section], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="losartan 주의사항",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == []


async def test_search_rescues_legacy_encyclopedia_chunk_from_attached_heading() -> None:
    legacy_caution = build_chunk(
        0.5668,
        title="로사르탄(losartan)",
        content=(
            "제품별 허가정보에서 확인할 수 있습니다.\n\n주의사항로사르탄 단일제에 대한 주의사항은 다음과 같습니다."
        ),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    legacy_caution.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[legacy_caution], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄 주의사항",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [legacy_caution]


async def test_search_rescues_lower_score_exact_drug_function_heading() -> None:
    exact_function = build_chunk(
        0.536,
        title="로사르탄(losartan)",
        content=("효능.효과로사르탄 단일제는 고혈압과 고혈압이 있는 제2형 당뇨병 환자의 신장병 치료에 사용됩니다."),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    exact_function.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[exact_function], [exact_function]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄의 효능을 알려줘",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [exact_function]


async def test_search_prefers_explicit_requested_section_coverage() -> None:
    explicit_caution = build_chunk(
        0.62,
        chunk_id="1" * 64,
        title="로사르탄(losartan)",
        content="주의사항로사르탄 단일제의 주의사항입니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
        document_id="losartan",
    )
    ambiguous_continuation = build_chunk(
        0.604,
        chunk_id="2" * 64,
        title="로사르탄(losartan)",
        content="고칼륨혈증이 유발될 수 있으므로 주의합니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
        document_id="losartan",
    )
    explicit_function = build_chunk(
        0.536,
        chunk_id="3" * 64,
        title="로사르탄(losartan)",
        content="효능.효과로사르탄 단일제는 고혈압 치료에 사용됩니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
        document_id="losartan",
    )
    for chunk in (explicit_caution, ambiguous_continuation, explicit_function):
        chunk.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(
        responses=[
            [explicit_caution, ambiguous_continuation, explicit_function],
            [],
            [],
        ],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄의 효능과 주의사항을 알려줘",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [explicit_function, explicit_caution]


async def test_search_does_not_keep_wrong_legacy_section_after_heading_recovery() -> None:
    legacy_caution = build_chunk(
        0.5668,
        title="로사르탄(losartan)",
        content="주의사항로사르탄 단일제의 주의사항입니다.",
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    legacy_caution.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[legacy_caution], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄 효능",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == []


async def test_search_rescues_legacy_usage_heading_after_previous_sentence() -> None:
    legacy_usage = build_chunk(
        0.5668,
        title="로사르탄(losartan)",
        content=(
            "효능.효과로사르탄 단일제는 고혈압 치료에 사용됩니다. "
            "제품별 허가정보에서 확인할 수 있습니다. "
            "용법로사르탄 단일제는 1회 50 mg, 1일 1회 복용합니다."
        ),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    legacy_usage.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[legacy_usage], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄은 일반적으로 어떻게 복용하나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == [legacy_usage]


async def test_search_does_not_treat_body_word_as_legacy_section_heading() -> None:
    ordinary_function = build_chunk(
        0.5668,
        title="로사르탄(losartan)",
        content=("로사르탄은 혈압을 낮추는 데 사용됩니다. 복용 시 주의사항을 제품설명서에서 확인하십시오."),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.FUNCTION,
    )
    ordinary_function.metadata.drug_names = ["로사르탄(losartan)"]
    store = FakeKnowledgeStore(responses=[[ordinary_function], []])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    results = await retriever.search(
        question="로사르탄 주의사항",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert results == []


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


async def test_search_rescues_low_score_drug_food_chunk_only_when_both_entities_match() -> None:
    target = build_chunk(
        0.508,
        chunk_id="1" * 64,
        title="펙소페나딘(fexofenadine)",
        content=("자몽주스나 오렌지, 사과주스와 같은 과일주스는 펙소페나딘의 효과를 감소시킬 수 있다."),
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        section_type=KnowledgeSectionType.INTERACTION,
    )
    target.metadata.drug_names = ["펙소페나딘(fexofenadine)"]
    store = FakeKnowledgeStore(responses=[[target], [target]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search_with_diagnostics(
        question="펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert result.chunks == [target]
    assert result.diagnostics.accepted_count == 1
    assert result.diagnostics.rejected_below_score_count == 0


async def test_search_rejects_high_score_interaction_chunk_when_one_entity_is_missing() -> None:
    unrelated = build_chunk(
        0.78,
        chunk_id="2" * 64,
        title="약과 과일주스 상호작용",
        content="일부 의약품은 과일주스와 상호작용할 수 있다.",
        document_type=KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        section_type=KnowledgeSectionType.INTERACTION,
    )
    store = FakeKnowledgeStore(responses=[[unrelated], [unrelated]])
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search_with_diagnostics(
        question="펙소페나딘을 먹을 때 과일주스를 피해야 하나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert result.chunks == []
    assert result.diagnostics.rejected_pair_mismatch_count == 2


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

    result = await retriever.search_with_diagnostics(
        question="아연을 복용하면 철분 수치가 낮아질 수 있나요?",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert result.chunks == []
    assert result.diagnostics.rejected_pair_mismatch_count == 1


async def test_search_multi_entity_question_accepts_only_chunks_matching_a_pair() -> None:
    supported_pair = build_chunk(
        0.56,
        chunk_id="7" * 64,
        ingredient_names=["비타민 K"],
        title="와파린과 비타민 K",
        content="와파린과 비타민 K 섭취의 상호작용을 설명합니다.",
        document_type=KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        section_type=KnowledgeSectionType.INTERACTION,
    )
    supported_pair.metadata.drug_names = ["와파린"]
    single_entity = build_chunk(
        0.82,
        chunk_id="8" * 64,
        ingredient_names=["칼슘"],
        title="칼슘",
        content="칼슘의 기능을 설명합니다.",
        section_type=KnowledgeSectionType.INTERACTION,
    )
    store = FakeKnowledgeStore(
        responses=[
            [single_entity, supported_pair],
            [supported_pair],
            [],
            [],
        ],
    )
    retriever = MedicationKnowledgeRetriever(
        embedding_provider=FakeEmbeddingProvider(),
        vector_store=store,
        dataset_version="knowledge-full-v1",
        min_similarity_score=0.65,
    )

    result = await retriever.search_with_diagnostics(
        question="와파린, 비타민 K, 칼슘의 상호작용을 알려줘",
        medication_names=[],
        supplement_names=[],
        interaction_pair_keys=[],
        limit=5,
    )

    assert result.chunks == [supported_pair]
    assert result.diagnostics.rejected_pair_mismatch_count == 1


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
