import logging

import pytest

from ai_worker import main as worker_main
from ai_worker.workers.public_guideline_index_worker import (
    PublicGuidelineIndexWorker,
)


def build_settings() -> worker_main.PublicGuidelineWorkerSettings:
    return worker_main.PublicGuidelineWorkerSettings(
        OPENAI_API_KEY="test-api-key",
        REDIS_URL="redis://localhost:6379/0",
        QDRANT_URL="http://localhost:6333",
        REDIS_CONSUMER_NAME="test-worker",
        _env_file=None,
    )


def test_settings_read_worker_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "REDIS_URL",
        "redis://redis:6379/0",
    )
    monkeypatch.setenv(
        "QDRANT_URL",
        "http://qdrant:6333",
    )
    monkeypatch.setenv(
        "REDIS_STREAM_NAME",
        "public-index-jobs",
    )
    monkeypatch.setenv(
        "REDIS_CONSUMER_GROUP",
        "public-index-workers",
    )
    monkeypatch.setenv(
        "REDIS_CONSUMER_NAME",
        "worker-1",
    )
    monkeypatch.setenv("REDIS_CLAIM_IDLE_MS", "120000")
    monkeypatch.setenv("REDIS_MAX_ATTEMPTS", "5")
    monkeypatch.setenv(
        "REDIS_DEAD_LETTER_STREAM",
        "public-index-jobs-dead",
    )

    settings = worker_main.PublicGuidelineWorkerSettings(_env_file=None)

    assert settings.OPENAI_API_KEY.get_secret_value() == "test-api-key"
    assert settings.REDIS_URL == "redis://redis:6379/0"
    assert settings.QDRANT_URL == "http://qdrant:6333"
    assert settings.REDIS_STREAM_NAME == "public-index-jobs"
    assert settings.REDIS_CONSUMER_GROUP == "public-index-workers"
    assert settings.REDIS_CONSUMER_NAME == "worker-1"
    assert settings.REDIS_CLAIM_IDLE_MS == 120000
    assert settings.REDIS_MAX_ATTEMPTS == 5
    assert settings.REDIS_DEAD_LETTER_STREAM == "public-index-jobs-dead"


def test_build_worker_returns_public_guideline_worker() -> None:
    settings = build_settings()

    worker = worker_main.build_worker(
        settings=settings,
        redis_client=object(),
        qdrant_client=object(),
        logger=logging.getLogger("test-ai-worker"),
    )

    assert isinstance(
        worker,
        PublicGuidelineIndexWorker,
    )


async def test_run_worker_closes_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = build_settings()

    class FakeRedisClient:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class FakeWorker:
        def __init__(self) -> None:
            self.started = False

        async def run_forever(self) -> None:
            self.started = True

    redis_client = FakeRedisClient()
    qdrant_client = FakeQdrantClient()
    worker = FakeWorker()

    monkeypatch.setattr(
        worker_main,
        "create_redis_client",
        lambda received_settings: redis_client,
    )
    monkeypatch.setattr(
        worker_main,
        "create_qdrant_client",
        lambda received_settings: qdrant_client,
    )
    monkeypatch.setattr(
        worker_main,
        "build_worker",
        lambda **kwargs: worker,
    )

    await worker_main.run_worker(settings=settings)

    assert worker.started is True
    assert redis_client.closed is True
    assert qdrant_client.closed is True
