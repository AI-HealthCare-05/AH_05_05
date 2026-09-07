from pathlib import Path

from ai_worker.rag.loaders.knowledge_document_loader_router import (
    KnowledgeDocumentLoaderRouter,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeMetadata,
    KnowledgePage,
)


class Loader:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def load(self, file_path: Path, metadata: KnowledgeMetadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=self.marker,
                metadata=metadata,
                page_number=1,
            )
        ]


def _metadata() -> KnowledgeMetadata:
    return KnowledgeMetadata(
        source_id="source",
        document_id="document",
        title="제목",
        provider="제공자",
        access_scope=KnowledgeAccessScope.PUBLIC,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="dataset",
    )


def test_routes_only_artifact_backed_document_to_ocr_loader(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "document.json").write_text("{}", encoding="utf-8")
    router = KnowledgeDocumentLoaderRouter(
        pdf_loader=Loader("PDF"),
        ocr_loader=Loader("OCR"),
        ocr_artifact_root=artifact_root,
        ocr_document_ids={"document"},
    )

    pages = router.load(tmp_path / "document.pdf", _metadata())

    assert pages[0].content == "OCR"


def test_routes_document_without_artifact_to_pdf_loader(tmp_path: Path) -> None:
    router = KnowledgeDocumentLoaderRouter(
        pdf_loader=Loader("PDF"),
        ocr_loader=Loader("OCR"),
        ocr_artifact_root=tmp_path / "artifacts",
    )

    pages = router.load(tmp_path / "document.pdf", _metadata())

    assert pages[0].content == "PDF"


def test_routes_non_allowlisted_document_to_pdf_loader_even_when_artifact_exists(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "document.json").write_text("{}", encoding="utf-8")
    router = KnowledgeDocumentLoaderRouter(
        pdf_loader=Loader("PDF"),
        ocr_loader=Loader("OCR"),
        ocr_artifact_root=artifact_root,
        ocr_document_ids={"selected-ocr-document"},
    )

    pages = router.load(tmp_path / "document.pdf", _metadata())

    assert pages[0].content == "PDF"
