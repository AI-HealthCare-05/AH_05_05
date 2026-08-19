from importlib import import_module
from pathlib import Path

import pytest

from ai_worker.schemas.guideline_manifest import (
    GuidelineManifest,
    GuidelineManifestDocument,
)


def test_parse_args_accepts_manifest_and_chunk_settings() -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")

    args = module.parse_args(
        [
            "--manifest",
            "data/public_guidelines/manifest.json",
            "--chunk-size",
            "800",
            "--chunk-overlap",
            "100",
        ]
    )

    assert args.manifest == Path("data/public_guidelines/manifest.json")
    assert args.chunk_size == 800
    assert args.chunk_overlap == 100


@pytest.mark.parametrize(
    (
        "chunk_size",
        "chunk_overlap",
    ),
    [
        (0, 0),
        (100, -1),
        (100, 100),
    ],
)
def test_parse_args_rejects_invalid_chunk_settings(
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")

    with pytest.raises(SystemExit):
        module.parse_args(
            [
                "--manifest",
                "manifest.json",
                "--chunk-size",
                str(chunk_size),
                "--chunk-overlap",
                str(chunk_overlap),
            ]
        )


def test_index_settings_reads_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")

    monkeypatch.setenv(
        "OPENAI_API_KEY",
        "test-api-key",
    )
    monkeypatch.setenv(
        "OPENAI_EMBEDDING_MODEL",
        "text-embedding-3-small",
    )
    monkeypatch.setenv(
        "OPENAI_EMBEDDING_DIMENSIONS",
        "1536",
    )
    monkeypatch.setenv(
        "QDRANT_URL",
        "http://localhost:6333",
    )
    monkeypatch.setenv(
        "QDRANT_COLLECTION",
        "public-guidelines-test",
    )

    settings = module.IndexSettings(_env_file=None)

    assert settings.OPENAI_API_KEY.get_secret_value() == "test-api-key"
    assert settings.OPENAI_EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.OPENAI_EMBEDDING_DIMENSIONS == 1536
    assert settings.QDRANT_URL == "http://localhost:6333"
    assert settings.QDRANT_COLLECTION == "public-guidelines-test"


async def test_run_indexing_loads_manifest_and_indexes_documents() -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")

    manifest = GuidelineManifest(
        documents=[
            GuidelineManifestDocument(
                file_path=Path("stroke-guideline.pdf"),
                document_id="stroke-2020",
                title="Stroke Guideline",
                condition="STROKE",
            )
        ]
    )

    class FakeManifestLoader:
        def __init__(self) -> None:
            self.received_path: Path | None = None

        def load(
            self,
            manifest_path: Path,
        ) -> GuidelineManifest:
            self.received_path = manifest_path
            return manifest

    class FakeManifestIndexer:
        def __init__(self) -> None:
            self.received_manifest: GuidelineManifest | None = None

        async def index_manifest(
            self,
            received_manifest: (GuidelineManifest),
        ) -> dict[str, list[str]]:
            self.received_manifest = received_manifest
            return {
                "stroke-2020": [
                    "point-1",
                    "point-2",
                ]
            }

    manifest_loader = FakeManifestLoader()
    indexer = FakeManifestIndexer()
    manifest_path = Path("data/public_guidelines/manifest.json")

    result = await module.run_indexing(
        manifest_path=manifest_path,
        manifest_loader=manifest_loader,
        indexer=indexer,
    )

    assert manifest_loader.received_path == manifest_path
    assert indexer.received_manifest == manifest
    assert result == {
        "stroke-2020": [
            "point-1",
            "point-2",
        ]
    }


def test_create_qdrant_client_uses_configured_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")
    received: dict[str, str] = {}

    class FakeQdrantClient:
        def __init__(
            self,
            *,
            url: str,
        ) -> None:
            received["url"] = url

    monkeypatch.setattr(
        module,
        "AsyncQdrantClient",
        FakeQdrantClient,
        raising=False,
    )

    settings = module.IndexSettings(
        OPENAI_API_KEY="test-api-key",
        QDRANT_URL=("http://qdrant-test:6333"),
        _env_file=None,
    )

    client = module.create_qdrant_client(settings)

    assert isinstance(
        client,
        FakeQdrantClient,
    )
    assert received["url"] == ("http://qdrant-test:6333")


def test_build_indexer_connects_configured_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")
    received: dict[str, object] = {}

    class FakeEmbeddingProvider:
        def __init__(
            self,
            *,
            model: str,
            dimensions: int,
            api_key: object,
        ) -> None:
            received["embedding_model"] = model
            received["dimensions"] = dimensions
            received["api_key"] = api_key

    class FakeVectorStore:
        def __init__(
            self,
            *,
            client: object,
            collection_name: str,
            vector_size: int,
        ) -> None:
            received["client"] = client
            received["collection_name"] = collection_name
            received["vector_size"] = vector_size

    class FakeSplitter:
        def __init__(
            self,
            *,
            chunk_size: int,
            chunk_overlap: int,
        ) -> None:
            received["chunk_size"] = chunk_size
            received["chunk_overlap"] = chunk_overlap

    class FakePdfLoader:
        pass

    class FakeGuidelineIndexer:
        def __init__(
            self,
            *,
            loader: object,
            splitter: object,
            embedding_provider: object,
            vector_store: object,
        ) -> None:
            received["loader"] = loader
            received["splitter"] = splitter
            received["embedding_provider"] = embedding_provider
            received["vector_store"] = vector_store

    monkeypatch.setattr(
        module,
        "OpenAIEmbeddingProvider",
        FakeEmbeddingProvider,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "QdrantGuidelineStore",
        FakeVectorStore,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "GuidelineSplitter",
        FakeSplitter,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "PdfLoader",
        FakePdfLoader,
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "GuidelineIndexer",
        FakeGuidelineIndexer,
    )

    settings = module.IndexSettings(
        OPENAI_API_KEY="test-api-key",
        OPENAI_EMBEDDING_MODEL=("text-embedding-test"),
        OPENAI_EMBEDDING_DIMENSIONS=3,
        QDRANT_COLLECTION=("public-guidelines-test"),
        _env_file=None,
    )
    args = module.parse_args(
        [
            "--manifest",
            "manifest.json",
            "--chunk-size",
            "800",
            "--chunk-overlap",
            "100",
        ]
    )
    qdrant_client = object()

    indexer = module.build_indexer(
        settings=settings,
        args=args,
        qdrant_client=qdrant_client,
    )

    assert isinstance(
        indexer,
        FakeGuidelineIndexer,
    )
    assert received["embedding_model"] == ("text-embedding-test")
    assert received["dimensions"] == 3
    assert received["client"] is qdrant_client
    assert received["collection_name"] == ("public-guidelines-test")
    assert received["vector_size"] == 3
    assert received["chunk_size"] == 800
    assert received["chunk_overlap"] == 100
    assert isinstance(
        received["loader"],
        FakePdfLoader,
    )


async def test_run_cli_indexes_manifest_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")
    received: dict[str, object] = {}

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeQdrantClient()
    fake_loader = object()
    fake_indexer = object()

    def fake_create_qdrant_client(
        settings: object,
    ) -> FakeQdrantClient:
        received["settings"] = settings
        return fake_client

    def fake_build_indexer(
        *,
        settings: object,
        args: object,
        qdrant_client: object,
    ) -> object:
        received["build_settings"] = settings
        received["args"] = args
        received["client"] = qdrant_client
        return fake_indexer

    async def fake_run_indexing(
        *,
        manifest_path: Path,
        manifest_loader: object,
        indexer: object,
    ) -> dict[str, list[str]]:
        received["manifest_path"] = manifest_path
        received["manifest_loader"] = manifest_loader
        received["indexer"] = indexer

        return {
            "stroke-2020": [
                "point-1",
                "point-2",
            ]
        }

    monkeypatch.setattr(
        module,
        "create_qdrant_client",
        fake_create_qdrant_client,
    )
    monkeypatch.setattr(
        module,
        "build_indexer",
        fake_build_indexer,
    )
    monkeypatch.setattr(
        module,
        "run_indexing",
        fake_run_indexing,
    )
    monkeypatch.setattr(
        module,
        "GuidelineManifestLoader",
        lambda: fake_loader,
    )

    settings = module.IndexSettings(
        OPENAI_API_KEY="test-api-key",
        _env_file=None,
    )
    args = module.parse_args(
        [
            "--manifest",
            "data/public_guidelines/manifest.json",
        ]
    )

    result = await module.run_cli(
        args=args,
        settings=settings,
    )

    assert result == {
        "stroke-2020": [
            "point-1",
            "point-2",
        ]
    }
    assert received["manifest_path"] == Path("data/public_guidelines/manifest.json")
    assert received["manifest_loader"] is fake_loader
    assert received["indexer"] is fake_indexer
    assert received["client"] is fake_client
    assert fake_client.closed is True

    output = capsys.readouterr().out
    assert "stroke-2020" in output
    assert "2개 청크" in output


async def test_run_cli_closes_client_when_indexing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("ai_worker.scripts.index_public_guidelines")

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    fake_client = FakeQdrantClient()

    async def failing_run_indexing(
        **_: object,
    ) -> dict[str, list[str]]:
        raise RuntimeError("인덱싱 실패")

    monkeypatch.setattr(
        module,
        "create_qdrant_client",
        lambda settings: fake_client,
    )
    monkeypatch.setattr(
        module,
        "build_indexer",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        module,
        "run_indexing",
        failing_run_indexing,
    )

    settings = module.IndexSettings(
        OPENAI_API_KEY="test-api-key",
        _env_file=None,
    )
    args = module.parse_args(
        [
            "--manifest",
            "manifest.json",
        ]
    )

    with pytest.raises(
        RuntimeError,
        match="인덱싱 실패",
    ):
        await module.run_cli(
            args=args,
            settings=settings,
        )

    assert fake_client.closed is True
