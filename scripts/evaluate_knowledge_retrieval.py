import argparse
import asyncio
from pathlib import Path

import yaml
from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.evaluators.knowledge_retrieval_evaluator import (
    KnowledgeRetrievalEvaluator,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge_evaluation import (
    KnowledgeEvaluationManifest,
    KnowledgeEvaluationReport,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="약·영양제 Knowledge release의 검색 품질을 평가합니다.")
    parser.add_argument("--evaluation-file", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.dataset_version.strip():
        parser.error("--dataset-version은 비어 있을 수 없습니다.")
    if not args.collection.strip():
        parser.error("--collection은 비어 있을 수 없습니다.")
    return args


def load_evaluation_manifest(path: Path) -> KnowledgeEvaluationManifest:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return KnowledgeEvaluationManifest.model_validate(raw)


def create_qdrant_client(settings: Config) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def require_api_key(settings: Config) -> SecretStr:
    api_key = settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("Knowledge 검색 평가에는 OPENAI_API_KEY가 필요합니다.")
    return api_key


def build_evaluator(
    *,
    settings: Config,
    args: argparse.Namespace,
    qdrant_client: AsyncQdrantClient,
) -> KnowledgeRetrievalEvaluator:
    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=require_api_key(settings),
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )
    vector_store = QdrantKnowledgeStore(
        client=qdrant_client,
        collection_name=args.collection,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    return KnowledgeRetrievalEvaluator(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> KnowledgeEvaluationReport:
    resolved_settings = settings or Config()
    manifest = load_evaluation_manifest(args.evaluation_file)
    manifest = manifest.model_copy(update={"dataset_version": args.dataset_version.strip()})

    qdrant_client = create_qdrant_client(resolved_settings)
    try:
        evaluator = build_evaluator(
            settings=resolved_settings,
            args=args,
            qdrant_client=qdrant_client,
        )
        report = await evaluator.evaluate(manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report
    finally:
        await qdrant_client.close()


def exit_code_for(report: KnowledgeEvaluationReport) -> int:
    return 0 if report.passed else 2


def main() -> None:
    report = asyncio.run(run_cli(args=parse_args()))
    print(report.model_dump_json(indent=2))
    raise SystemExit(exit_code_for(report))


if __name__ == "__main__":
    main()
