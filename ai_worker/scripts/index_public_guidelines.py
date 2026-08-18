import argparse
import asyncio
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from qdrant_client import AsyncQdrantClient

from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.indexers.guideline_indexer import (
    GuidelineIndexer,
)
from ai_worker.rag.loaders.manifest_loader import (
    GuidelineManifestLoader,
)
from ai_worker.rag.loaders.pdf_loader import (
    PdfLoader,
)
from ai_worker.rag.splitters.guideline_splitter import (
    GuidelineSplitter,
)
from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)


class IndexSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: SecretStr
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "public_guidelines_small_v1"


def create_qdrant_client(
    settings: IndexSettings,
) -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.QDRANT_URL)


def build_indexer(
    *,
    settings: IndexSettings,
    args: argparse.Namespace,
    qdrant_client: AsyncQdrantClient,
) -> GuidelineIndexer:
    embedding_provider = OpenAIEmbeddingProvider(
        model=(settings.OPENAI_EMBEDDING_MODEL),
        dimensions=(settings.OPENAI_EMBEDDING_DIMENSIONS),
        api_key=settings.OPENAI_API_KEY,
    )

    vector_store = QdrantGuidelineStore(
        client=qdrant_client,
        collection_name=(settings.QDRANT_COLLECTION),
        vector_size=(settings.OPENAI_EMBEDDING_DIMENSIONS),
    )

    return GuidelineIndexer(
        loader=PdfLoader(),
        splitter=GuidelineSplitter(
            chunk_size=args.chunk_size,
            chunk_overlap=(args.chunk_overlap),
        ),
        embedding_provider=(embedding_provider),
        vector_store=vector_store,
    )


async def run_indexing(
    *,
    manifest_path: Path,
    manifest_loader: GuidelineManifestLoader,
    indexer: GuidelineIndexer,
) -> dict[str, list[str]]:
    manifest = manifest_loader.load(manifest_path)

    return await indexer.index_manifest(manifest)


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: IndexSettings | None = None,
) -> dict[str, list[str]]:
    resolved_settings = settings or IndexSettings()
    qdrant_client = create_qdrant_client(resolved_settings)

    try:
        indexer = build_indexer(
            settings=resolved_settings,
            args=args,
            qdrant_client=qdrant_client,
        )

        result = await run_indexing(
            manifest_path=args.manifest,
            manifest_loader=(GuidelineManifestLoader()),
            indexer=indexer,
        )

        for document_id, point_ids in result.items():
            print(f"{document_id}: {len(point_ids)}개 청크")

        return result
    finally:
        await qdrant_client.close()


def parse_args(
    argv: list[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("manifest 기반 공공 가이드라인 PDF 일괄 인덱싱"))

    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="공공 가이드라인 manifest JSON 경로",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="청크 최대 문자 수",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="청크 간 중복 문자 수",
    )

    args = parser.parse_args(argv)

    if args.chunk_size <= 0:
        parser.error("--chunk-size는 0보다 커야 합니다.")

    if args.chunk_overlap < 0:
        parser.error("--chunk-overlap은 0 이상이어야 합니다.")

    if args.chunk_overlap >= args.chunk_size:
        parser.error("--chunk-overlap은 --chunk-size보다 작아야 합니다.")

    return args


def main() -> None:
    args = parse_args()

    asyncio.run(run_cli(args=args))


if __name__ == "__main__":
    main()
