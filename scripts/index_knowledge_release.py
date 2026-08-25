import argparse
import asyncio
import json
from pathlib import Path

from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.indexers.knowledge_indexer import (
    KnowledgeIndexer,
    KnowledgeIndexResult,
)
from ai_worker.rag.loaders.knowledge_chunk_loader import (
    KnowledgeChunkLoader,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전처리된 약·영양제 청크를 새 Qdrant release에 적재합니다.")
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/knowledge/processed/chunks"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--upsert-batch-size", type=int, default=64)
    parser.add_argument(
        "--allow-demo-restricted",
        action="store_true",
        help=("DEMO_RESTRICTED 청크를 외부 OpenAI 임베딩 API로 전송하는 것을 명시적으로 허용합니다."),
    )
    args = parser.parse_args(argv)
    if args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size는 1 이상이어야 합니다.")
    if args.upsert_batch_size <= 0:
        parser.error("--upsert-batch-size는 1 이상이어야 합니다.")
    if not args.dataset_version.strip():
        parser.error("--dataset-version은 비어 있을 수 없습니다.")
    if not args.collection.strip():
        parser.error("--collection은 비어 있을 수 없습니다.")
    return args


def create_qdrant_client(settings: Config) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def require_api_key(settings: Config) -> SecretStr:
    api_key = settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("Knowledge release 인덱싱에는 OPENAI_API_KEY가 필요합니다.")
    return api_key


def load_release_chunks(args: argparse.Namespace) -> list[KnowledgeChunk]:
    return KnowledgeChunkLoader().load(
        args.chunks_dir,
        expected_dataset_version=args.dataset_version,
    )


def ensure_external_embedding_allowed(
    chunks: list[KnowledgeChunk],
    *,
    allow_demo_restricted: bool,
) -> None:
    restricted_count = sum(chunk.metadata.access_scope == KnowledgeAccessScope.DEMO_RESTRICTED for chunk in chunks)
    if restricted_count and not allow_demo_restricted:
        raise ValueError(
            "DEMO_RESTRICTED 청크가 "
            f"{restricted_count}개 포함되어 있습니다. 외부 OpenAI "
            "임베딩 API 전송을 승인한 경우에만 "
            "--allow-demo-restricted를 지정하세요."
        )


def build_indexer(
    *,
    settings: Config,
    args: argparse.Namespace,
    qdrant_client: AsyncQdrantClient,
) -> KnowledgeIndexer:
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
    return KnowledgeIndexer(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        embedding_batch_size=args.embedding_batch_size,
        upsert_batch_size=args.upsert_batch_size,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> KnowledgeIndexResult:
    resolved_settings = settings or Config()
    qdrant_client = create_qdrant_client(resolved_settings)
    try:
        chunks = load_release_chunks(args)
        ensure_external_embedding_allowed(
            chunks,
            allow_demo_restricted=args.allow_demo_restricted,
        )
        indexer = build_indexer(
            settings=resolved_settings,
            args=args,
            qdrant_client=qdrant_client,
        )
        return await indexer.index_release(chunks)
    finally:
        await qdrant_client.close()


def main() -> None:
    result = asyncio.run(run_cli(args=parse_args()))
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "collection_name": result.collection_name,
                "indexed_chunk_count": result.indexed_chunk_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
