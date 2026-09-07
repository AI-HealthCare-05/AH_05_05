from pathlib import Path
from typing import Protocol

from ai_worker.schemas.knowledge import KnowledgeMetadata, KnowledgePage
from ai_worker.schemas.knowledge_ocr import knowledge_ocr_artifact_path


class KnowledgeDocumentLoader(Protocol):
    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]: ...


class KnowledgeDocumentLoaderRouter:
    """artifact가 준비된 OCR 문서만 OCR loader로 보내고 나머지는 기존 PDF loader를 사용합니다."""

    def __init__(
        self,
        *,
        pdf_loader: KnowledgeDocumentLoader,
        ocr_loader: KnowledgeDocumentLoader,
        ocr_artifact_root: Path,
    ) -> None:
        self._pdf_loader = pdf_loader
        self._ocr_loader = ocr_loader
        self._ocr_artifact_root = Path(ocr_artifact_root)

    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        artifact_path = knowledge_ocr_artifact_path(
            artifact_root=self._ocr_artifact_root,
            document_id=metadata.document_id,
        )
        loader = self._ocr_loader if artifact_path.is_file() else self._pdf_loader
        return loader.load(file_path, metadata)
