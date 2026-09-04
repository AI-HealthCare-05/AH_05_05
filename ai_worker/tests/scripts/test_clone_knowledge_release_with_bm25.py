from argparse import Namespace

import pytest

from ai_worker.schemas.knowledge import KnowledgeSearchMode
from scripts import clone_knowledge_release_with_bm25 as module


def test_parse_args_requires_different_immutable_release_names() -> None:
    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--source-collection",
                "knowledge-v2",
                "--target-collection",
                "knowledge-v2",
            ]
        )


def test_build_cloner_uses_single_dense_source_and_hybrid_target() -> None:
    args = Namespace(
        source_collection="knowledge-v2",
        target_collection="knowledge-v2-hybrid",
        batch_size=64,
    )

    cloner = module.build_cloner(
        settings=module.Config(
            OPENAI_EMBEDDING_DIMENSIONS=1536,
            _env_file=None,
        ),
        args=args,
        client=object(),
    )

    assert cloner._source_store.collection_name == "knowledge-v2"
    assert cloner._target_store.collection_name == "knowledge-v2-hybrid"
    assert cloner._target_store.search_mode == KnowledgeSearchMode.HYBRID
