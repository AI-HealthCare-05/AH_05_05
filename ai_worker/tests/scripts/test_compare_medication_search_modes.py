import asyncio
from pathlib import Path

from ai_worker.core.config import Config
from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineReport,
    MedicationSearchModeComparisonReport,
    MedicationSearchModeDecision,
)
from scripts import compare_medication_search_modes as module
from scripts.compare_medication_search_modes import parse_args, render_markdown
from scripts.evaluate_medication_search_baseline import load_evaluation_manifest


def test_parse_args_accepts_distinct_dataset_versions_for_release_ab_test() -> None:
    """v5와 v6은 collection뿐 아니라 dataset version도 달라질 수 있다."""

    args = parse_args(
        [
            "--evaluation-file",
            "data/knowledge/evaluation/user_expression_queries_v3.yaml",
            "--dense-collection",
            "medication_knowledge_full_v5",
            "--dense-dataset-version",
            "knowledge-full-v5-o200k",
            "--hybrid-collection",
            "medication_knowledge_full_v6",
            "--hybrid-dataset-version",
            "knowledge-full-v6-o200k-source-backed",
            "--output",
            "output/comparison.md",
        ]
    )

    assert args.dense_dataset_version == "knowledge-full-v5-o200k"
    assert args.hybrid_dataset_version == "knowledge-full-v6-o200k-source-backed"


def test_mode_evaluation_builds_its_resolver_catalog_from_the_candidate_release(
    monkeypatch,
) -> None:
    """모드 비교가 활성 v5 설정으로 v6 질문 해석을 오염시키면 안 된다."""

    captured: dict[str, object] = {}
    catalog = object()
    expected_report = object()

    def build_catalog(**kwargs):
        captured["catalog_kwargs"] = kwargs
        return catalog

    class FakeEmbeddingProvider:
        def __init__(self, **kwargs) -> None:
            self.model_name = kwargs["model"]
            self.dimension = kwargs["dimensions"]

    class FakeEvaluator:
        def __init__(self, **kwargs) -> None:
            captured["resolver_catalog"] = kwargs["question_resolver"]._catalog

        async def evaluate(self, manifest, **kwargs):
            captured["manifest"] = manifest
            return expected_report

    monkeypatch.setattr(module, "build_runtime_expression_catalog", build_catalog)
    monkeypatch.setattr(module, "OpenAIEmbeddingProvider", FakeEmbeddingProvider)
    monkeypatch.setattr(module, "MedicationSearchBaselineEvaluator", FakeEvaluator)

    manifest = load_evaluation_manifest(
        Path("data/knowledge/evaluation/user_expression_queries_v3.yaml"),
    )
    result = asyncio.run(
        module._evaluate_mode(
            mode=KnowledgeSearchMode.DENSE,
            collection_name="medication_knowledge_full_v6",
            dataset_version="knowledge-full-v6-o200k-source-backed",
            manifest=manifest,
            settings=Config(
                _env_file=None,
                OPENAI_API_KEY="test-key",
                KNOWLEDGE_QDRANT_COLLECTION="medication_knowledge_full_v5",
                KNOWLEDGE_DATASET_VERSION="knowledge-full-v5-o200k",
            ),
            client=object(),
            evaluation_hash="a" * 64,
            git_commit="abc1234",
            working_tree_dirty=False,
        )
    )

    assert result is expected_report
    assert captured["resolver_catalog"] is catalog
    catalog_kwargs = captured["catalog_kwargs"]
    assert catalog_kwargs["settings"].KNOWLEDGE_QDRANT_COLLECTION == ("medication_knowledge_full_v5")
    assert catalog_kwargs["collection_name"] == "medication_knowledge_full_v6"
    assert catalog_kwargs["dataset_version"] == "knowledge-full-v6-o200k-source-backed"
    assert captured["manifest"].collection_name == "medication_knowledge_full_v6"
    assert captured["manifest"].dataset_version == "knowledge-full-v6-o200k-source-backed"


def build_report(mode: KnowledgeSearchMode) -> MedicationSearchBaselineReport:
    return MedicationSearchBaselineReport(
        experiment_goal="골드 문서 기준으로 Dense와 Hybrid를 비교합니다.",
        activation_rule=("정확도가 개선되고 안전 지표가 악화되지 않을 때만 Hybrid를 채택합니다."),
        metric_rationales={
            "mrr": "첫 정답 문서의 순위를 비교합니다.",
        },
        dataset_version="knowledge-full-v2-interaction-metadata",
        collection_name=f"knowledge-{mode.value.lower()}",
        search_mode=mode,
        min_similarity_score=0.65,
        final_top_k=5,
        candidate_top_k=20,
        git_commit="abc1234",
        working_tree_dirty=False,
        evaluation_file_sha256="f" * 64,
        query_count=14,
        active_query_count=14,
        active_pass_count=0,
        active_pass_rate=0.0,
        deferred_query_count=0,
        resolution_accuracy=1.0,
        scope_accuracy=1.0,
        correction_accuracy=1.0,
        false_correction_rate=0.0,
        ambiguity_accuracy=1.0,
        recall_at_20=0.8,
        hit_at_5=0.7,
        mrr=0.6,
        source_accuracy=0.9,
        evidence_coverage_rate=0.75,
        wrong_target_mixing_count=0,
        duplicate_retrieval_rate=0.0,
        fallback_rate=0.2,
        search_p50_ms=100.0,
        search_p95_ms=200.0,
        passed=False,
        results=[],
    )


def test_render_markdown_explains_accuracy_first_decision_and_all_modes() -> None:
    reports = {mode: build_report(mode) for mode in KnowledgeSearchMode}
    comparison = MedicationSearchModeComparisonReport(
        dense_collection_name="knowledge-dense",
        bm25_collection_name="knowledge-bm25",
        hybrid_collection_name="knowledge-hybrid",
        decision=MedicationSearchModeDecision.KEEP_DENSE,
        blocking_reasons=["NO_ACCURACY_IMPROVEMENT"],
    )

    rendered = render_markdown(
        reports=reports,
        comparison=comparison,
    )

    assert "정확도 우선" in rendered
    assert "DENSE" in rendered
    assert "BM25" in rendered
    assert "HYBRID" in rendered
    assert "근거 커버리지" in rendered
    assert "KEEP_DENSE" in rendered
    assert "골드 문서 기준으로 Dense와 Hybrid를 비교" in rendered
    assert "첫 정답 문서의 순위를 비교" in rendered
