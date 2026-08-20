import asyncio
import logging
import os
import socket

from pydantic import (
    Field,
    SecretStr,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from ai_worker.core.logger import setup_logger
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
from ai_worker.services.public_guideline_index_service import (
    ManifestIndexerFactory,
    PublicGuidelineIndexService,
)
from ai_worker.tasks.public_guideline_index_task import (
    PublicGuidelineIndexTask,
)
from ai_worker.workers.public_guideline_index_worker import (
    PublicGuidelineIndexWorker,
)


def build_default_consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class PublicGuidelineWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: SecretStr
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = Field(
        default=1536,
        gt=0,
    )

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "public_guidelines_small_v1"
    QDRANT_TIMEOUT_SECONDS: int = Field(
        default=30,
        gt=0,
    )

    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_STREAM_NAME: str = "public-guideline-index-jobs"
    REDIS_CONSUMER_GROUP: str = "public-guideline-index-workers"
    REDIS_CONSUMER_NAME: str = Field(default_factory=(build_default_consumer_name))
    REDIS_READ_COUNT: int = Field(
        default=1,
        gt=0,
    )
    REDIS_BLOCK_MS: int = Field(
        default=5000,
        ge=0,
    )
    REDIS_CONNECT_TIMEOUT_SECONDS: int = Field(
        default=5,
        gt=0,
    )


def create_redis_client(
    settings: PublicGuidelineWorkerSettings,
) -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=(settings.REDIS_CONNECT_TIMEOUT_SECONDS),
        socket_timeout=None,
        health_check_interval=30,
    )


def create_qdrant_client(
    settings: PublicGuidelineWorkerSettings,
) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def build_indexer_factory(
    *,
    settings: PublicGuidelineWorkerSettings,
    qdrant_client: AsyncQdrantClient,
) -> ManifestIndexerFactory:
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

    def create_indexer(
        chunk_size: int,
        chunk_overlap: int,
    ) -> GuidelineIndexer:
        return GuidelineIndexer(
            loader=PdfLoader(),
            splitter=GuidelineSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            ),
            embedding_provider=(embedding_provider),
            vector_store=vector_store,
        )

    return create_indexer


def build_worker(
    *,
    settings: PublicGuidelineWorkerSettings,
    redis_client: object,
    qdrant_client: object,
    logger: logging.Logger,
) -> PublicGuidelineIndexWorker:
    indexer_factory = build_indexer_factory(
        settings=settings,
        qdrant_client=qdrant_client,
    )

    service = PublicGuidelineIndexService(
        manifest_loader=(GuidelineManifestLoader()),
        indexer_factory=indexer_factory,
    )

    task = PublicGuidelineIndexTask(service=service)

    return PublicGuidelineIndexWorker(
        redis_client=redis_client,
        task=task,
        stream_name=(settings.REDIS_STREAM_NAME),
        consumer_group=(settings.REDIS_CONSUMER_GROUP),
        consumer_name=(settings.REDIS_CONSUMER_NAME),
        read_count=settings.REDIS_READ_COUNT,
        block_ms=settings.REDIS_BLOCK_MS,
        logger=logger,
    )


async def run_worker(
    settings: (PublicGuidelineWorkerSettings | None) = None,
) -> None:
    resolved_settings = settings or PublicGuidelineWorkerSettings()

    logger = setup_logger(name="public-guideline-index-worker")

    redis_client = create_redis_client(resolved_settings)
    qdrant_client = create_qdrant_client(resolved_settings)

    try:
        worker = build_worker(
            settings=resolved_settings,
            redis_client=redis_client,
            qdrant_client=qdrant_client,
            logger=logger,
        )

        logger.info(
            "공공 가이드라인 인덱싱 Worker를 시작합니다: stream=%s, group=%s, consumer=%s",
            resolved_settings.REDIS_STREAM_NAME,
            resolved_settings.REDIS_CONSUMER_GROUP,
            resolved_settings.REDIS_CONSUMER_NAME,
        )

        await worker.run_forever()
    finally:
        await redis_client.aclose()
        await qdrant_client.close()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
