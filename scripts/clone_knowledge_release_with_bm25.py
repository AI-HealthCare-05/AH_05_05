import argparse
import asyncio
import json

from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.rag.vectorstores.qdrant_hybrid_knowledge_store import (
    QdrantHybridKnowledgeStore,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge import KnowledgeSearchMode
from ai_worker.services.knowledge_hybrid_release_cloner import (
    KnowledgeHybridCloneResult,
    KnowledgeHybridReleaseCloner,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "기존 단일 Dense Qdrant 릴리스를 Dense+BM25 named-vector "
            "실험 릴리스로 복제합니다. OpenAI 재임베딩은 수행하지 않습니다."
        ),
    )
    parser.add_argument("--source-collection", required=True)
    parser.add_argument("--target-collection", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args(argv)
    if not args.source_collection.strip():
        parser.error("--source-collection은 비어 있을 수 없습니다.")
    if not args.target_collection.strip():
        parser.error("--target-collection은 비어 있을 수 없습니다.")
    if args.source_collection == args.target_collection:
        parser.error("원본과 대상 컬렉션 이름은 서로 달라야 합니다.")
    if args.batch_size <= 0:
        parser.error("--batch-size는 1 이상이어야 합니다.")
    return args


def build_cloner(
    *,
    settings: Config,
    args: argparse.Namespace,
    client: AsyncQdrantClient,
) -> KnowledgeHybridReleaseCloner:
    source_store = QdrantKnowledgeStore(
        client=client,
        collection_name=args.source_collection,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
    )
    target_store = QdrantHybridKnowledgeStore(
        client=client,
        collection_name=args.target_collection,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
        search_mode=KnowledgeSearchMode.HYBRID,
    )
    return KnowledgeHybridReleaseCloner(
        client=client,
        source_store=source_store,
        target_store=target_store,
        batch_size=args.batch_size,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> KnowledgeHybridCloneResult:
    resolved_settings = settings or Config()
    client = AsyncQdrantClient(
        url=resolved_settings.QDRANT_URL,
        timeout=resolved_settings.QDRANT_TIMEOUT_SECONDS,
    )
    try:
        cloner = build_cloner(
            settings=resolved_settings,
            args=args,
            client=client,
        )
        return await cloner.clone()
    finally:
        await client.close()


def main() -> None:
    result = asyncio.run(run_cli(args=parse_args()))
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
