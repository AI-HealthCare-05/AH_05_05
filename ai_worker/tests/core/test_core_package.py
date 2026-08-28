from ai_worker.core import (
    Config,
    setup_logger,
)


def test_core_package_uses_ai_worker_dependencies() -> None:
    assert Config.__module__ == ("ai_worker.core.config")
    assert setup_logger.__module__ == ("ai_worker.core.logger")


def test_config_defaults_to_approved_full_knowledge_release() -> None:
    settings = Config(_env_file=None)

    assert settings.KNOWLEDGE_QDRANT_COLLECTION == ("medication_knowledge_full_v1")
    assert settings.KNOWLEDGE_DATASET_VERSION == ("knowledge-full-v1")


def test_config_limits_openai_and_qdrant_calls_to_ten_seconds() -> None:
    settings = Config(_env_file=None)

    assert settings.OPENAI_TIMEOUT_SECONDS == 10.0
    assert settings.QDRANT_TIMEOUT_SECONDS == 10.0


def test_config_reads_openai_chat_integration_settings(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "OPENAI_CHAT_MODEL",
        "gpt-4o",
    )
    monkeypatch.setenv(
        "RUN_OPENAI_INTEGRATION_TESTS",
        "1",
    )
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "1536")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "public-guidelines-test")
    monkeypatch.setenv(
        "KNOWLEDGE_QDRANT_COLLECTION",
        "medication-knowledge-test",
    )
    monkeypatch.setenv(
        "KNOWLEDGE_DATASET_VERSION",
        "knowledge-test-v1",
    )
    monkeypatch.setenv("RAG_MIN_SIMILARITY_SCORE", "0.7")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "4")

    settings = Config(
        _env_file=None,
    )

    assert settings.OPENAI_API_KEY is not None
    assert settings.OPENAI_API_KEY.get_secret_value() == "test-api-key"
    assert settings.OPENAI_CHAT_MODEL == "gpt-4o"
    assert settings.RUN_OPENAI_INTEGRATION_TESTS is True
    assert settings.OPENAI_EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.OPENAI_EMBEDDING_DIMENSIONS == 1536
    assert settings.QDRANT_URL == "http://qdrant:6333"
    assert settings.QDRANT_COLLECTION == "public-guidelines-test"
    assert settings.KNOWLEDGE_QDRANT_COLLECTION == "medication-knowledge-test"
    assert settings.KNOWLEDGE_DATASET_VERSION == "knowledge-test-v1"
    assert settings.RAG_MIN_SIMILARITY_SCORE == 0.7
    assert settings.OPENAI_TIMEOUT_SECONDS == 20
    assert settings.OPENAI_MAX_RETRIES == 4


def test_config_disables_langsmith_content_capture_by_default() -> None:
    settings = Config(_env_file=None)

    assert settings.LANGSMITH_TRACING is False
    assert settings.LANGSMITH_CAPTURE_CONTENT is False
    assert settings.RUN_LANGSMITH_INTEGRATION_TESTS is False


def test_config_reads_langsmith_settings(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "ai-health-test")
    monkeypatch.setenv("LANGSMITH_ENVIRONMENT", "test")
    monkeypatch.setenv("LANGSMITH_CAPTURE_CONTENT", "true")
    monkeypatch.setenv(
        "LANGSMITH_HASH_SALT",
        "test-observability-salt",
    )

    settings = Config(_env_file=None)

    assert settings.LANGSMITH_TRACING is True
    assert settings.LANGSMITH_API_KEY is not None
    assert settings.LANGSMITH_API_KEY.get_secret_value() == ("test-langsmith-key")
    assert settings.LANGSMITH_PROJECT == "ai-health-test"
    assert settings.LANGSMITH_ENVIRONMENT == "test"
    assert settings.LANGSMITH_CAPTURE_CONTENT is True
    assert settings.LANGSMITH_HASH_SALT is not None
    assert settings.LANGSMITH_HASH_SALT.get_secret_value() == ("test-observability-salt")
