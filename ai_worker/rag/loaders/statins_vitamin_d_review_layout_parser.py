import re
from dataclasses import dataclass
from typing import Any

from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


@dataclass(frozen=True)
class _Region:
    x0: float
    top: float
    x1: float
    bottom: float


class StatinsVitaminDReviewLayoutParser:
    """검수된 MDPI statin-vitamin D review의 본문 영역만 복원합니다."""

    _SOURCE_ID = "research_drug_nutrient_interactions"
    _DOCUMENT_ID = "research_drug_nutrient_interactions-186668a2a92b533c"
    _LINE_TOP_TOLERANCE = 4.0

    def parse(
        self,
        *,
        page: Any,
        page_number: int,
        source_id: str,
        document_id: str | None = None,
    ) -> PdfLayoutExtraction | None:
        if source_id != self._SOURCE_ID or document_id != self._DOCUMENT_ID:
            return None
        if page_number >= 14:
            return PdfLayoutExtraction(blocks=[], warnings=[])

        words = self._words(page)
        if page_number == 7:
            return self._page_seven(words)
        if page_number == 8:
            return self._page_eight(words)
        blocks = [
            block for region in self._regions(page_number) if (block := self._text_block(words, region)) is not None
        ]
        return PdfLayoutExtraction(
            blocks=[block.model_copy(update={"order": index}) for index, block in enumerate(blocks)],
            warnings=[],
        )

    @staticmethod
    def _regions(page_number: int) -> tuple[_Region, ...]:
        if page_number == 1:
            return (
                _Region(30.0, 90.0, 565.0, 160.0),
                _Region(150.0, 310.0, 565.0, 650.0),
                _Region(150.0, 650.0, 565.0, 800.0),
            )
        if page_number == 5:
            # Figure 1과 캡션은 제외하고 이어지는 본문부터 읽는다.
            return (_Region(150.0, 525.0, 565.0, 800.0),)
        return (_Region(150.0, 55.0, 565.0, 800.0),)

    def _page_seven(
        self,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        blocks = [
            block
            for region in (
                _Region(150.0, 55.0, 565.0, 195.0),
                _Region(150.0, 545.0, 565.0, 800.0),
            )
            if (block := self._text_block(words, region)) is not None
        ]
        table = self._table_block(
            words=words,
            title="Overlap of Statins and Vitamin D Mechanisms",
            headers=(
                "Mechanism/Pathway",
                "Statin Mechanism",
                "Vitamin D Mechanism",
                "Representative Evidence (Study Type/Population)",
            ),
            bounds=(40.0, 165.0, 295.0, 425.0, 560.0),
            row_ranges=(
                (239.0, 276.0),
                (276.0, 305.0),
                (305.0, 341.0),
                (341.0, 371.0),
                (371.0, 399.0),
                (399.0, 439.0),
                (439.0, 478.0),
                (478.0, 525.0),
            ),
            region=_Region(40.0, 215.0, 560.0, 525.0),
        )
        if table is not None:
            blocks.insert(1, table)
        return PdfLayoutExtraction(blocks=self._ordered(blocks), warnings=[])

    def _page_eight(
        self,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        blocks = [
            block
            for region in (
                _Region(150.0, 55.0, 565.0, 445.0),
                _Region(150.0, 725.0, 565.0, 800.0),
            )
            if (block := self._text_block(words, region)) is not None
        ]
        table = self._table_block(
            words=words,
            title="Effects of Statins on Vitamin D Levels",
            headers=(
                "Statin(s) Studied",
                "Study Design",
                "Effect on Vitamin D Levels",
                "Remarks/Limitations",
            ),
            bounds=(40.0, 165.0, 295.0, 455.0, 560.0),
            row_ranges=(
                (486.0, 508.0),
                (508.0, 539.0),
                (539.0, 572.0),
                (572.0, 594.0),
                (594.0, 626.0),
                (626.0, 649.0),
                (649.0, 671.0),
                (671.0, 692.0),
                (692.0, 715.0),
            ),
            region=_Region(40.0, 465.0, 560.0, 715.0),
        )
        if table is not None:
            blocks.insert(1, table)
        return PdfLayoutExtraction(blocks=self._ordered(blocks), warnings=[])

    def _table_block(
        self,
        *,
        words: list[dict[str, Any]],
        title: str,
        headers: tuple[str, ...],
        bounds: tuple[float, ...],
        row_ranges: tuple[tuple[float, float], ...],
        region: _Region,
    ) -> KnowledgePageBlock | None:
        rows = [
            KnowledgeTableRow(
                cells=[
                    self._table_cell(words, bounds[index], bounds[index + 1], top, bottom)
                    for index in range(len(headers))
                ]
            )
            for top, bottom in row_ranges
        ]
        rows = [row for row in rows if sum(bool(cell) for cell in row.cells) >= 3]
        if not rows:
            return None
        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(headers, row.cells, strict=True) if cell)
            for row in rows
        )
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(**region.__dict__),
            content=content,
            headers=list(headers),
            rows=rows,
            column_count=len(headers),
            table_title=title,
            validation_errors=[],
        )

    def _table_cell(
        self,
        words: list[dict[str, Any]],
        x0: float,
        x1: float,
        top: float,
        bottom: float,
    ) -> str:
        selected = [
            word
            for word in words
            if word["upright"] and x0 <= self._center_x(word) < x1 and top <= self._center_y(word) < bottom
        ]
        lines = [self._render_line(line) for line in self._lines(selected)]
        return self._clean_table_cell(" ".join(lines))

    @staticmethod
    def _clean_table_cell(content: str) -> str:
        content = re.sub(r"(?<=[A-Za-z])[-‐]\s+(?=[a-z])", "", content)
        content = re.sub(r"(?<=[A-Za-z])[-‐]\s+(?=[α-ωΑ-Ω])", "-", content)
        content = re.sub(r"\(\s*citation\s+(\[[^]]+\])\s*\)", r"\1", content, flags=re.IGNORECASE)
        content = re.sub(r"\.\s+(?=\[\s*\d)", " ", content)
        content = re.sub(r"\s+([,;:.])", r"\1", content)
        content = re.sub(r"\s+", " ", content)
        return content.strip()

    def _text_block(
        self,
        words: list[dict[str, Any]],
        region: _Region,
    ) -> KnowledgePageBlock | None:
        selected = [word for word in words if word["upright"] and self._inside(word, region)]
        lines = [self._render_line(line) for line in self._lines(selected)]
        content = self._clean_content("\n".join(line for line in lines if line))
        if not content:
            return None
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(**region.__dict__),
            content=content,
        )

    def _lines(self, words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        lines: list[list[dict[str, Any]]] = []
        for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
            if not lines or abs(float(lines[-1][0]["top"]) - float(word["top"])) > self._LINE_TOP_TOLERANCE:
                lines.append([word])
            else:
                lines[-1].append(word)
        return lines

    @staticmethod
    def _render_line(words: list[dict[str, Any]]) -> str:
        return " ".join(str(word["text"]) for word in sorted(words, key=lambda item: item["x0"]))

    @staticmethod
    def _clean_content(content: str) -> str:
        content = re.sub(r"(?<=[A-Za-z])[-‐]\n(?=[a-z])", "", content)
        content = re.sub(r"[ \t]+", " ", content)
        content = re.sub(r" *\n *", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    @staticmethod
    def _inside(word: dict[str, Any], region: _Region) -> bool:
        x = (float(word["x0"]) + float(word["x1"])) / 2
        y = (float(word["top"]) + float(word["bottom"])) / 2
        return region.x0 <= x < region.x1 and region.top <= y < region.bottom

    @staticmethod
    def _center_x(word: dict[str, Any]) -> float:
        return (float(word["x0"]) + float(word["x1"])) / 2

    @staticmethod
    def _center_y(word: dict[str, Any]) -> float:
        return (float(word["top"]) + float(word["bottom"])) / 2

    @staticmethod
    def _ordered(blocks: list[KnowledgePageBlock]) -> list[KnowledgePageBlock]:
        return [block.model_copy(update={"order": index}) for index, block in enumerate(blocks)]

    @staticmethod
    def _words(page: Any) -> list[dict[str, Any]]:
        raw_words = (
            page.extract_words(
                return_chars=True,
                x_tolerance=1,
                y_tolerance=3,
                extra_attrs=["upright", "fontname", "size"],
            )
            or []
        )
        return [
            {
                "text": str(word.get("text", "")).strip(),
                "x0": float(word["x0"]),
                "top": float(word["top"]),
                "x1": float(word["x1"]),
                "bottom": float(word["bottom"]),
                "upright": bool(word.get("upright", True)),
            }
            for word in raw_words
            if str(word.get("text", "")).strip()
        ]
