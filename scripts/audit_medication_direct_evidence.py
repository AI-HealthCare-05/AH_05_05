"""QDRANT_GOLD 직접 근거가 검색 파이프라인에서 사라지는 지점을 감사한다."""

import argparse
import asyncio
from contextlib import AsyncExitStack
from pathlib import Path

from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient
from tortoise import Tortoise

from ai_worker.chains.medication_query_plan_chain import (
    MedicationQueryPlanChainInput,
    MedicationQuestionPlanResult,
    build_medication_query_plan_chain,
)
from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.domain.medication_question_resolver import (
    RuleBasedMedicationQuestionResolver,
)
from ai_worker.evaluation.medication_direct_evidence_audit import (
    DirectEvidenceAuditReport,
    MedicationDirectEvidenceAuditor,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.retrievers.medication_knowledge_retriever import (
    MedicationKnowledgeRetriever,
)
from ai_worker.schemas.medication_search import MedicationKnowledgeQueryPlan
from app.core.db.databases import TORTOISE_ORM
from scripts.evaluate_medication_search_baseline import (
    build_evaluation_expression_catalog,
    build_evaluation_vector_store,
    load_evaluation_manifest,
    resolve_evaluation_manifest,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QDRANT_GOLD 직접 근거의 최초 탈락 단계를 감사합니다.",
    )
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collection")
    parser.add_argument("--dataset-version")
    parser.add_argument(
        "--query-id",
        action="append",
        dest="query_ids",
        help="특정 QDRANT_GOLD query_id만 감사합니다. 여러 번 지정할 수 있습니다.",
    )
    args = parser.parse_args(argv)
    if args.output.suffix.casefold() not in {".json", ".md"}:
        parser.error("--output 확장자는 .json 또는 .md여야 합니다.")
    for field_name in ("collection", "dataset_version"):
        value = getattr(args, field_name)
        if value is not None and not value.strip():
            parser.error(f"--{field_name.replace('_', '-')}은 비어 있을 수 없습니다.")
    args.query_ids = list(dict.fromkeys(query_id.strip() for query_id in args.query_ids or [] if query_id.strip()))
    return args


def render_markdown(report: DirectEvidenceAuditReport) -> str:
    lines = [
        "# QDRANT_GOLD 직접 근거 단계 감사",
        "",
        f"- Collection: `{report.collection_name}`",
        f"- Dataset: `{report.dataset_version}`",
        f"- 감사 대상 gold 문서: {report.target_count}건",
        "",
        "## 최초 실패 단계 집계",
        "",
        "| 단계 | 문서 수 |",
        "|---|---:|",
    ]
    lines.extend(f"| {stage.value} | {count} |" for stage, count in sorted(report.stage_counts.items()))
    lines.extend(
        [
            "",
            "## 문서별 결과",
            "",
            "| 질문 ID | gold 문서 | 최초 단계 | raw rank | refiner 후 rank | 조정 rank | Top-5 |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for attribution in report.attributions:
        observation = attribution.observation
        lines.append(
            "| "
            + " | ".join(
                [
                    observation.query_id,
                    observation.expected_document_id,
                    attribution.first_failure_stage.value,
                    str(observation.exact_pair_raw_rank or "-"),
                    str(observation.refined_rank or "-"),
                    str(observation.adjusted_rank or "-"),
                    "PASS" if observation.selected_in_top_5 else "FAIL",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_report(report: DirectEvidenceAuditReport, output_path: Path) -> None:
    content = report.model_dump_json(indent=2) if output_path.suffix.casefold() == ".json" else render_markdown(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def build_embedding_provider(*, settings: Config, api_key: SecretStr) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=api_key,
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> DirectEvidenceAuditReport:
    resolved_settings = settings or Config()
    manifest = resolve_evaluation_manifest(
        load_evaluation_manifest(args.evaluation_file),
        args=args,
    )
    api_key = resolved_settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("직접 근거 감사에는 OPENAI_API_KEY가 필요합니다.")

    async with AsyncExitStack() as stack:
        await Tortoise.init(config=TORTOISE_ORM)
        stack.push_async_callback(Tortoise.close_connections)
        qdrant_client = AsyncQdrantClient(
            url=resolved_settings.QDRANT_URL,
            timeout=resolved_settings.QDRANT_TIMEOUT_SECONDS,
        )
        stack.push_async_callback(qdrant_client.close)
        vector_store = build_evaluation_vector_store(
            settings=resolved_settings,
            qdrant_client=qdrant_client,
            collection_name=manifest.collection_name,
        )
        resolver = RuleBasedMedicationQuestionResolver(
            catalog=build_evaluation_expression_catalog(
                settings=resolved_settings,
                qdrant_client=qdrant_client,
                collection_name=manifest.collection_name,
                dataset_version=manifest.dataset_version,
            ),
        )
        query_plan_chain = build_medication_query_plan_chain()
        embedding_provider = build_embedding_provider(settings=resolved_settings, api_key=api_key)

        async def plan_question(question: str) -> MedicationKnowledgeQueryPlan:
            resolution = await resolver.resolve(question=question)
            planned = await query_plan_chain.ainvoke(
                MedicationQueryPlanChainInput(
                    question=resolution.resolved_question,
                    resolution=resolution,
                )
            )
            return MedicationQuestionPlanResult.model_validate(planned).query_plan

        auditor = MedicationDirectEvidenceAuditor(
            collection_name=manifest.collection_name,
            dataset_version=manifest.dataset_version,
            vector_store=vector_store,
            query_planner=plan_question,
            retriever_factory=lambda tracing_store: MedicationKnowledgeRetriever(
                embedding_provider=embedding_provider,
                vector_store=tracing_store,
                dataset_version=manifest.dataset_version,
                min_similarity_score=manifest.min_similarity_score,
            ),
            limit=manifest.final_top_k,
        )
        report = await auditor.audit_manifest(
            manifest,
            query_ids=set(args.query_ids) if args.query_ids else None,
        )
        write_report(report, args.output)
        return report


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_cli(args=args))
    print(f"직접 근거 감사 완료: {report.target_count}건, 보고서={args.output}")


if __name__ == "__main__":
    main()
