from argparse import Namespace
from pathlib import Path

import pytest
from pydantic import SecretStr

from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationCase,
    KnowledgeEvaluationManifest,
    KnowledgeEvaluationReport,
    KnowledgeQueryEvaluationResult,
)
from scripts import evaluate_knowledge_retrieval as module


class FakeClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeEvaluator:
    def __init__(self, report: KnowledgeEvaluationReport) -> None:
        self.report = report
        self.received_manifest: KnowledgeEvaluationManifest | None = None

    async def evaluate(
        self,
        manifest: KnowledgeEvaluationManifest,
    ) -> KnowledgeEvaluationReport:
        self.received_manifest = manifest
        return self.report


def build_manifest() -> KnowledgeEvaluationManifest:
    return KnowledgeEvaluationManifest(
        dataset_version="knowledge-pilot-v1",
        cases=[
            KnowledgeEvaluationCase(
                query_id="vitamin-b6",
                query="비타민 B6 주의사항",
                expected_document_ids=["vitamin-b6-document"],
            )
        ],
    )


def build_report(*, passed: bool) -> KnowledgeEvaluationReport:
    return KnowledgeEvaluationReport(
        dataset_version="knowledge-pilot-v1",
        collection_name="medication_knowledge_pilot_v1",
        query_count=1,
        hit_at_5=1.0 if passed else 0.0,
        mrr=1.0 if passed else 0.0,
        citation_accuracy=1.0 if passed else 0.0,
        duplicate_retrieval_rate=0.0,
        wrong_entity_mixing_count=0,
        search_p95_ms=10.0,
        passed=passed,
        query_results=[
            KnowledgeQueryEvaluationResult(
                query_id="vitamin-b6",
                retrieved_document_ids=["vitamin-b6-document"],
                hit_at_5=passed,
                reciprocal_rank=1.0 if passed else 0.0,
                relevant_count=1 if passed else 0,
                retrieved_count=1,
                duplicate_count=0,
                wrong_entity_mixing_count=0,
                search_latency_ms=10.0,
            )
        ],
    )


async def test_run_cli_writes_report_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "report.json"
    args = Namespace(
        evaluation_file=tmp_path / "queries.yaml",
        dataset_version="knowledge-pilot-v1",
        collection="medication_knowledge_pilot_v1",
        output=output_path,
    )
    settings = module.Config(
        _env_file=None,
        OPENAI_API_KEY=SecretStr("test-key"),
    )
    manifest = build_manifest()
    report = build_report(passed=True)
    fake_client = FakeClient()
    fake_evaluator = FakeEvaluator(report)

    monkeypatch.setattr(
        module,
        "load_evaluation_manifest",
        lambda path: manifest,
    )
    monkeypatch.setattr(
        module,
        "create_qdrant_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        module,
        "build_evaluator",
        lambda **kwargs: fake_evaluator,
    )

    result = await module.run_cli(args=args, settings=settings)

    assert result == report
    assert fake_evaluator.received_manifest == manifest
    assert fake_client.closed is True
    assert KnowledgeEvaluationReport.model_validate_json(output_path.read_text(encoding="utf-8")) == report


def test_exit_code_is_two_when_quality_gate_fails() -> None:
    assert module.exit_code_for(build_report(passed=False)) == 2
    assert module.exit_code_for(build_report(passed=True)) == 0


def test_load_evaluation_manifest_reads_yaml(tmp_path: Path) -> None:
    path = tmp_path / "queries.yaml"
    path.write_text(
        """
schema_version: knowledge-retrieval-evaluation-v1
dataset_version: knowledge-pilot-v1
cases:
  - query_id: vitamin-b6
    query: 비타민 B6 섭취 시 주의사항은?
    expected_document_ids:
      - vitamin-b6-document
""".strip(),
        encoding="utf-8",
    )

    manifest = module.load_evaluation_manifest(path)

    assert manifest.cases[0].query_id == "vitamin-b6"
