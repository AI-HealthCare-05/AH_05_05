import asyncio
from hashlib import sha256
from pathlib import Path

import pytest

from ai_worker.schemas.knowledge_ocr import KnowledgeOcrBlock, KnowledgeOcrBoundingBox
from ai_worker.schemas.knowledge_recovery import (
    KnowledgeOcrManifestEntry,
    KnowledgeOcrManifestOrigin,
)
from ai_worker.services.knowledge_ocr_extraction_service import (
    KnowledgeOcrExtractionService,
    KnowledgeOcrRenderedPage,
)


class FakeRasterizer:
    name = "fake-rasterizer"
    version = "v1"

    def __init__(self) -> None:
        self.rendered_pages: list[int] = []

    def page_count(self, source_path: Path) -> int:
        assert source_path.name == "ocr.pdf"
        return 2

    def render_page(self, source_path: Path, page_number: int, dpi: int) -> KnowledgeOcrRenderedPage:
        self.rendered_pages.append(page_number)
        return KnowledgeOcrRenderedPage(
            image_bytes=f"page-{page_number}-{dpi}".encode(),
            width=600,
            height=800,
            rotation_degrees=0,
        )


class FakeOcrProvider:
    name = "fake-ocr"
    version = "v1"

    def __init__(self) -> None:
        self.calls = 0

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
        self.calls += 1
        return [
            KnowledgeOcrBlock(
                block_id="line-1",
                text=image_bytes.decode(),
                confidence=0.99,
                bbox=KnowledgeOcrBoundingBox(x0=1, top=1, x1=20, bottom=20),
                line_break=True,
            )
        ]


def test_reuses_complete_artifact_without_calling_external_ocr_again(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "ocr.pdf"
    source_path.write_bytes(b"source pdf")
    source_sha256 = sha256(source_path.read_bytes()).hexdigest()
    entry = KnowledgeOcrManifestEntry(
        document_id="ocr-document",
        source_id="ocr-source",
        repo_path=Path("raw/ocr.pdf"),
        source_sha256=source_sha256,
        origin=KnowledgeOcrManifestOrigin.CATALOG,
    )
    rasterizer = FakeRasterizer()
    provider = FakeOcrProvider()
    service = KnowledgeOcrExtractionService(
        rasterizer=rasterizer,
        provider=provider,
    )
    artifact_root = tmp_path / "artifacts"

    first = asyncio.run(
        service.extract(
            entry=entry,
            source_path=source_path,
            artifact_root=artifact_root,
        )
    )
    second = asyncio.run(
        service.extract(
            entry=entry,
            source_path=source_path,
            artifact_root=artifact_root,
        )
    )

    assert [page.page_number for page in first.pages] == [1, 2]
    assert second == first
    assert rasterizer.rendered_pages == [1, 2]
    assert provider.calls == 2


def test_recreates_artifact_when_ocr_engine_version_changes(
    tmp_path: Path,
) -> None:
    class NewVersionOcrProvider(FakeOcrProvider):
        version = "v2"

    source_path = tmp_path / "ocr.pdf"
    source_path.write_bytes(b"source pdf")
    entry = KnowledgeOcrManifestEntry(
        document_id="ocr-document",
        source_id="ocr-source",
        repo_path=Path("raw/ocr.pdf"),
        source_sha256=sha256(source_path.read_bytes()).hexdigest(),
        origin=KnowledgeOcrManifestOrigin.CATALOG,
    )
    artifact_root = tmp_path / "artifacts"
    first_provider = FakeOcrProvider()
    asyncio.run(
        KnowledgeOcrExtractionService(
            rasterizer=FakeRasterizer(),
            provider=first_provider,
        ).extract(
            entry=entry,
            source_path=source_path,
            artifact_root=artifact_root,
        )
    )
    replacement_provider = NewVersionOcrProvider()

    artifact = asyncio.run(
        KnowledgeOcrExtractionService(
            rasterizer=FakeRasterizer(),
            provider=replacement_provider,
        ).extract(
            entry=entry,
            source_path=source_path,
            artifact_root=artifact_root,
        )
    )

    assert artifact.ocr_engine.version == "v2"
    assert first_provider.calls == 2
    assert replacement_provider.calls == 2


def test_rejects_empty_ocr_response_instead_of_writing_partial_artifact(
    tmp_path: Path,
) -> None:
    class EmptyOcrProvider(FakeOcrProvider):
        async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]:
            return []

    source_path = tmp_path / "ocr.pdf"
    source_path.write_bytes(b"source pdf")
    entry = KnowledgeOcrManifestEntry(
        document_id="ocr-document",
        source_id="ocr-source",
        repo_path=Path("raw/ocr.pdf"),
        source_sha256=sha256(source_path.read_bytes()).hexdigest(),
        origin=KnowledgeOcrManifestOrigin.CATALOG,
    )

    with pytest.raises(ValueError, match="빈 OCR 응답"):
        asyncio.run(
            KnowledgeOcrExtractionService(
                rasterizer=FakeRasterizer(),
                provider=EmptyOcrProvider(),
            ).extract(
                entry=entry,
                source_path=source_path,
                artifact_root=tmp_path / "artifacts",
            )
        )
