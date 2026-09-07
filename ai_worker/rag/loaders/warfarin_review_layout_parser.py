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


class WarfarinReviewLayoutParser:
    """검수된 Wiley 지면 규칙으로 warfarin 체계적 문헌고찰을 복원합니다."""

    _SOURCE_ID = "research_drug_nutrient_interactions"
    _DOCUMENT_ID = "research_drug_nutrient_interactions-299edbe35f581616"
    _LINE_TOP_TOLERANCE = 3.0
    _REGISTRATION_PATTERN = re.compile(
        r"\s*(?:The review was registered with\s+)?PROSPERO\s*"
        r"\(Registration No:\s*CRD42020169696\)\.?",
        flags=re.IGNORECASE,
    )
    _SPACED_HEADINGS = {
        "K E Y W O R D S": "KEYWORDS",
        "M E T H O D S": "METHODS",
        "R E S U L T S": "RESULTS",
        "O U T C O M E S": "OUTCOMES",
        "D I S C U S S I O N": "DISCUSSION",
        "C O N C L U S I O N": "CONCLUSION",
    }
    _NUMBERED_SPACED_HEADING_PATTERN = re.compile(
        r"(?m)^(?P<prefix>\d+(?:\.\d+)?\s*\|\s*)"
        r"(?P<title>[A-Z][A-Z ]*[A-Z])$",
    )
    _CAPTION_SPACED_HEADING_PATTERN = re.compile(
        r"(?m)^(?P<title>(?:T\s*A\s*B\s*L\s*E|F\s*I\s*G\s*U\s*R\s*E))"
        r"(?P<suffix>\s+\d+.*)$",
    )
    _TABLE_2_HEADERS = (
        "Food, herbal or dietary supplement (common name and Latin name)",
        "Clinical result of interaction reported",
        "Severity of interaction",
        "Source of evidence",
        "Comment",
    )
    _TABLE_2_COLUMN_BOUNDS = (45.0, 160.0, 273.0, 323.0, 436.0, 555.0)

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

        words = self._words(page)
        page_parser = {
            1: self._front_page,
            2: self._methods_page,
            3: self._results_page,
            4: self._outcomes_and_table_one,
            16: self._table_three_page,
            17: self._table_three_and_discussion,
            18: self._discussion_and_conclusion,
            19: self._conclusion_tail,
        }.get(page_number)
        if page_parser is not None:
            return page_parser(page, words)
        if 5 <= page_number <= 15:
            return self._table_two_pages(page, words, page_number)
        return PdfLayoutExtraction(blocks=[], warnings=[])

    def _front_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        regions = (
            _Region(40.0, 95.0, width - 40.0, 160.0),
            _Region(205.0, 215.0, width - 40.0, 510.0),
            _Region(205.0, 510.0, width - 40.0, 552.0),
            _Region(40.0, 565.0, 295.0, 742.0),
            _Region(300.0, 565.0, width - 40.0, 742.0),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered(self._text_blocks(words, regions)),
            warnings=[],
        )

    def _methods_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        regions = (
            _Region(40.0, 45.0, 295.0, 742.0),
            _Region(300.0, 45.0, width - 40.0, 742.0),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered(self._text_blocks(words, regions)),
            warnings=[],
        )

    def _results_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        """3쪽 본문을 좌→우로 복원하고 하단 Figure 1 캡션은 제외합니다."""
        width = float(page.width)
        regions = (
            _Region(40.0, 42.0, 295.0, 715.0),
            _Region(300.0, 42.0, width - 40.0, 715.0),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered(self._text_blocks(words, regions)),
            warnings=[],
        )

    def _outcomes_and_table_one(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        body = self._text_blocks(
            words,
            (
                _Region(40.0, 42.0, 300.0, 120.0),
                _Region(300.0, 42.0, width - 40.0, 120.0),
            ),
        )
        row_ranges = (
            ("Highly probable", 174.0, 229.0),
            ("Probable", 229.0, 296.0),
            ("Possible", 296.0, 446.0),
            ("Doubtful", 446.0, 735.0),
        )
        rows = [
            KnowledgeTableRow(
                cells=[
                    label,
                    self._table_cell(words, 105.0, 230.0, top, bottom),
                    self._table_cell(words, 230.0, 390.0, top, bottom),
                    self._table_cell(words, 390.0, 555.0, top, bottom),
                ]
            )
            for label, top, bottom in row_ranges
        ]
        table = self._table_block(
            title=("Herbal and dietary supplement interaction with warfarin by causality and direction"),
            headers=(
                "Probability scale",
                "Potentiation",
                "Inhibition",
                "No effect",
            ),
            rows=rows,
            region=_Region(45.0, 132.0, width - 40.0, 735.0),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered([*body, table]),
            warnings=[],
        )

    def _table_two_pages(
        self,
        page: Any,
        words: list[dict[str, Any]],
        page_number: int,
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        blocks: list[KnowledgePageBlock] = []
        if page_number == 5:
            blocks.extend(
                self._text_blocks(
                    words,
                    (
                        _Region(40.0, 42.0, 300.0, 130.0),
                        _Region(300.0, 42.0, width - 40.0, 130.0),
                    ),
                )
            )

        table_top = 195.0 if page_number == 5 else 96.0
        table_bottom = 620.0 if page_number == 15 else 735.0
        rows = self._column_table_rows(
            words,
            top=table_top,
            bottom=table_bottom,
            bounds=self._TABLE_2_COLUMN_BOUNDS,
        )
        if rows:
            blocks.append(
                self._table_block(
                    title=("Reported clinical interactions between herbal/dietary supplement and warfarin (Table 2)"),
                    headers=self._TABLE_2_HEADERS,
                    rows=rows,
                    region=_Region(45.0, table_top, width - 40.0, table_bottom),
                )
            )
        if page_number == 15:
            blocks.extend(
                self._text_blocks(
                    words,
                    (
                        _Region(40.0, 665.0, 300.0, 742.0),
                        _Region(300.0, 665.0, width - 40.0, 742.0),
                    ),
                )
            )
        return PdfLayoutExtraction(
            blocks=self._ordered(blocks),
            warnings=[],
        )

    def _table_three_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
        page_number: int = 16,
    ) -> PdfLayoutExtraction:
        top = 90.0
        bottom = 735.0 if page_number == 16 else 255.0
        rows = self._column_table_rows(
            words,
            top=top,
            bottom=bottom,
            bounds=(45.0, 150.0, 555.0),
        )
        if not rows:
            return PdfLayoutExtraction(blocks=[], warnings=[])
        table = self._table_block(
            title=(
                "Herbs, food and dietary supplements associated with bleeding "
                "events in patients taking warfarin (Table 3)"
            ),
            headers=("Herb, food or dietary supplement", "Brief description of event"),
            rows=rows,
            region=_Region(45.0, top, float(page.width) - 40.0, bottom),
        )
        return PdfLayoutExtraction(blocks=[table], warnings=[])

    def _table_three_and_discussion(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        table_extraction = self._table_three_page(page, words, 17)
        discussion = self._text_blocks(
            words,
            (
                _Region(40.0, 290.0, 300.0, 450.0),
                _Region(300.0, 290.0, width - 40.0, 410.0),
                _Region(300.0, 410.0, width - 40.0, 450.0),
            ),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered([*table_extraction.blocks, *discussion]),
            warnings=[],
        )

    def _discussion_and_conclusion(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        regions = (
            _Region(40.0, 42.0, 300.0, 742.0),
            _Region(300.0, 42.0, width - 40.0, 590.0),
            _Region(300.0, 600.0, width - 40.0, 742.0),
        )
        return PdfLayoutExtraction(
            blocks=self._ordered(self._text_blocks(words, regions)),
            warnings=[],
        )

    def _conclusion_tail(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        blocks = self._text_blocks(
            words,
            (_Region(40.0, 42.0, 300.0, 125.0),),
        )
        return PdfLayoutExtraction(blocks=self._ordered(blocks), warnings=[])

    def _column_table_rows(
        self,
        words: list[dict[str, Any]],
        *,
        top: float,
        bottom: float,
        bounds: tuple[float, ...],
    ) -> list[KnowledgeTableRow]:
        selected = [item for item in words if item["upright"] and top <= self._center_y(item) < bottom]
        lines = self._lines(selected)
        row_tops: list[float] = []
        for line in lines:
            first = [item for item in line if bounds[0] <= self._center_x(item) < bounds[1]]
            second = [item for item in line if bounds[1] <= self._center_x(item) < bounds[2]]
            if first and second and not self._is_italic(first[0]):
                row_tops.append(min(float(item["top"]) for item in line))
        row_tops = list(dict.fromkeys(row_tops))
        ranges: list[tuple[float, float]] = []
        if row_tops and top < row_tops[0] - 2:
            ranges.append((top, row_tops[0]))
        ranges.extend(
            (row_top, row_tops[index + 1] if index + 1 < len(row_tops) else bottom)
            for index, row_top in enumerate(row_tops)
        )
        rows: list[KnowledgeTableRow] = []
        for row_top, row_bottom in ranges:
            cells = [
                self._table_cell(
                    selected,
                    bounds[index],
                    bounds[index + 1],
                    row_top,
                    row_bottom,
                )
                for index in range(len(bounds) - 1)
            ]
            if any(cells):
                rows.append(KnowledgeTableRow(cells=cells))
        return rows

    def _table_cell(
        self,
        words: list[dict[str, Any]],
        x0: float,
        x1: float,
        top: float,
        bottom: float,
    ) -> str:
        selected = [
            item
            for item in words
            if item["upright"] and x0 <= self._center_x(item) < x1 and top <= self._center_y(item) < bottom
        ]
        lines = [self._render_line(line) for line in self._lines(selected)]
        return self._clean_content(" ".join(lines))

    def _table_block(
        self,
        *,
        title: str,
        headers: tuple[str, ...],
        rows: list[KnowledgeTableRow],
        region: _Region,
    ) -> KnowledgePageBlock:
        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(headers, row.cells, strict=True) if cell)
            for row in rows
            if any(row.cells)
        )
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(**region.__dict__),
            content=content or "No indexable rows",
            headers=list(headers),
            rows=rows,
            column_count=len(headers),
            table_title=title,
            validation_errors=[],
        )

    def _text_blocks(
        self,
        words: list[dict[str, Any]],
        regions: tuple[_Region, ...],
    ) -> list[KnowledgePageBlock]:
        blocks: list[KnowledgePageBlock] = []
        for region in regions:
            selected = [item for item in words if item["upright"] and self._inside(item, region)]
            lines = [self._render_line(line) for line in self._lines(selected)]
            content = self._clean_content("\n".join(lines))
            if not content:
                continue
            blocks.append(
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TEXT,
                    order=0,
                    bbox=KnowledgeBoundingBox(**region.__dict__),
                    content=content,
                )
            )
        return blocks

    def _clean_blocks(
        self,
        blocks: list[KnowledgePageBlock],
    ) -> list[KnowledgePageBlock]:
        cleaned: list[KnowledgePageBlock] = []
        for block in blocks:
            content = self._clean_content(block.content)
            if not content:
                continue
            cleaned.append(block.model_copy(update={"content": content}))
        return cleaned

    def _clean_content(self, content: str) -> str:
        content = self._REGISTRATION_PATTERN.sub("", content)
        content = content.replace("(cid:129)", "•")
        for source, replacement in self._SPACED_HEADINGS.items():
            content = content.replace(source, replacement)
        content = self._NUMBERED_SPACED_HEADING_PATTERN.sub(
            lambda match: (f"{match.group('prefix')}{re.sub(r'\s+', '', match.group('title'))}"),
            content,
        )
        content = self._CAPTION_SPACED_HEADING_PATTERN.sub(
            lambda match: (f"{re.sub(r'\s+', '', match.group('title'))}{match.group('suffix')}"),
            content,
        )
        content = re.sub(r"(?m)^TAN\s+AND\s+LEE(?:\s+\d+)?$", "", content)
        content = re.sub(
            r"(?im)^Br\s+J\s+Clin\s+Pharmacol\.\s*2021;87:352[–-]374\.?$",
            "",
            content,
        )
        content = re.sub(
            r"(?im)^wileyonlinelibrary\.com/journal/bcp$",
            "",
            content,
        )
        content = re.sub(r"[ \t]+", " ", content)
        content = re.sub(r" *\n *", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip()

    @staticmethod
    def _center_x(word: dict[str, Any]) -> float:
        return (float(word["x0"]) + float(word["x1"])) / 2

    @staticmethod
    def _center_y(word: dict[str, Any]) -> float:
        return (float(word["top"]) + float(word["bottom"])) / 2

    @staticmethod
    def _is_italic(word: dict[str, Any]) -> bool:
        return str(word.get("fontname", "")).endswith(".I")

    @staticmethod
    def _content_only_page(page: Any) -> Any:
        page_filter = getattr(page, "filter", None)
        if not callable(page_filter):
            return page

        def keep(item: dict[str, Any]) -> bool:
            x0 = float(item.get("x0", 0.0))
            x1 = float(item.get("x1", x0))
            top = float(item.get("top", 0.0))
            bottom = float(item.get("bottom", top))
            return bool(item.get("upright", True)) and (x0 + x1) / 2 < 560.0 and 42.0 <= (top + bottom) / 2 < 742.0

        return page_filter(keep)

    def _lines(
        self,
        words: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        lines: list[list[dict[str, Any]]] = []
        for item in sorted(words, key=lambda word: (word["top"], word["x0"])):
            if not lines or abs(float(lines[-1][0]["top"]) - float(item["top"])) > self._LINE_TOP_TOLERANCE:
                lines.append([item])
            else:
                lines[-1].append(item)
        return lines

    @staticmethod
    def _render_line(words: list[dict[str, Any]]) -> str:
        return " ".join(str(item["text"]) for item in sorted(words, key=lambda word: word["x0"])).strip()

    @staticmethod
    def _inside(word: dict[str, Any], region: _Region) -> bool:
        x = (float(word["x0"]) + float(word["x1"])) / 2
        y = (float(word["top"]) + float(word["bottom"])) / 2
        return region.x0 <= x < region.x1 and region.top <= y < region.bottom

    @staticmethod
    def _ordered(
        blocks: list[KnowledgePageBlock],
    ) -> list[KnowledgePageBlock]:
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
                "size": float(word.get("size", 8.0)),
                "fontname": str(word.get("fontname", "")),
            }
            for word in raw_words
            if str(word.get("text", "")).strip() and float(word.get("size", 8.0)) >= 7.0
        ]
