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
        interaction_annotations=None,
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
    monkeypatch.setattr(
        module,
        "ensure_interaction_annotations_applied",
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
    assert default_args.interaction_annotations is None


def test_parse_args_accepts_interaction_annotation_contract() -> None:
    args = module.parse_args(
        [
            "--dataset-version",
            "knowledge-full-v2-interaction-metadata",
            "--collection",
            "medication_knowledge_full_v2",
            "--interaction-annotations",
            "data/knowledge/manifests/interaction_annotations.yaml",
        ]
    )

    assert args.interaction_annotations == Path("data/knowledge/manifests/interaction_annotations.yaml")


def test_rejects_release_when_required_annotation_pair_is_missing(
    tmp_path: Path,
) -> None:
    annotation_path = tmp_path / "annotations.yaml"
    annotation_path.write_text(
        """
documents:
  - document_id: mfds-guide
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [펙소페나딘]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스]
""".strip(),
        encoding="utf-8",
    )
    chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            document_id="mfds-guide",
            interaction_pair_keys=[],
        ),
    )

    with pytest.raises(ValueError, match="주석.*적용"):
        module.ensure_interaction_annotations_applied(
            [chunk],
            annotation_path=annotation_path,
        )


def test_rejects_annotation_pair_found_only_in_the_wrong_document(
    tmp_path: Path,
) -> None:
    annotation_path = tmp_path / "annotations.yaml"
    annotation_path.write_text(
        """
documents:
  - document_id: expected-document
    pairs:
      - pair_type: DRUG_FOOD
        left:
          kind: DRUG
          display_name: 펙소페나딘
          aliases: [펙소페나딘]
        right:
          kind: FOOD
          display_name: 과일주스
          aliases: [과일주스]
""".strip(),
        encoding="utf-8",
    )
    registry = module.KnowledgeInteractionAnnotationRegistry.from_yaml(annotation_path)
    chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            document_id="wrong-document",
            interaction_pair_keys=registry.required_pair_keys(),
        ),
    )

    with pytest.raises(ValueError, match="expected-document"):
        module.ensure_interaction_annotations_applied(
            [chunk],
            annotation_path=annotation_path,
        )


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
    chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            source_id="supplement_code",
            document_id="vitamin-a",
        )
    )

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
    chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            source_id="supplement_code",
            document_id="vitamin-a",
        )
    )

    module.ensure_preprocessing_approved(
        [chunk],
        quality_report_path=quality_report,
        expected_dataset_version="knowledge-pilot-v1",
    )


def test_rejects_stale_quality_report_with_different_chunk_count(
    tmp_path: Path,
) -> None:
    quality_report = tmp_path / "preprocessing-quality.json"
    quality_report.write_text(
        json.dumps(
            {
                "dataset_version": "knowledge-pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 2,
                "ready_for_bulk_source_ids": ["supplement_code"],
            }
        ),
        encoding="utf-8",
    )
    chunk = SimpleNamespace(
        metadata=SimpleNamespace(
            source_id="supplement_code",
            document_id="vitamin-a",
        )
    )

    with pytest.raises(ValueError, match="청크 수"):
        module.ensure_preprocessing_approved(
            [chunk],
            quality_report_path=quality_report,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_rejects_stale_quality_report_with_different_document_count(
    tmp_path: Path,
) -> None:
    quality_report = tmp_path / "preprocessing-quality.json"
    quality_report.write_text(
        json.dumps(
            {
                "dataset_version": "knowledge-pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 2,
                "ready_for_bulk_source_ids": ["supplement_code"],
            }
        ),
        encoding="utf-8",
    )
    chunks = [
        SimpleNamespace(
            metadata=SimpleNamespace(
                source_id="supplement_code",
                document_id=document_id,
            )
        )
        for document_id in ("vitamin-a", "vitamin-b6")
    ]

    with pytest.raises(ValueError, match="문서 수"):
        module.ensure_preprocessing_approved(
            chunks,
            quality_report_path=quality_report,
            expected_dataset_version="knowledge-pilot-v1",
        )
