from pathlib import Path

from ai_worker.rag.loaders import knowledge_pdf_loader
from ai_worker.rag.loaders.knowledge_pdf_loader import KnowledgePdfLoader
from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePageBlock,
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


class FakeMultiColumnPage:
    def extract_text(
        self,
        *,
        extraction_mode=None,
        orientations=(0, 90, 180, 270),
        **kwargs,
    ) -> str:
        if orientations == (90, 180, 270):
            return ""
        if extraction_mode == "layout":
            return (
                "Left column text                         Right column text\n"
                "Left continuation                        Right continuation\n"
                "Left result                              Right result"
            )
        return "Left column text\nLeft continuation\nRight column text\nRight continuation"


class FakeMultiColumnReader:
    metadata = {}

    def __init__(self, _: Path) -> None:
        self.pages = [FakeMultiColumnPage()]


def test_load_marks_research_multi_column_layout_for_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeMultiColumnReader,
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-1",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader().load(pdf_path, metadata)

    assert pages[0].content.startswith("Left column text")
    assert KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT in (pages[0].extraction_warnings)
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in (pages[0].extraction_warnings)


class FakeRotatedTextPage:
    def extract_text(
        self,
        *,
        extraction_mode=None,
        orientations=(0, 90, 180, 270),
        **kwargs,
    ) -> str:
        if orientations == (90, 180, 270):
            return "Rotated table heading"
        if extraction_mode == "layout":
            return "Single column research text"
        return "Single column research text\nRotated table heading"


class FakeRotatedTextReader:
    def __init__(self, _: Path) -> None:
        self.pages = [FakeRotatedTextPage()]


def test_load_marks_rotated_research_text_for_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeRotatedTextReader,
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-rotated",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader().load(pdf_path, metadata)

    assert KnowledgeExtractionWarning.ROTATED_TEXT in (pages[0].extraction_warnings)
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in (pages[0].extraction_warnings)


class FakeCoordinatePage:
    pass


class FakeBrokenCoordinatePage:
    pass


class FakeLayoutDocument:
    def __init__(self) -> None:
        self.pages = [FakeCoordinatePage()]
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.closed = True


class FakeTwoPageLayoutDocument(FakeLayoutDocument):
    def __init__(self) -> None:
        super().__init__()
        self.pages = [FakeCoordinatePage(), FakeBrokenCoordinatePage()]


class FakeCoordinateExtractor:
    def extract(self, page) -> PdfLayoutExtraction:
        if isinstance(page, FakeBrokenCoordinatePage):
            raise RuntimeError("page layout failure")
        assert isinstance(page, FakeCoordinatePage)
        return PdfLayoutExtraction(
            blocks=[
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TEXT,
                    order=0,
                    bbox=KnowledgeBoundingBox(
                        x0=10,
                        top=10,
                        x1=300,
                        bottom=30,
                    ),
                    content="좌표 본문",
                ),
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TABLE,
                    order=1,
                    bbox=KnowledgeBoundingBox(
                        x0=10,
                        top=40,
                        x1=300,
                        bottom=100,
                    ),
                    content="성분=철분 | 결과=감소",
                    headers=["성분", "결과"],
                    rows=[{"cells": ["철분", "감소"]}],
                    column_count=2,
                ),
            ],
            warnings=[],
        )


class FakeContinuedTableExtractor:
    def extract(self, page) -> PdfLayoutExtraction:
        is_first = not isinstance(page, FakeBrokenCoordinatePage)
        return PdfLayoutExtraction(
            blocks=[
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TABLE,
                    order=0,
                    bbox=KnowledgeBoundingBox(
                        x0=10,
                        top=40,
                        x1=300,
                        bottom=100,
                    ),
                    content=(
                        "Drug=Calcium | Effect=Reduced absorption"
                        if is_first
                        else "Drug=Iron | Effect=Reduced absorption"
                    ),
                    headers=["Drug", "Effect"],
                    rows=[
                        {
                            "cells": [
                                "Calcium" if is_first else "Iron",
                                "Reduced absorption",
                            ]
                        }
                    ],
                    column_count=2,
                    table_title=("Shared interaction table" if is_first else None),
                )
            ],
            warnings=[],
        )


class FakeTwoPageReader:
    def __init__(self, _: Path) -> None:
        self.pages = [FakeMultiColumnPage(), FakeMultiColumnPage()]


def test_load_uses_coordinate_blocks_for_research_document(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeMultiColumnReader,
    )
    layout_document = FakeLayoutDocument()
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-coordinate",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader(
        layout_extractor=FakeCoordinateExtractor(),
        layout_document_opener=lambda _: layout_document,
    ).load(pdf_path, metadata)

    assert pages[0].content == ("좌표 본문\n\n성분=철분 | 결과=감소")
    assert [block.kind for block in pages[0].blocks] == [
        KnowledgeContentKind.TEXT,
        KnowledgeContentKind.TABLE,
    ]
    assert layout_document.closed is True


def test_load_marks_layout_unsafe_when_coordinate_extraction_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeMultiColumnReader,
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-fallback",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader(
        layout_document_opener=lambda _: (_ for _ in ()).throw(RuntimeError("layout failure")),
    ).load(pdf_path, metadata)

    assert pages[0].content.startswith("Left column text")
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in (pages[0].extraction_warnings)


def test_load_falls_back_only_the_page_with_coordinate_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeTwoPageReader,
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-page-fallback",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader(
        layout_extractor=FakeCoordinateExtractor(),
        layout_document_opener=lambda _: FakeTwoPageLayoutDocument(),
    ).load(pdf_path, metadata)

    assert pages[0].blocks
    assert pages[1].blocks == []
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in (pages[1].extraction_warnings)


def test_load_inherits_title_for_consecutive_continued_table_pages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "research.pdf"
    pdf_path.write_bytes(b"%PDF-test")
    monkeypatch.setattr(
        knowledge_pdf_loader,
        "PdfReader",
        FakeTwoPageReader,
    )
    metadata = KnowledgeMetadata(
        source_id="research",
        document_id="research-table",
        title="Interaction review",
        provider="Journal",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="pilot-v1",
    )

    pages = KnowledgePdfLoader(
        layout_extractor=FakeContinuedTableExtractor(),
        layout_document_opener=lambda _: FakeTwoPageLayoutDocument(),
    ).load(pdf_path, metadata)

    table_titles = [
        block.table_title for page in pages for block in page.blocks if block.kind == KnowledgeContentKind.TABLE
    ]
    assert table_titles == [
        "Shared interaction table",
        "Shared interaction table",
    ]
