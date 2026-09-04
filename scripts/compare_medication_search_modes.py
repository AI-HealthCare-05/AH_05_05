import argparse
import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from tortoise import Tortoise

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.evaluation.medication_search_baseline_evaluator import (
    MedicationSearchBaselineEvaluator,
)
from ai_worker.evaluation.medication_search_mode_comparator import (
    MedicationSearchModeComparator,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import (
    QdrantHybridKnowledgeStore,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
)
from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineManifest,
    MedicationSearchBaselineReport,
    MedicationSearchModeComparisonReport,
)
from app.core.db.databases import TORTOISE_ORM
from scripts.evaluate_medication_search_baseline import (
    current_git_commit,
    file_sha256,
    load_evaluation_manifest,
    working_tree_is_dirty,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("동일 평가 질문으로 Dense·BM25·RRF Hybrid 검색을 비교하고 정확도 우선 활성화 여부를 판정합니다."),
    )
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--dense-collection", required=True)
    parser.add_argument("--hybrid-collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.suffix.casefold() != ".md":
        parser.error("--output은 Markdown(.md) 파일이어야 합니다.")
    if args.dense_collection == args.hybrid_collection:
        parser.error("Dense와 Hybrid 컬렉션은 서로 달라야 합니다.")
    return args


def render_markdown(
    *,
    reports: dict[KnowledgeSearchMode, MedicationSearchBaselineReport],
    comparison: MedicationSearchModeComparisonReport,
) -> str:
    lines = [
        "# Dense·BM25·Hybrid 검색 비교 실험",
        "",
        "- 판정 원칙: 속도보다 정확도 우선",
        f"- 최종 결정: `{comparison.decision.value}`",
        "- 차단 사유: " + (", ".join(comparison.blocking_reasons) or "없음"),
        "- 경고: " + (", ".join(comparison.warning_reasons) or "없음"),
        "",
        "## 실험 근거",
        "",
        f"- 목적: {reports[KnowledgeSearchMode.DENSE].experiment_goal or '기록되지 않음'}",
        f"- 채택 기준: {reports[KnowledgeSearchMode.DENSE].activation_rule or '기록되지 않음'}",
        "",
        "| 지표 | 선정 이유 |",
        "|---|---|",
        *[
            f"| {name} | {rationale} |"
            for name, rationale in reports[KnowledgeSearchMode.DENSE].metric_rationales.items()
        ],
        "",
        "## 모드별 결과",
        "",
        "| 모드 | Recall@20 | Hit@5 | MRR | 출처 정확도 | 근거 커버리지 | 잘못된 대상 혼입 | 중복률 | P95(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in KnowledgeSearchMode:
        report = reports[mode]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode.value,
                    f"{report.recall_at_20:.3f}",
                    f"{report.hit_at_5:.3f}",
                    f"{report.mrr:.3f}",
                    f"{report.source_accuracy:.3f}",
                    f"{report.evidence_coverage_rate:.3f}",
                    str(report.wrong_target_mixing_count),
                    f"{report.duplicate_retrieval_rate:.3f}",
                    f"{report.search_p95_ms:.1f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Hybrid - Dense 변화량",
            "",
            "| 지표 | 변화량 |",
            "|---|---:|",
            *[f"| {name} | {value:+.6f} |" for name, value in comparison.metric_deltas.items()],
            "",
            "Hybrid는 Hit@5 또는 MRR이 개선되고 Recall@20·출처 정확도·근거 "
            "커버리지가 하락하지 않으며 잘못된 대상 혼입과 중복이 늘지 않을 "
            "때만 활성화 후보가 됩니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _vector_store(
    *,
    mode: KnowledgeSearchMode,
    client: AsyncQdrantClient,
    collection_name: str,
    vector_size: int,
):
    kwargs = {
        "client": client,
        "collection_name": collection_name,
        "vector_size": vector_size,
    }
    if mode == KnowledgeSearchMode.DENSE:
        return QdrantKnowledgeStore(**kwargs)
    return QdrantHybridKnowledgeStore(search_mode=mode, **kwargs)


async def _evaluate_mode(
    *,
    mode: KnowledgeSearchMode,
    collection_name: str,
    manifest: MedicationSearchBaselineManifest,
    settings: Config,
    client: AsyncQdrantClient,
    evaluation_hash: str,
    git_commit: str,
    working_tree_dirty: bool,
) -> MedicationSearchBaselineReport:
    api_key = settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("검색 모드 비교에는 OPENAI_API_KEY가 필요합니다.")
    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=api_key,
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    evaluator = MedicationSearchBaselineEvaluator(
        question_resolver=RuleBasedMedicationQuestionResolver(
            catalog=DbMedicationExpressionCatalog(),
        ),
        query_builder=MedicationKnowledgeQueryBuilder(),
        knowledge_retriever=MedicationKnowledgeRetriever(
            embedding_provider=embedding_provider,
            vector_store=_vector_store(
                mode=mode,
                client=client,
                collection_name=collection_name,
                vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
            ),
            dataset_version=manifest.dataset_version,
            min_similarity_score=manifest.min_similarity_score,
        ),
        embedding_model_name=embedding_provider.model_name,
        embedding_dimension=embedding_provider.dimension,
        search_mode=mode,
    )
    return await evaluator.evaluate(
        manifest.model_copy(update={"collection_name": collection_name}),
        git_commit=git_commit,
        working_tree_dirty=working_tree_dirty,
        evaluation_file_sha256=evaluation_hash,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> MedicationSearchModeComparisonReport:
    resolved_settings = settings or Config()
    manifest = load_evaluation_manifest(args.evaluation_file)
    evaluation_hash = file_sha256(args.evaluation_file)
    commit = current_git_commit()
    dirty = working_tree_is_dirty()
    async with AsyncExitStack() as stack:
        await Tortoise.init(config=TORTOISE_ORM)
        stack.push_async_callback(Tortoise.close_connections)
        client = AsyncQdrantClient(
            url=resolved_settings.QDRANT_URL,
            timeout=resolved_settings.QDRANT_TIMEOUT_SECONDS,
        )
        stack.push_async_callback(client.close)
        reports = {}
        for mode in KnowledgeSearchMode:
            collection = args.dense_collection if mode == KnowledgeSearchMode.DENSE else args.hybrid_collection
            reports[mode] = await _evaluate_mode(
                mode=mode,
                collection_name=collection,
                manifest=manifest,
                settings=resolved_settings,
                client=client,
                evaluation_hash=evaluation_hash,
                git_commit=commit,
                working_tree_dirty=dirty,
            )

    comparison = MedicationSearchModeComparator().compare(
        dense=reports[KnowledgeSearchMode.DENSE],
        bm25=reports[KnowledgeSearchMode.BM25],
        hybrid=reports[KnowledgeSearchMode.HYBRID],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_markdown(reports=reports, comparison=comparison),
        encoding="utf-8",
    )
    for mode, report in reports.items():
        path = args.output.with_name(f"{args.output.stem}-{mode.value.casefold()}.json")
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    args.output.with_name(f"{args.output.stem}-decision.json").write_text(
        comparison.model_dump_json(indent=2), encoding="utf-8"
    )
    return comparison


def main() -> None:
    args = parse_args()
    comparison = asyncio.run(run_cli(args=args))
    print(
        json.dumps(
            comparison.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
