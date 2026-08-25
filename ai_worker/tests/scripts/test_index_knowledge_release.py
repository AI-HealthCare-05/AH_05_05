import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from ai_worker.rag.indexers.knowledge_indexer import (
    KnowledgeIndexResult,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
)
from scripts import index_knowledge_release as module


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeIndexer:
    def __init__(self, result: KnowledgeIndexResult) -> None:
        self.result = result
        self.received_chunks: list[KnowledgeChunk] | None = None

    async def index_release(
        self,
        chunks: list[KnowledgeChunk],
    ) -> KnowledgeIndexResult:
        self.received_chunks = chunks
        return self.result


async def test_run_cli_loads_release_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    args = Namespace(
        chunks_dir=tmp_path,
        quality_report=tmp_path / "preprocessing-quality.json",
        dataset_version="knowledge-pilot-v1",
        collection="medication_knowledge_pilot_v1",
        embedding_batch_size=64,
        upsert_batch_size=64,
        allow_demo_restricted=False,
    )
    settings = module.Config(
        _env_file=None,
        OPENAI_API_KEY=SecretStr("test-key"),
    )
    fake_client = FakeClient()
    fake_chunks: list[KnowledgeChunk] = []
    fake_indexer = FakeIndexer(
        KnowledgeIndexResult(
            dataset_version="knowledge-pilot-v1",
            collection_name="medication_knowledge_pilot_v1",
            indexed_chunk_count=480,
        )
    )
    received: dict[str, object] = {}

    def fake_load_release_chunks(
        received_args: Namespace,
    ) -> list[KnowledgeChunk]:
        received["load_args"] = received_args
        return fake_chunks

    def fake_build_indexer(
        *,
        settings: module.Config,
        args: Namespace,
        qdrant_client: object,
    ) -> FakeIndexer:
        received["settings"] = settings
        received["build_args"] = args
        received["client"] = qdrant_client
        return fake_indexer

    monkeypatch.setattr(
        module,
        "create_qdrant_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        module,
        "load_release_chunks",
        fake_load_release_chunks,
    )
    monkeypatch.setattr(module, "build_indexer", fake_build_indexer)
    monkeypatch.setattr(
        module,
        "ensure_preprocessing_approved",
        lambda chunks, **kwargs: None,
    )

    result = await module.run_cli(args=args, settings=settings)

    assert result.indexed_chunk_count == 480
    assert fake_indexer.received_chunks is fake_chunks
    assert fake_client.closed is True
    assert received["client"] is fake_client
    assert received["load_args"] is args


def test_parse_args_rejects_zero_batch_size() -> None:
    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--dataset-version",
                "knowledge-pilot-v1",
                "--collection",
                "medication_knowledge_pilot_v1",
                "--embedding-batch-size",
                "0",
            ]
        )


def test_parse_args_requires_explicit_demo_restricted_opt_in() -> None:
    default_args = module.parse_args(
        [
            "--dataset-version",
            "knowledge-pilot-v1",
            "--collection",
            "medication_knowledge_pilot_v1",
        ]
    )
    approved_args = module.parse_args(
        [
            "--dataset-version",
            "knowledge-pilot-v1",
            "--collection",
            "medication_knowledge_pilot_v1",
            "--allow-demo-restricted",
        ]
    )

    assert default_args.allow_demo_restricted is False
    assert approved_args.allow_demo_restricted is True
    assert default_args.quality_report == Path("data/knowledge/processed/reports/preprocessing-quality.json")


def test_rejects_demo_restricted_chunks_without_explicit_opt_in() -> None:
    restricted_chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        )
    )

    with pytest.raises(
        ValueError,
        match="allow-demo-restricted",
    ):
        module.ensure_external_embedding_allowed(
            [restricted_chunk],
            allow_demo_restricted=False,
        )

    module.ensure_external_embedding_allowed(
        [restricted_chunk],
        allow_demo_restricted=True,
    )


def test_rejects_chunks_from_source_without_completed_approval(
    tmp_path: Path,
) -> None:
    quality_report = tmp_path / "preprocessing-quality.json"
    quality_report.write_text(
        json.dumps(
            {
                "dataset_version": "knowledge-pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": [],
            }
        ),
        encoding="utf-8",
    )
    chunk = SimpleNamespace(metadata=SimpleNamespace(source_id="supplement_code"))

    with pytest.raises(ValueError, match="승인"):
        module.ensure_preprocessing_approved(
            [chunk],
            quality_report_path=quality_report,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_accepts_chunks_only_from_approved_sources(
    tmp_path: Path,
) -> None:
    quality_report = tmp_path / "preprocessing-quality.json"
    quality_report.write_text(
        json.dumps(
            {
                "dataset_version": "knowledge-pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": ["supplement_code"],
            }
        ),
        encoding="utf-8",
    )
    chunk = SimpleNamespace(metadata=SimpleNamespace(source_id="supplement_code"))

    module.ensure_preprocessing_approved(
        [chunk],
        quality_report_path=quality_report,
        expected_dataset_version="knowledge-pilot-v1",
    )
