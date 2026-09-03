import argparse
import asyncio
import hashlib
import subprocess
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
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
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.repositories.medication_expression_catalog_repository import (
    DbMedicationExpressionCatalog,
)
from ai_worker.schemas.medication_search_evaluation import (
    MedicationSearchBaselineManifest,
    MedicationSearchBaselineReport,
)
from app.core.db.databases import TORTOISE_ORM


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("사용자 표현 해석과 현재 단계적 검색의 고정 기준선을 측정합니다."),
    )
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.suffix.casefold() not in {".json", ".md"}:
        parser.error("--output 확장자는 .json 또는 .md여야 합니다.")
    return args


def load_evaluation_manifest(path: Path) -> MedicationSearchBaselineManifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return MedicationSearchBaselineManifest.model_validate(raw)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def working_tree_is_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(completed.stdout.strip())


def render_markdown(report: MedicationSearchBaselineReport) -> str:
    lines = [
        "# 사용자 표현·검색 기준선 보고서",
        "",
        f"- Git commit: `{report.git_commit}`",
        f"- 미커밋 변경 포함: {'예' if report.working_tree_dirty else '아니요'}",
        f"- Collection: `{report.collection_name}`",
        f"- Dataset: `{report.dataset_version}`",
        f"- Embedding: `{report.embedding_model_name}` / {report.embedding_dimension}",
        f"- 유사도 기준: {report.min_similarity_score}",
        f"- 후보/최종: Top-{report.candidate_top_k} / Top-{report.final_top_k}",
        f"- 평가 YAML SHA-256: `{report.evaluation_file_sha256}`",
        "",
        "## 집계",
        "",
        "| 지표 | 값 |",
        "|---|---:|",
        f"| 범위 판별 정확도 | {report.scope_accuracy:.3f} |",
        f"| 표현 처리 정확도 | {report.resolution_accuracy:.3f} |",
        f"| 자동 교정 정확도 | {report.correction_accuracy:.3f} |",
        f"| 오교정률 | {report.false_correction_rate:.3f} |",
        f"| 모호성 확인 정확도 | {report.ambiguity_accuracy:.3f} |",
        f"| Recall@20 | {report.recall_at_20:.3f} |",
        f"| Hit@5 | {report.hit_at_5:.3f} |",
        f"| MRR | {report.mrr:.3f} |",
        f"| 출처 정확도 | {report.source_accuracy:.3f} |",
        f"| P50 / P95 | {report.search_p50_ms:.1f} / {report.search_p95_ms:.1f} ms |",
        "",
        "## 질문별 결과",
        "",
        "| 질문 ID | 표현 유형 | 범위 | 처리 상태 | 후보 관련 순위 | Top-5 | 시간(ms) | 판정 |",
        "|---|---|---|---|---:|---|---:|---|",
    ]
    for result in report.results:
        candidate_rank = result.candidate_first_relevant_rank or "-"
        hit = "-" if result.hit_at_5 is None else ("PASS" if result.hit_at_5 else "FAIL")
        lines.append(
            "| "
            + " | ".join(
                [
                    result.query_id,
                    result.expression_category.value,
                    result.observed_scope.value,
                    result.observed_resolution_status.value,
                    str(candidate_rank),
                    hit,
                    f"{result.search_latency_ms:.1f}",
                    "PASS" if result.passed else ", ".join(result.failure_reasons),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: MedicationSearchBaselineReport, output_path: Path) -> None:
    content = report.model_dump_json(indent=2) if output_path.suffix.casefold() == ".json" else render_markdown(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> MedicationSearchBaselineReport:
    resolved_settings = settings or Config()
    manifest = load_evaluation_manifest(args.evaluation_file)
    api_key = resolved_settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("검색 기준선 평가에는 OPENAI_API_KEY가 필요합니다.")

    async with AsyncExitStack() as stack:
        await Tortoise.init(config=TORTOISE_ORM)
        stack.push_async_callback(Tortoise.close_connections)
        qdrant_client = AsyncQdrantClient(
            url=resolved_settings.QDRANT_URL,
            timeout=resolved_settings.QDRANT_TIMEOUT_SECONDS,
        )
        stack.push_async_callback(qdrant_client.close)
        embedding_provider = OpenAIEmbeddingProvider(
            model=resolved_settings.OPENAI_EMBEDDING_MODEL,
            dimensions=resolved_settings.OPENAI_EMBEDDING_DIMENSIONS,
            api_key=api_key,
            timeout_seconds=resolved_settings.OPENAI_TIMEOUT_SECONDS,
            max_retries=resolved_settings.OPENAI_MAX_RETRIES,
        )
        vector_store = QdrantKnowledgeStore(
            client=qdrant_client,
            collection_name=manifest.collection_name,
            vector_size=resolved_settings.OPENAI_EMBEDDING_DIMENSIONS,
        )
        evaluator = MedicationSearchBaselineEvaluator(
            question_resolver=RuleBasedMedicationQuestionResolver(
                catalog=DbMedicationExpressionCatalog(),
            ),
            query_builder=MedicationKnowledgeQueryBuilder(),
            knowledge_retriever=MedicationKnowledgeRetriever(
                embedding_provider=embedding_provider,
                vector_store=vector_store,
                dataset_version=manifest.dataset_version,
                min_similarity_score=manifest.min_similarity_score,
            ),
            embedding_model_name=embedding_provider.model_name,
            embedding_dimension=embedding_provider.dimension,
        )
        report = await evaluator.evaluate(
            manifest,
            git_commit=current_git_commit(),
            working_tree_dirty=working_tree_is_dirty(),
            evaluation_file_sha256=file_sha256(args.evaluation_file),
        )
        write_report(report, args.output)
        return report


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_cli(args=args))
    print(
        f"기준선 평가 완료: {sum(result.passed for result in report.results)}/"
        f"{report.query_count} 통과, 보고서={args.output}",
    )


if __name__ == "__main__":
    main()
