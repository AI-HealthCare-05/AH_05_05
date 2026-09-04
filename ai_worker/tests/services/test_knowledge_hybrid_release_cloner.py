from types import SimpleNamespace

import pytest

from ai_worker.services.knowledge_hybrid_release_cloner import (
    KnowledgeHybridReleaseCloner,
)


def build_point(*, chunk_id: str, vector: list[float]):
    return SimpleNamespace(
        vector=vector,
        payload={
            "chunk_id": chunk_id,
            "content": "마그네슘은 에너지 이용에 필요합니다.",
            "embedding_text": "[성분] 마그네슘\n마그네슘 기능성",
            "token_count": 12,
            "metadata": {
                "source_id": "source-a",
                "document_id": "document-a",
                "title": "마그네슘 기능성",
                "provider": "시험기관",
                "access_scope": "PUBLIC",
                "document_type": "SUPPLEMENT_CODE",
                "dataset_version": "knowledge-full-v2-interaction-metadata",
                "ingredient_names": ["마그네슘"],
                "section_type": "FUNCTION",
                "page_start": 1,
                "page_end": 1,
                "chunk_index": 0,
                "content_hash": "b" * 64,
            },
        },
    )


class FakeScrollClient:
    def __init__(self) -> None:
        self.calls = []

    async def scroll(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["offset"] is None:
            return [build_point(chunk_id="a" * 64, vector=[1.0, 0.0])], "next"
        return [build_point(chunk_id="c" * 64, vector=[0.0, 1.0])], None


class FakeSourceStore:
    collection_name = "knowledge-v2"

    async def count_points(self) -> int:
        return 2


class FakeTargetStore:
    collection_name = "knowledge-v2-hybrid"

    def __init__(self) -> None:
        self.created = False
        self.batches = []

    async def create_release_collection(self) -> None:
        self.created = True

    async def upsert_chunks(self, chunks, vectors):
        self.batches.append((chunks, vectors))
        return [chunk.chunk_id for chunk in chunks]

    async def count_points(self) -> int:
        return sum(len(chunks) for chunks, _ in self.batches)


async def test_clone_reuses_dense_vectors_and_validates_point_count() -> None:
    client = FakeScrollClient()
    target = FakeTargetStore()
    cloner = KnowledgeHybridReleaseCloner(
        client=client,
        source_store=FakeSourceStore(),
        target_store=target,
        batch_size=1,
    )

    result = await cloner.clone()

    assert result.source_count == 2
    assert result.target_count == 2
    assert result.batch_count == 2
    assert target.created is True
    assert target.batches[0][1] == [[1.0, 0.0]]
    assert target.batches[1][1] == [[0.0, 1.0]]
    assert client.calls[0]["with_vectors"] is True
    assert client.calls[0]["with_payload"] is True


async def test_clone_rejects_same_source_and_target_collection() -> None:
    target = FakeTargetStore()
    target.collection_name = "knowledge-v2"
    cloner = KnowledgeHybridReleaseCloner(
        client=FakeScrollClient(),
        source_store=FakeSourceStore(),
        target_store=target,
    )

    with pytest.raises(ValueError, match="서로 달라야"):
        await cloner.clone()

    assert target.created is False


async def test_clone_rejects_named_source_vector_instead_of_guessing() -> None:
    client = FakeScrollClient()

    async def scroll(**kwargs):
        return [build_point(chunk_id="a" * 64, vector={"dense": [1.0, 0.0]})], None

    client.scroll = scroll
    cloner = KnowledgeHybridReleaseCloner(
        client=client,
        source_store=FakeSourceStore(),
        target_store=FakeTargetStore(),
    )

    with pytest.raises(ValueError, match="단일 Dense 벡터"):
        await cloner.clone()
