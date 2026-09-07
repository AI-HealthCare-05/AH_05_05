from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ai_worker.schemas.knowledge_ocr import (
    KnowledgeOcrBlock,
    KnowledgeOcrDocumentArtifact,
    KnowledgeOcrEngineMetadata,
    KnowledgeOcrPageArtifact,
    KnowledgeOcrRendererMetadata,
    knowledge_ocr_artifact_path,
)
from ai_worker.schemas.knowledge_recovery import KnowledgeOcrManifestEntry


@dataclass(frozen=True)
class KnowledgeOcrRenderedPage:
    image_bytes: bytes
    width: float
    height: float
    rotation_degrees: int


class KnowledgeOcrPageRasterizer(Protocol):
    name: str
    version: str

    def page_count(self, source_path: Path) -> int: ...

    def render_page(
        self,
        source_path: Path,
        page_number: int,
        dpi: int,
    ) -> KnowledgeOcrRenderedPage: ...


class KnowledgeOcrProvider(Protocol):
    name: str
    version: str

    async def recognize(self, image_bytes: bytes) -> list[KnowledgeOcrBlock]: ...


class KnowledgeOcrExtractionService:
    """OCR 실행 결과를 공급자 중립 artifact로 저장하고 재실행을 안전하게 재사용합니다."""

    def __init__(
        self,
        *,
        rasterizer: KnowledgeOcrPageRasterizer,
        provider: KnowledgeOcrProvider,
        dpi: int = 300,
    ) -> None:
        self._rasterizer = rasterizer
        self._provider = provider
        self._dpi = dpi

    async def extract(
        self,
        *,
        entry: KnowledgeOcrManifestEntry,
        source_path: Path,
        artifact_root: Path,
    ) -> KnowledgeOcrDocumentArtifact:
        source = Path(source_path)
        self._validate_source_sha256(entry=entry, source_path=source)
        page_count = self._rasterizer.page_count(source)
        if page_count < 1:
            raise ValueError(f"OCR 대상 PDF 페이지가 없습니다: {entry.document_id}")
        artifact_path = knowledge_ocr_artifact_path(
            artifact_root=artifact_root,
            document_id=entry.document_id,
        )
        existing = self._load_complete_artifact_if_available(
            artifact_path=artifact_path,
            entry=entry,
            page_count=page_count,
        )
        if existing is not None:
            return existing

        pages: list[KnowledgeOcrPageArtifact] = []
        for page_number in range(1, page_count + 1):
            rendered = self._rasterizer.render_page(
                source,
                page_number,
                self._dpi,
            )
            blocks = await self._provider.recognize(rendered.image_bytes)
            if not blocks:
                raise ValueError(f"빈 OCR 응답입니다: {entry.document_id} p.{page_number}")
            pages.append(
                KnowledgeOcrPageArtifact(
                    page_number=page_number,
                    image_sha256=sha256(rendered.image_bytes).hexdigest(),
                    width=rendered.width,
                    height=rendered.height,
                    rotation_degrees=rendered.rotation_degrees,
                    blocks=blocks,
                ),
            )
        artifact = KnowledgeOcrDocumentArtifact(
            schema_version="knowledge-ocr-artifact-v1",
            document_id=entry.document_id,
            source_sha256=entry.source_sha256,
            renderer=KnowledgeOcrRendererMetadata(
                name=self._rasterizer.name,
                version=self._rasterizer.version,
                dpi=self._dpi,
            ),
            ocr_engine=KnowledgeOcrEngineMetadata(
                name=self._provider.name,
                version=self._provider.version,
            ),
            pages=pages,
        )
        self._write_artifact(artifact_path=artifact_path, artifact=artifact)
        return artifact

    @staticmethod
    def _validate_source_sha256(
        *,
        entry: KnowledgeOcrManifestEntry,
        source_path: Path,
    ) -> None:
        if not source_path.is_file():
            raise ValueError(f"OCR 대상 원본 PDF가 없습니다: {entry.document_id}")
        actual = sha256(source_path.read_bytes()).hexdigest()
        if actual != entry.source_sha256:
            raise ValueError(f"OCR 대상 원본 SHA-256이 다릅니다: {entry.document_id}")

    def _load_complete_artifact_if_available(
        self,
        *,
        artifact_path: Path,
        entry: KnowledgeOcrManifestEntry,
        page_count: int,
    ) -> KnowledgeOcrDocumentArtifact | None:
        if not artifact_path.is_file():
            return None
        artifact = KnowledgeOcrDocumentArtifact.model_validate_json(
            artifact_path.read_text(encoding="utf-8"),
        )
        if artifact.document_id != entry.document_id or artifact.source_sha256 != entry.source_sha256:
            return None
        if (
            artifact.renderer.name != self._rasterizer.name
            or artifact.renderer.version != self._rasterizer.version
            or artifact.renderer.dpi != self._dpi
        ):
            return None
        if artifact.ocr_engine.name != self._provider.name or artifact.ocr_engine.version != self._provider.version:
            return None
        if len(artifact.pages) != page_count:
            return None
        return artifact

    @staticmethod
    def _write_artifact(
        *,
        artifact_path: Path,
        artifact: KnowledgeOcrDocumentArtifact,
    ) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = artifact_path.with_suffix(".tmp")
        temporary_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        temporary_path.replace(artifact_path)
