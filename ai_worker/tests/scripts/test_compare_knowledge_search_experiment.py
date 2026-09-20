from types import SimpleNamespace

import pytest
from qdrant_client.http import models

from ai_worker.schemas.knowledge_evaluation import KnowledgeEvaluationCase, KnowledgeEvaluationManifest
from scripts import compare_knowledge_search_experiment as module


class FakeClient:
    def __init__(self, *, changed=False, dimension=1536, vector_changed=False, empty=False):
        self.changed = changed
        self.dimension = dimension
        self.vector_changed = vector_changed
        self.empty = empty
        self.scrolled = []

    async def get_collection(self, name):
        vector = models.VectorParams(size=self.dimension, distance=models.Distance.COSINE)
        vectors = vector if name == "dense" else {"dense": vector}
        sparse = {} if name == "dense" else {"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)}
        return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors, sparse_vectors=sparse)))

    async def count(self, *, collection_name, exact):
        return SimpleNamespace(count=0 if self.empty else 1)

    async def scroll(self, *, collection_name, offset, limit, with_payload, with_vectors):
        self.scrolled.append((collection_name, with_vectors))
        if self.empty:
            return [], None
        payload = {
            "chunk_id": "chunk",
            "content": "different" if self.changed and collection_name == "hybrid" else "same",
            "embedding_text": "same embedding",
            "token_count": 2,
            "metadata": {"dataset_version": "v1", "document_id": "gold"},
        }
        vector = ([0.2] if self.vector_changed and collection_name == "hybrid" else [0.1]) * self.dimension
        return [
            SimpleNamespace(
                id="point-id", payload=payload, vector=vector if collection_name == "dense" else {"dense": vector}
            )
        ], None


class FakeEmbedding:
    model_name = "test"
    dimension = 1536

    def __init__(self):
        self.calls = []

    async def embed_query(self, query):
        self.calls.append(query)
        return [0.1] * self.dimension


class FailingEmbedding:
    async def embed_query(self, query):
        raise RuntimeError("embedding unavailable")


class FakeStore:
    def __init__(self, name, calls, *, fail=False):
        self.name = name
        self.calls = calls
        self.fail = fail

    async def search(self, *, query_vector, search_query):
        self.calls.append((self.name, search_query))
        if self.fail:
            raise RuntimeError("search failed")
        return [
            SimpleNamespace(
                chunk_id="chunk",
                content="review me",
                similarity_score=0.7,
                dense_similarity_score=0.6,
                metadata=FakeMetadata(),
            )
        ]


class FakeMetadata:
    document_id = "gold"
    section_type = "OTHER"
    drug_names = ["drug"]
    ingredient_names = []
    interaction_pair_keys = []

    def model_dump(self, *, mode):
        return {"document_id": self.document_id, "section_type": self.section_type, "drug_names": self.drug_names}


def manifest():
    return KnowledgeEvaluationManifest(
        dataset_version="v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="q1",
                query="question",
                expected_document_ids=["gold"],
                drug_names=["drug"],
                top_k=5,
            )
        ],
    )


def test_unfiltered_query_keeps_dataset_and_access_eligibility():
    query = module._search_query(manifest().cases[0], "v1", "semantic_unfiltered")
    filters = module.EligibleDenseStore._build_filter(query).model_dump(mode="json")
    assert query.dataset_version == "v1"
    assert query.drug_names == []
    assert any(condition.get("key") == "metadata.index_eligible" for condition in filters["must"])
    assert any(condition.get("key") == "metadata.access_scope" for condition in filters["must"])


def test_hybrid_preserves_production_score_normalization():
    assert module.EligibleHybridStore._bounded_relevance_score(0.03125) == 0.03125 / 1.03125


async def test_fingerprint_streams_vectors_and_rejects_mismatch():
    client = FakeClient()
    result = await module.verify_collections(client, "dense", "hybrid", "v1", 1536, models.Distance.COSINE)
    assert result["dense"]["fingerprint"] == result["hybrid"]["fingerprint"]
    assert client.scrolled == [("dense", True), ("hybrid", True)]
    with pytest.raises(ValueError, match="fingerprint"):
        await module.verify_collections(FakeClient(changed=True), "dense", "hybrid", "v1", 1536, models.Distance.COSINE)
    with pytest.raises(ValueError, match="dimension"):
        await module.verify_collections(FakeClient(dimension=42), "dense", "hybrid", "v1", 1536, models.Distance.COSINE)
    with pytest.raises(ValueError, match="fingerprint"):
        await module.verify_collections(
            FakeClient(vector_changed=True), "dense", "hybrid", "v1", 1536, models.Distance.COSINE
        )
    with pytest.raises(ValueError, match="empty"):
        await module.verify_collections(FakeClient(empty=True), "dense", "hybrid", "v1", 1536, models.Distance.COSINE)


async def test_shared_embedding_warmup_order_filters_and_error_recording():
    calls = []
    embedding = FakeEmbedding()
    report = await module.compare(
        manifest(),
        embedding,
        {"dense": FakeStore("dense", calls), "hybrid": FakeStore("hybrid", calls, fail=True)},
        repeats=2,
    )
    assert embedding.calls == ["question"]
    assert len(calls) == 12  # two tracks, two warmups and four measured searches each
    assert [name for name, _ in calls[:6]] == ["dense", "hybrid", "dense", "hybrid", "hybrid", "dense"]
    assert calls[0][1].drug_names == ["drug"]
    assert calls[6][1].drug_names == []
    measured = report["results"]
    assert len(measured) == 8
    dense = next(item for item in measured if item["mode"] == "dense")
    assert dense["document_hit_at_5_proxy"] is True
    assert dense["retrieved"][0]["content"] == "review me"
    assert dense["retrieved"][0]["store_score"] == 0.7
    assert dense["retrieved"][0]["metadata"]["document_id"] == "gold"
    assert dense["retrieved"][0]["strict_metadata_relevant"] is True
    assert dense["retrieved"][0]["forbidden_entity_or_document_hit"] is False
    assert dense["strict_metadata_hit_at_5"] is True
    assert dense["strict_metadata_reciprocal_rank"] == 1.0
    assert dense["forbidden_entity_or_document_hit_at_5"] is False
    assert dense["embedding_ms"] >= 0
    assert dense["search_refiner_ms"] >= 0
    assert sum(item["error"] is not None for item in measured) == 4


async def test_evaluator_hit_requires_all_expected_sections_even_when_any_hit_succeeds():
    case = manifest().cases[0].model_copy(update={"expected_section_types": ["OTHER", "CAUTION"]})
    evaluation = manifest().model_copy(update={"cases": [case]})
    report = await module.compare(
        evaluation,
        FakeEmbedding(),
        {"dense": FakeStore("dense", []), "hybrid": FakeStore("hybrid", [])},
        repeats=1,
    )
    for result in report["results"]:
        assert result["strict_metadata_hit_at_5"] is True
        assert result["section_coverage"] is False
        assert result["evaluator_hit_at_5"] is False


async def test_embedding_failure_aborts_entire_comparison():
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        await module.compare(
            manifest(),
            FailingEmbedding(),
            {"dense": FakeStore("dense", []), "hybrid": FakeStore("hybrid", [])},
            repeats=1,
        )
