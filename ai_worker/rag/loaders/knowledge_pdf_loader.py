import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader

from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtractor
from ai_worker.rag.loaders.verified_knowledge_layout_parser import (
    VerifiedKnowledgeLayoutParser,
)
from ai_worker.schemas.knowledge import (
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgePageBlock,
    KnowledgeTableRow,
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
        verified_layout_parser: Any | None = None,
    ) -> None:
        self._layout_extractor = layout_extractor or PdfLayoutExtractor()
        self._layout_document_opener = layout_document_opener or pdfplumber.open
        self._verified_layout_parser = verified_layout_parser or VerifiedKnowledgeLayoutParser()

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
        return self._merge_continued_table_rows(pages)

    @classmethod
    def _merge_continued_table_rows(
        cls,
        pages: list[KnowledgePage],
    ) -> list[KnowledgePage]:
        """이전 페이지 표의 마지막 열로만 이어진 행을 원래 행에 복원합니다."""
        merged = list(pages)
        for page_index in range(1, len(merged)):
            previous = merged[page_index - 1]
            current = merged[page_index]
            previous_table_index = cls._last_table_index(previous.blocks)
            current_table_index = cls._first_table_index(current.blocks)
            if previous_table_index is None or current_table_index is None:
                continue

            previous_table = previous.blocks[previous_table_index]
            current_table = current.blocks[current_table_index]
            if not cls._is_same_continued_table(previous_table, current_table):
                continue
            if not previous_table.rows or not current_table.rows:
                continue

            continuation = current_table.rows[0]
            populated = [index for index, cell in enumerate(continuation.cells) if cell]
            last_column = len(current_table.headers) - 1
            if populated != [last_column]:
                continue

            previous_rows = list(previous_table.rows)
            previous_last = previous_rows[-1]
            if not any(previous_last.cells[:-1]):
                continue
            previous_cells = list(previous_last.cells)
            previous_cells[-1] = " ".join(filter(None, [previous_cells[-1].rstrip(), continuation.cells[-1].lstrip()]))
            previous_rows[-1] = previous_last.model_copy(update={"cells": previous_cells})
            current_rows = list(current_table.rows[1:])

            previous_blocks = list(previous.blocks)
            previous_blocks[previous_table_index] = cls._table_with_rows(
                previous_table,
                previous_rows,
            )
            current_blocks = list(current.blocks)
            if current_rows:
                current_blocks[current_table_index] = cls._table_with_rows(
                    current_table,
                    current_rows,
                )
            else:
                current_blocks.pop(current_table_index)

            merged[page_index - 1] = cls._page_with_blocks(previous, previous_blocks)
            merged[page_index] = cls._page_with_blocks(current, current_blocks)
        return merged

    @staticmethod
    def _first_table_index(blocks: list[KnowledgePageBlock]) -> int | None:
        return next(
            (index for index, block in enumerate(blocks) if block.kind == KnowledgeContentKind.TABLE),
            None,
        )

    @staticmethod
    def _last_table_index(blocks: list[KnowledgePageBlock]) -> int | None:
        return next(
            (index for index in range(len(blocks) - 1, -1, -1) if blocks[index].kind == KnowledgeContentKind.TABLE),
            None,
        )

    @staticmethod
    def _is_same_continued_table(
        previous: KnowledgePageBlock,
        current: KnowledgePageBlock,
    ) -> bool:
        return (
            previous.table_title is not None
            and previous.table_title == current.table_title
            and previous.headers == current.headers
            and previous.column_count == current.column_count
        )

    @staticmethod
    def _table_with_rows(
        block: KnowledgePageBlock,
        rows: list[KnowledgeTableRow],
    ) -> KnowledgePageBlock:
        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(block.headers, row.cells, strict=True) if cell)
            for row in rows
            if any(row.cells)
        )
        return block.model_copy(update={"rows": rows, "content": content})

    @staticmethod
    def _page_with_blocks(
        page: KnowledgePage,
        blocks: list[KnowledgePageBlock],
    ) -> KnowledgePage:
        ordered = [block.model_copy(update={"order": index}) for index, block in enumerate(blocks)]
        content = "\n\n".join(block.content for block in ordered if block.content).strip()
        return page.model_copy(update={"blocks": ordered, "content": content})

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
                    document_id=metadata.document_id,
                )
                used_verified_extraction = verified_extraction is not None
                if used_verified_extraction:
                    extraction = verified_extraction
                repair_extraction = getattr(
                    self._verified_layout_parser,
                    "repair",
                    None,
                )
                if callable(repair_extraction):
                    extraction = repair_extraction(
                        extraction=extraction,
                        page_number=page_number,
                        source_id=metadata.source_id,
                    )
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
            if used_verified_extraction and not extraction.blocks:
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

            warnings = (
                []
                if used_verified_extraction
                else [
                    warning
                    for warning in self._extraction_warnings(page, metadata)
                    if warning == KnowledgeExtractionWarning.ROTATED_TEXT
                ]
            )
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
