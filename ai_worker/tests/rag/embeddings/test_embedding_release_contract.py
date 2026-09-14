import pytest

from ai_worker.rag.embeddings.embedding_release_contract import (
    EmbeddingReleaseContract,
)
from ai_worker.schemas.knowledge import KnowledgeVectorDistance


def build_contract(**overrides) -> EmbeddingReleaseContract:
    values = {
        "model_name": "text-embedding-3-large",
        "dimensions": 3072,
        "distance": KnowledgeVectorDistance.DOT,
        "tokenizer_encoding": "cl100k_base",
        "chunking_version": "semantic-structure-v2",
        "embedding_text_version": "medical-retrieval-v2",
    }
    values.update(overrides)
    return EmbeddingReleaseContract(**values)


def test_release_contract_serializes_the_full_embedding_identity() -> None:
    manifest = build_contract().to_manifest(
        collection_name="medication_knowledge_full_v16_te3large_3072_dot",
        dataset_version="knowledge-full-v16",
    )

    assert manifest["embedding_model"] == "text-embedding-3-large"
    assert manifest["embedding_dimensions"] == 3072
    assert manifest["distance"] == "DOT"
    assert manifest["chunking_version"] == "semantic-structure-v2"
    assert manifest["embedding_text_version"] == "medical-retrieval-v2"


@pytest.mark.parametrize(
    "override",
    [
        {"model_name": "text-embedding-3-small"},
        {"dimensions": 1536},
        {"distance": KnowledgeVectorDistance.COSINE},
        {"chunking_version": "semantic-structure-v1"},
        {"embedding_text_version": "medical-retrieval-v1"},
    ],
)
def test_release_contract_rejects_vector_reuse_from_a_different_identity(override: dict) -> None:
    target = build_contract()
    source = build_contract(**override)

    with pytest.raises(ValueError, match="벡터 재사용"):
        target.assert_reuse_compatible(source)
