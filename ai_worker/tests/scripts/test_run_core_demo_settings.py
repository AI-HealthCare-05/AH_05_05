from ai_worker.scripts.run_core_demo import (
    DemoSettings,
)


def test_demo_settings_reads_rag_similarity_threshold(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "RAG_MIN_SIMILARITY_SCORE",
        "0.72",
    )

    settings = DemoSettings(
        _env_file=None
    )

    assert (
        settings.RAG_MIN_SIMILARITY_SCORE
        == 0.72
    )


def test_demo_settings_reads_qdrant_url(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "QDRANT_URL",
        "http://qdrant:6333",
    )

    settings = DemoSettings(
        _env_file=None
    )

    assert (
        settings.QDRANT_URL
        == "http://qdrant:6333"
    )
