import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from ai_worker.rag.loaders.botanical_review_layout_parser import (
    BotanicalReviewLayoutParser,
)
from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtractor
from ai_worker.schemas.knowledge import (
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
)


class KnowledgePdfLoader:
    _COORDINATE_DOCUMENT_TYPES = {
        KnowledgeDocumentType.RESEARCH_ARTICLE,
        KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
    }

    def __init__(
        self,
        *,
        layout_extractor: PdfLayoutExtractor | None = None,
        layout_document_opener: Callable[[Path], Any] | None = None,
        verified_layout_parser: BotanicalReviewLayoutParser | None = None,
    ) -> None:
        self._layout_extractor = layout_extractor or PdfLayoutExtractor()
        self._layout_document_opener = layout_document_opener or pdfplumber.open
        self._verified_layout_parser = verified_layout_parser or BotanicalReviewLayoutParser()

    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            raise ValueError("PDF 파일만 불러올 수 있습니다.")

        reader = PdfReader(path)
        pages = self._load_pages(path, reader, metadata)
        if not pages:
            raise ValueError("PDF에서 추출 가능한 텍스트를 찾지 못했습니다.")
        return pages

    def _load_pages(
        self,
        path: Path,
        reader: PdfReader,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        if metadata.document_type not in self._COORDINATE_DOCUMENT_TYPES:
            return self._load_legacy_pages(reader, metadata)

        try:
            with self._layout_document_opener(path) as layout_document:
                return self._load_coordinate_pages(
                    reader,
                    layout_document,
                    metadata,
                )
        except Exception:
            return self._load_legacy_pages(
                reader,
                metadata,
                extra_warnings=[
                    KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
                ],
            )

    def _load_coordinate_pages(  # noqa: C901
        self,
        reader: PdfReader,
        layout_document: Any,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        if len(layout_document.pages) != len(reader.pages):
            raise ValueError("PDF 페이지 수가 추출 엔진 사이에서 다릅니다.")

        pages: list[KnowledgePage] = []
        previous_table_headers: list[str] | None = None
        previous_table_title: str | None = None
        previous_table_column_count: int | None = None
        previous_page_had_table = False
        for page_number, (page, layout_page) in enumerate(
            zip(reader.pages, layout_document.pages, strict=True),
            start=1,
        ):
            try:
                extraction = self._layout_extractor.extract(layout_page)
                verified_extraction = self._verified_layout_parser.parse(
                    page=layout_page,
                    page_number=page_number,
                    source_id=metadata.source_id,
                )
                if verified_extraction is not None:
                    extraction = verified_extraction
                inherit_headers = getattr(
                    self._layout_extractor,
                    "inherit_continued_table_headers",
                    None,
                )
                if callable(inherit_headers):
                    extraction = inherit_headers(
                        extraction,
                        previous_table_headers,
                    )
            except Exception:
                content = self._extract_text(page, metadata).strip()
                if not content:
                    continue
                warnings = self._extraction_warnings(page, metadata)
                warnings.append(KnowledgeExtractionWarning.READING_ORDER_UNSAFE)
                pages.append(
                    KnowledgePage(
                        content=content,
                        metadata=metadata,
                        page_number=page_number,
                        extraction_warnings=list(dict.fromkeys(warnings)),
                    )
                )
                continue
            blocks = sorted(
                extraction.blocks,
                key=lambda block: block.order,
            )
            if previous_page_had_table and previous_table_title:
                blocks = [
                    (
                        block.model_copy(update={"table_title": previous_table_title})
                        if block.kind == KnowledgeContentKind.TABLE
                        and block.table_title is None
                        and block.column_count == previous_table_column_count
                        else block
                    )
                    for block in blocks
                ]
            complete_table_headers = [
                block.headers
                for block in blocks
                if block.kind == KnowledgeContentKind.TABLE
                and block.headers
                and not any(header.startswith("열 ") for header in block.headers)
            ]
            if complete_table_headers:
                previous_table_headers = complete_table_headers[-1]
            table_blocks = [block for block in blocks if block.kind == KnowledgeContentKind.TABLE]
            if table_blocks:
                previous_page_had_table = True
                previous_table_title = table_blocks[-1].table_title
                previous_table_column_count = table_blocks[-1].column_count
            else:
                previous_page_had_table = False
                previous_table_title = None
                previous_table_column_count = None
            content = "\n\n".join(block.content.strip() for block in blocks if block.content.strip()).strip()
            if not content:
                content = self._extract_text(page, metadata).strip()
            if not content:
                continue

            warnings = [
                warning
                for warning in self._extraction_warnings(page, metadata)
                if warning == KnowledgeExtractionWarning.ROTATED_TEXT
            ]
            warnings.extend(extraction.warnings)
            pages.append(
                KnowledgePage(
                    content=content,
                    metadata=metadata,
                    page_number=page_number,
                    blocks=blocks,
                    extraction_warnings=list(dict.fromkeys(warnings)),
                )
            )
        return pages

    def _load_legacy_pages(
        self,
        reader: PdfReader,
        metadata: KnowledgeMetadata,
        *,
        extra_warnings: list[KnowledgeExtractionWarning] | None = None,
    ) -> list[KnowledgePage]:
        pages: list[KnowledgePage] = []
        for page_number, page in enumerate(reader.pages, start=1):
            content = self._extract_text(page, metadata).strip()
            if not content:
                continue
            warnings = self._extraction_warnings(page, metadata)
            warnings.extend(extra_warnings or [])
            pages.append(
                KnowledgePage(
                    content=content,
                    metadata=metadata,
                    page_number=page_number,
                    extraction_warnings=list(dict.fromkeys(warnings)),
                )
            )
        return pages

    @staticmethod
    def _extract_text(page, metadata: KnowledgeMetadata) -> str:
        if metadata.document_type == KnowledgeDocumentType.PHARM_REVIEW:
            return page.extract_text(extraction_mode="layout") or ""
        return page.extract_text() or ""

    @staticmethod
    def _extraction_warnings(
        page,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgeExtractionWarning]:
        if metadata.document_type not in {
            KnowledgeDocumentType.RESEARCH_ARTICLE,
            KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        }:
            return []

        rotated_text = (
            page.extract_text(
                orientations=(90, 180, 270),
            )
            or ""
        )
        if rotated_text.strip():
            return [KnowledgeExtractionWarning.ROTATED_TEXT]

        layout_text = page.extract_text(extraction_mode="layout") or ""
        separated_rows = sum(bool(re.search(r"\S {12,}\S", line)) for line in layout_text.splitlines())
        if separated_rows >= 2:
            return [KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT]
        return []
