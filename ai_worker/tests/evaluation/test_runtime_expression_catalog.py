from ai_worker.core.config import Config
from ai_worker.evaluation.runtime_expression_catalog import (
    build_runtime_expression_catalog,
)


def test_runtime_catalog_uses_the_release_being_evaluated() -> None:
    """활성 v5 설정이 있어도 v6 평가에는 v6 metadata를 읽어야 한다."""

    settings = Config(
        _env_file=None,
        KNOWLEDGE_QDRANT_COLLECTION="medication_knowledge_full_v5",
        KNOWLEDGE_DATASET_VERSION="knowledge-full-v5-o200k",
    )

    catalog = build_runtime_expression_catalog(
        settings=settings,
        qdrant_client=object(),
        collection_name="medication_knowledge_full_v6",
        dataset_version="knowledge-full-v6-o200k-source-backed",
    )

    supplement_catalog = catalog._supplement_catalog
    assert supplement_catalog is not None
    qdrant_source = supplement_catalog._sources[1]
    assert qdrant_source._collection_name == "medication_knowledge_full_v6"
    assert qdrant_source._dataset_version == "knowledge-full-v6-o200k-source-backed"
