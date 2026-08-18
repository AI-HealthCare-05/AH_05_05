from ai_worker.scripts import run_core_demo
from ai_worker.scripts.run_core_demo import (
    DemoSettings,
)


def test_create_qdrant_client_uses_qdrant_url(
    monkeypatch,
) -> None:
    received_values: dict[str, str] = {}

    def fake_async_qdrant_client(
        *,
        url: str,
    ) -> object:
        received_values["url"] = url
        return object()

    monkeypatch.setattr(
        run_core_demo,
        "AsyncQdrantClient",
        fake_async_qdrant_client,
    )

    settings = DemoSettings(
        OPENAI_API_KEY="test-api-key",
        QDRANT_URL="http://qdrant:6333",
        _env_file=None,
    )

    create_client = getattr(
        run_core_demo,
        "create_qdrant_client",
        None,
    )

    assert create_client is not None

    client = create_client(settings)

    assert received_values["url"] == (
        "http://qdrant:6333"
    )
    assert client is not None
