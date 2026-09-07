from dataclasses import dataclass
from typing import Any

from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


@dataclass(frozen=True)
class _Region:
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class _TableSpec:
    title: str
    headers: tuple[str, ...]
    x_boundaries: tuple[float, ...]
    row_starts: tuple[float, ...]
    bottom: float


class BotanicalReviewLayoutParser:
    """검수된 좌표로 식물성 보충제 체계적 문헌고찰의 표와 본문을 분리합니다."""

    _SOURCE_ID = "research_supplement_adverse_effects"
    _WORD_X_TOLERANCE = 1
    _WORD_Y_TOLERANCE = 3
    _LINE_TOP_TOLERANCE = 3.0

    _TEXT_REGIONS = {
        # Table 1은 식물명 목록일 뿐 이상반응 근거가 아니므로 제외한다.
        3: (
            _Region(41.0, 380.0, 290.0, 750.0),
            _Region(305.0, 380.0, 555.0, 750.0),
        ),
        # 왼쪽 하단 문장이 먼저 끝난 뒤 오른쪽 단으로 이어진다.
        4: (
            _Region(41.0, 550.0, 290.0, 750.0),
            _Region(305.0, 50.0, 555.0, 550.0),
            _Region(305.0, 550.0, 555.0, 750.0),
        ),
        5: (
            _Region(41.0, 570.0, 290.0, 750.0),
            _Region(305.0, 570.0, 555.0, 750.0),
        ),
        6: (
            _Region(41.0, 555.0, 290.0, 750.0),
            _Region(305.0, 555.0, 555.0, 750.0),
        ),
        7: (
            _Region(41.0, 490.0, 290.0, 750.0),
            _Region(305.0, 490.0, 555.0, 750.0),
        ),
    }

    _TABLE_SPECS = {
        4: (
            _TableSpec(
                title="Causality categories according to the World Health Organization",
                headers=("Causality classification", "Details"),
                x_boundaries=(41.0, 137.0, 283.0),
                row_starts=(122.0, 223.5, 307.8, 372.4, 429.1, 475.2),
                bottom=510.0,
            ),
        ),
        5: (
            _TableSpec(
                title=(
                    "Number of scientific papers describing adverse effects of "
                    "botanicals/plant food supplements, including misidentification "
                    "and interaction with nutrient or conventional drugs"
                ),
                headers=(
                    "Plant by scientific name (common name)",
                    "Number of references due to adverse effects as such",
                    "Number of references due to misidentification",
                    "Number of references due to interactions",
                    "Total references",
                ),
                x_boundaries=(41.0, 245.0, 320.0, 420.0, 495.0, 553.0),
                row_starts=(
                    150.4,
                    159.7,
                    170.1,
                    179.4,
                    189.8,
                    199.1,
                    209.5,
                    218.8,
                    229.3,
                    238.5,
                    249.0,
                    258.2,
                    268.7,
                    277.9,
                    288.4,
                    297.6,
                    308.1,
                    317.3,
                    327.8,
                    337.0,
                    347.5,
                    356.7,
                    367.2,
                    376.4,
                    386.9,
                    396.1,
                    406.6,
                    415.8,
                    426.3,
                    435.6,
                    446.0,
                    455.3,
                    465.7,
                    475.0,
                    485.4,
                    494.7,
                    505.1,
                    514.4,
                    524.8,
                    534.1,
                ),
                bottom=546.0,
            ),
        ),
        6: (
            _TableSpec(
                title=(
                    "Number of papers describing specific adverse effects to the "
                    "botanicals considered and their ranking by causality"
                ),
                headers=(
                    "Plant by scientific name (common name)",
                    "Total number of papers describing side-effects",
                    "Papers reporting certain/probable association",
                    "Papers reporting possible association",
                    "Papers showing unlikely/unassessable association",
                ),
                x_boundaries=(41.0, 245.0, 315.0, 385.0, 465.0, 553.0),
                row_starts=(
                    140.4,
                    149.7,
                    160.2,
                    169.4,
                    179.9,
                    189.1,
                    199.6,
                    208.8,
                    219.3,
                    228.5,
                    239.0,
                    248.2,
                    258.7,
                    267.9,
                    278.4,
                ),
                bottom=291.0,
            ),
            _TableSpec(
                title=(
                    "Number of papers reporting interactions between the botanicals "
                    "considered and nutrients, food or conventional drugs with "
                    "ranking by causality"
                ),
                headers=(
                    "Plant by scientific name (common name)",
                    "Total number of papers describing interactions",
                    "Papers reporting certain/probable association",
                    "Papers reporting possible association",
                    "Papers showing unlikely/unassessable association",
                ),
                x_boundaries=(41.0, 245.0, 315.0, 385.0, 465.0, 553.0),
                row_starts=(
                    406.9,
                    416.1,
                    426.6,
                    435.8,
                    446.3,
                    455.5,
                    466.0,
                    475.2,
                    485.7,
                    494.9,
                    505.4,
                    514.6,
                ),
                bottom=527.0,
            ),
        ),
        7: (
            _TableSpec(
                title="Form used by consumers experiencing adverse effects",
                headers=(
                    "Plant by scientific name (common name)",
                    "Botanical part used (when specified)",
                    "Food and beverages (functional, flavoured etc.)",
                    "Plant food supplement (type)",
                    "Others",
                ),
                x_boundaries=(41.0, 180.0, 250.0, 345.0, 455.0, 553.0),
                row_starts=(
                    131.2,
                    149.7,
                    169.4,
                    187.8,
                    207.6,
                    226.0,
                    245.7,
                    282.6,
                    311.6,
                    339.3,
                    368.2,
                    395.9,
                    415.6,
                    434.1,
                ),
                bottom=463.0,
            ),
        ),
    }

    def parse(
        self,
        *,
        page: Any,
        page_number: int,
        source_id: str,
        document_id: str | None = None,
    ) -> PdfLayoutExtraction | None:
        if source_id != self._SOURCE_ID or page_number not in self._TEXT_REGIONS:
            return None

        words = self._normalized_words(
            page.extract_words(
                return_chars=True,
                x_tolerance=self._WORD_X_TOLERANCE,
                y_tolerance=self._WORD_Y_TOLERANCE,
            )
            or []
        )
        blocks: list[KnowledgePageBlock] = []
        for region in self._TEXT_REGIONS[page_number]:
            block = self._text_block(words, region)
            if block is not None:
                blocks.append(block)
        for spec in self._TABLE_SPECS.get(page_number, ()):
            blocks.append(self._table_block(words, spec))

        blocks = [block.model_copy(update={"order": index}) for index, block in enumerate(blocks)]
        return PdfLayoutExtraction(
            blocks=blocks,
            warnings=[KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT],
        )

    def _text_block(
        self,
        words: list[tuple[int, dict[str, Any]]],
        region: _Region,
    ) -> KnowledgePageBlock | None:
        content = self._region_text(words, region)
        if not content:
            return None
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(**region.__dict__),
            content=content,
        )

    def _table_block(
        self,
        words: list[tuple[int, dict[str, Any]]],
        spec: _TableSpec,
    ) -> KnowledgePageBlock:
        row_boundaries = [*spec.row_starts, spec.bottom]
        rows: list[KnowledgeTableRow] = []
        for row_index, row_top in enumerate(spec.row_starts):
            row_bottom = row_boundaries[row_index + 1]
            cells = [
                self._region_text(
                    words,
                    _Region(
                        spec.x_boundaries[column_index],
                        row_top,
                        spec.x_boundaries[column_index + 1],
                        row_bottom,
                    ),
                    join_lines=True,
                )
                for column_index in range(len(spec.headers))
            ]
            rows.append(KnowledgeTableRow(cells=cells))

        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(spec.headers, row.cells, strict=True) if cell)
            for row in rows
            if any(row.cells)
        )
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(
                x0=spec.x_boundaries[0],
                top=spec.row_starts[0],
                x1=spec.x_boundaries[-1],
                bottom=spec.bottom,
            ),
            content=content,
            headers=list(spec.headers),
            rows=rows,
            column_count=len(spec.headers),
            table_title=spec.title,
            validation_errors=[],
        )

    def _region_text(
        self,
        words: list[tuple[int, dict[str, Any]]],
        region: _Region,
        *,
        join_lines: bool = False,
    ) -> str:
        selected = [
            word
            for _, word in words
            if region.x0 <= (word["x0"] + word["x1"]) / 2 < region.x1
            and region.top <= (word["top"] + word["bottom"]) / 2 < region.bottom
        ]
        lines: list[list[dict[str, Any]]] = []
        for word in sorted(selected, key=lambda item: (item["top"], item["x0"])):
            if not lines or abs(lines[-1][0]["top"] - word["top"]) > self._LINE_TOP_TOLERANCE:
                lines.append([word])
            else:
                lines[-1].append(word)
        rendered = [" ".join(item["text"] for item in sorted(line, key=lambda item: item["x0"])) for line in lines]
        separator = " " if join_lines else "\n"
        return separator.join(rendered).strip()

    @staticmethod
    def _normalized_words(
        raw_words: list[dict[str, Any]],
    ) -> list[tuple[int, dict[str, Any]]]:
        return [
            (
                index,
                {
                    "text": str(word.get("text", "")).strip(),
                    "x0": float(word["x0"]),
                    "top": float(word["top"]),
                    "x1": float(word["x1"]),
                    "bottom": float(word["bottom"]),
                },
            )
            for index, word in enumerate(raw_words)
            if str(word.get("text", "")).strip()
        ]
