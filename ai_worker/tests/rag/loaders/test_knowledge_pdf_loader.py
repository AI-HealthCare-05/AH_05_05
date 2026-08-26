from pathlib import Path

from ai_worker.rag.loaders import knowledge_pdf_loader
from ai_worker.rag.loaders.knowledge_pdf_loader import KnowledgePdfLoader
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeMetadata,
)


class FakeLayoutPage:
    def __init__(self) -> None:
        self.extraction_modes: list[str | None] = []

    def extract_text(self, *, extraction_mode=None) -> str:
        self.extraction_modes.append(extraction_mode)
        if extraction_mode == "layout":
            return "개요\n공백이 보존된 본문"
        return "개요공백이보존되지않은본문"


class FakeReader:
    page = FakeLayoutPage()

    def __init__(self, _: Path) -> None:
        self.pages = [self.page]


def test_load_prefers_layout_extraction(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "review.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(knowledge_pdf_loader, "PdfReader", FakeReader)
    metadata = KnowledgeMetadata(
        source_id="kpicia_pharm_review",
        document_id="review-1",
        title="과민성대장증후군",
        provider="약학정보원",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.PHARM_REVIEW,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader().load(pdf_path, metadata)

    assert pages[0].content == "개요\n공백이 보존된 본문"
    assert FakeReader.page.extraction_modes[-1] == "layout"


def test_load_uses_plain_extraction_for_structured_supplement_pdf(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "supplement.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(knowledge_pdf_loader, "PdfReader", FakeReader)
    metadata = KnowledgeMetadata(
        source_id="mfds_supplement_code",
        document_id="vitamin-b6",
        title="비타민 B6",
        provider="식품의약품안전처",
        access_scope=KnowledgeAccessScope.PUBLIC,
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader().load(pdf_path, metadata)

    assert pages[0].content == "개요공백이보존되지않은본문"
    assert FakeReader.page.extraction_modes[-1] is None
