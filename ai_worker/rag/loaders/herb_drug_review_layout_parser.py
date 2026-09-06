import re
import unicodedata
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


class HerbDrugReviewLayoutParser:
    """검수된 지면 규칙으로 HDS–약물 상호작용 논문을 복원합니다."""

    _SOURCE_ID = "research_herb_drug_interactions"
    _EXCLUDED_PAGES = frozenset(range(16, 24))
    _ROTATED_TABLE_HEADERS = {
        4: (
            "Reference",
            "HDS",
            "Medication",
            "Animal model (number)",
            "Study design",
            "Outcome measures",
            "Dose dependent",
            "Major findings",
        ),
        5: (
            "Reference",
            "HDS",
            "Medication",
            "Study design",
            "Population (number of participants)",
            "Outcome measures",
            "Evidence resources of interactions",
            "Results related to HDS–drug interactions",
        ),
        6: (
            "Reference",
            "HDS",
            "Dose schedule of HDS",
            "Medication",
            "Study design",
            "Country",
            "Population (number of participants)",
            "Outcome measures",
        ),
        7: (
            "Reference",
            "HDS",
            "Dose schedule of HDS",
            "Medication",
            "Study design",
            "Country",
            "Population (number of participants)",
            "Outcome measures",
        ),
    }
    _ROTATED_COLUMN_BOUNDARIES = {
        4: (55.0, 135.0, 235.0, 345.0, 435.0, 490.0, 570.0, 625.0, 735.0),
        5: (55.0, 120.0, 190.0, 255.0, 325.0, 405.0, 520.0, 610.0, 735.0),
        6: (55.0, 125.0, 220.0, 285.0, 355.0, 430.0, 495.0, 585.0, 735.0),
        7: (55.0, 125.0, 220.0, 285.0, 355.0, 430.0, 495.0, 585.0, 735.0),
    }
    _CONTRAINDICATION_CLASSES = (
        (140.0, "Gastrointestinal Diseases (n = 25, 16.4%)"),
        (205.0, "Neurologic Disorders (n = 22, 14.5%)"),
        (260.0, "Renal and Genitourinary Diseases (n = 19, 12.5%)"),
        (345.0, "Neoplastic Disorders (n = 18, 11.8%)"),
        (
            400.0,
            "Diseases of the Liver, Gallbladder, and Bile Ducts (n = 16, 10.5%)",
        ),
        (450.0, "Cardiovascular Disease (n = 14, 9.2%)"),
    )
    _CITATION_PATTERN = re.compile(r"\s*\(\d[\d,\s–-]*\)")
    _VERIFIED_SPACING_REPLACEMENTS = {
        "Chiangetal.": "Chiang et al.",
        "Methotrexate(intravenous)": "Methotrexate (intravenous)",
        "Puerarialobata(oral)": "Pueraria lobata (oral)",
        "Rats(7ineachgroup)": "Rats (7 in each group)",
        "Paralleldesign": "Parallel design",
        "Puerarialobatasigniifcantly": "Pueraria lobata significantly",
        "Puerarialobatasignificantly": "Pueraria lobata significantly",
        "Puerarialobata": "Pueraria lobata",
        "lobatasignificantly": "lobata significantly",
        "Ginkgobiloba(oral)": "Ginkgo biloba (oral)",
        "Evodiarutaecarpa(Wu-Chu-Yu)": "Evodia rutaecarpa (Wu-Chu-Yu)",
        "rutaecarpa(": "rutaecarpa (",
        "Andrographispaniculataand": "Andrographis paniculata and",
        "paniculataand": "paniculata and",
        "g u a r a n a": "guarana",
        "ho r s e c h e st n u t": "horse chestnut",
        "h o r se t a il": "horsetail",
        "li c o r ic e": "licorice",
        "m a g n e s iu m": "magnesium",
        "n o n i": "noni",
        "r h u b a r b": "rhubarb",
    }
    _LINE_TOP_TOLERANCE = 4.0

    def parse(
        self,
        *,
        page: Any,
        page_number: int,
        source_id: str,
    ) -> PdfLayoutExtraction | None:
        if source_id != self._SOURCE_ID:
            return None
        if page_number in self._EXCLUDED_PAGES:
            return PdfLayoutExtraction(blocks=[], warnings=[])

        words = self._words(page)
        if page_number in self._ROTATED_TABLE_HEADERS:
            return self._rotated_evidence_table(page, words, page_number)
        if page_number in {10, 11, 12, 13}:
            return self._major_interaction_page(page, words, page_number)
        if page_number == 14:
            return self._contraindication_page(page, words)
        return self._body_page(page, words, page_number)

    def _body_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
        page_number: int,
    ) -> PdfLayoutExtraction:
        width = float(page.width)
        if page_number == 1:
            regions = (
                _Region(120.0, 35.0, width - 35.0, 205.0),
                _Region(120.0, 205.0, 380.0, 535.0),
                _Region(120.0, 535.0, 330.0, 730.0),
                _Region(338.0, 535.0, width - 35.0, 730.0),
            )
        elif page_number == 15:
            # 결론 뒤의 감사·저자 기여·참고문헌은 검색 근거에서 제외한다.
            regions = (
                _Region(120.0, 45.0, 330.0, 500.0),
                _Region(338.0, 45.0, width - 35.0, 175.0),
            )
        elif page_number == 3:
            # 검색 흐름도(Figure 1)는 제외하고 결과 본문만 보존한다.
            regions = (
                _Region(120.0, 485.0, 330.0, 730.0),
                _Region(338.0, 485.0, width - 35.0, 730.0),
            )
        elif page_number == 8:
            regions = (
                _Region(40.0, 285.0, 260.0, 435.0),
                _Region(270.0, 285.0, width - 35.0, 435.0),
            )
        elif page_number == 9:
            regions = (
                _Region(120.0, 335.0, 330.0, 730.0),
                _Region(338.0, 335.0, width - 35.0, 730.0),
            )
        else:
            regions = (
                _Region(120.0, 45.0, 330.0, 730.0),
                _Region(338.0, 45.0, width - 35.0, 730.0),
            )
        blocks = self._text_blocks(words, regions)
        return PdfLayoutExtraction(
            blocks=self._ordered(blocks),
            warnings=[KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT],
        )

    def _major_interaction_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
        page_number: int,
    ) -> PdfLayoutExtraction:
        table_bottom = {10: 650.0, 11: 145.0, 12: 650.0, 13: 380.0}[page_number]
        table_words = [item for item in words if item["upright"] and 95.0 <= self._center_y(item) < table_bottom]
        rows = self._interaction_rows(table_words, page_number=page_number)
        title = (
            "HDS–drug interactions with major severity"
            if page_number in {10, 11}
            else "St John’s wort–drug interactions with major severity"
        )
        blocks: list[KnowledgePageBlock] = []
        if rows:
            blocks.append(
                self._table_block(
                    title=title,
                    headers=(
                        "Herb or dietary supplement",
                        "Drug",
                        "Potential consequence or reaction",
                    ),
                    rows=rows,
                    bbox=_Region(55.0, 95.0, float(page.width) - 35.0, table_bottom),
                )
            )
        if page_number in {11, 13}:
            body_top = {11: 205.0, 13: 440.0}[page_number]
            blocks.extend(
                self._text_blocks(
                    words,
                    (
                        _Region(120.0, body_top, 330.0, 730.0),
                        _Region(
                            338.0,
                            body_top,
                            float(page.width) - 35.0,
                            730.0,
                        ),
                    ),
                )
            )
        return PdfLayoutExtraction(
            blocks=self._ordered(blocks),
            warnings=[KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT],
        )

    def _interaction_rows(
        self,
        words: list[dict[str, Any]],
        *,
        page_number: int,
    ) -> list[KnowledgeTableRow]:
        rows: list[KnowledgeTableRow] = []
        current_hds = "St John’s wort" if page_number == 13 else ""
        pending_drug = ""
        hds_x0 = 35.0 if page_number in {11, 13} else 55.0
        for line in self._lines(words):
            hds = self._cell(line, hds_x0, 125.0)
            drug = self._cell(line, 125.0, 420.0)
            effect = self._cell(line, 420.0, 565.0)
            if hds:
                current_hds = hds
            if drug and not effect:
                if rows and rows[-1].cells[0] == self._clean(current_hds):
                    previous = rows[-1]
                    rows[-1] = KnowledgeTableRow(
                        cells=[
                            previous.cells[0],
                            " ".join([previous.cells[1], self._clean(drug)]),
                            previous.cells[2],
                        ]
                    )
                else:
                    pending_drug = " ".join(filter(None, [pending_drug, drug]))
                continue
            if effect and not drug and not hds and rows:
                previous = rows[-1]
                rows[-1] = KnowledgeTableRow(
                    cells=[
                        previous.cells[0],
                        previous.cells[1],
                        " ".join([previous.cells[2], self._clean(effect)]),
                    ]
                )
                continue
            if effect:
                complete_drug = " ".join(filter(None, [pending_drug, drug]))
                pending_drug = ""
                if current_hds and complete_drug:
                    rows.append(
                        KnowledgeTableRow(
                            cells=[
                                self._clean(current_hds),
                                self._clean(complete_drug),
                                self._clean(effect),
                            ]
                        )
                    )
        return [KnowledgeTableRow(cells=[self._clean(cell) for cell in row.cells]) for row in rows]

    def _rotated_evidence_table(
        self,
        page: Any,
        words: list[dict[str, Any]],
        page_number: int,
    ) -> PdfLayoutExtraction:
        logical_words = [
            {
                "text": self._restore_rotated_text(item),
                "x0": float(page.height) - item["bottom"],
                "x1": float(page.height) - item["top"],
                "top": item["x0"],
                "bottom": item["x1"],
                "upright": True,
            }
            for item in words
            if not item["upright"]
        ]
        boundaries = self._ROTATED_COLUMN_BOUNDARIES[page_number]
        headers = self._ROTATED_TABLE_HEADERS[page_number]
        data_top = {4: 140.0, 5: 85.0, 6: 105.0, 7: 230.0}[page_number]
        data_bottom = 450.0 if page_number == 7 else 500.0
        logical_lines = [
            line for line in self._lines(logical_words) if data_top <= self._center_y(line[0]) < data_bottom
        ]
        rows: list[KnowledgeTableRow] = []
        current: list[str] | None = None
        for line in logical_lines:
            cells = [self._cell(line, boundaries[index], boundaries[index + 1]) for index in range(len(headers))]
            normalized_reference = re.sub(r"\s+", "", cells[0]).casefold()
            reference_is_continuation = normalized_reference in {
                "etal.",
                "andschneir",
                "abduletal.",
            } or bool(re.fullmatch(r"\(\d[\d,\s–-]*\)", cells[0]))
            if cells[0] and not reference_is_continuation:
                if current and any(current):
                    rows.append(KnowledgeTableRow(cells=[self._clean(cell) for cell in current]))
                current = cells
            elif current is not None:
                current = [
                    " ".join(filter(None, [existing, continuation]))
                    for existing, continuation in zip(current, cells, strict=True)
                ]
        if current and any(current):
            rows.append(KnowledgeTableRow(cells=[self._clean(cell) for cell in current]))

        block = self._table_block(
            title=(f"HDS-drug interaction evidence studies (Table {min(page_number - 3, 3)})"),
            headers=headers,
            rows=rows,
            bbox=_Region(55.0, data_top, float(page.height) - 35.0, float(page.width) - 35.0),
        )
        return PdfLayoutExtraction(
            blocks=[block],
            warnings=[KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT],
        )

    def _contraindication_page(
        self,
        page: Any,
        words: list[dict[str, Any]],
    ) -> PdfLayoutExtraction:
        table_words = [item for item in words if item["upright"] and 55.0 <= self._center_y(item) < 450.0]
        condition_lines = self._lines([item for item in table_words if 210.0 <= self._center_x(item) < 325.0])
        condition_rows = [(self._center_y(line[0]), self._clean(self._render_line(line))) for line in condition_lines]
        ingredients_by_row: list[list[str]] = [[] for _ in condition_rows]
        ingredient_lines = self._lines([item for item in table_words if 325.0 <= self._center_x(item) < 455.0])
        for line in ingredient_lines:
            ingredients = self._clean(self._render_line(line))
            if not ingredients or not condition_rows:
                continue
            y = self._center_y(line[0])
            row_index = min(
                range(len(condition_rows)),
                key=lambda index: abs(condition_rows[index][0] - y),
            )
            ingredients_by_row[row_index].append(ingredients)
        rows = [
            KnowledgeTableRow(
                cells=[
                    self._contraindication_class(y),
                    condition,
                    self._clean(" ".join(ingredients_by_row[index])),
                ]
            )
            for index, (y, condition) in enumerate(condition_rows)
            if ingredients_by_row[index]
        ]
        blocks: list[KnowledgePageBlock] = []
        if rows:
            blocks.append(
                self._table_block(
                    title=("Contraindication relationships for herbs and dietary supplements"),
                    headers=(
                        "Class of contraindications",
                        "Contraindications",
                        "HDS which should be avoided and/or not recommended",
                    ),
                    rows=rows,
                    bbox=_Region(210.0, 55.0, 455.0, 450.0),
                )
            )
        blocks.extend(
            self._text_blocks(
                words,
                (
                    _Region(40.0, 550.0, 260.0, float(page.height) - 30.0),
                    _Region(
                        270.0,
                        550.0,
                        float(page.width) - 35.0,
                        float(page.height) - 30.0,
                    ),
                ),
            )
        )
        return PdfLayoutExtraction(
            blocks=self._ordered(blocks),
            warnings=[KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT],
        )

    def _contraindication_class(self, y: float) -> str:
        for bottom, class_name in self._CONTRAINDICATION_CLASSES:
            if y < bottom:
                return class_name
        return self._CONTRAINDICATION_CLASSES[-1][1]

    def _text_blocks(
        self,
        words: list[dict[str, Any]],
        regions: tuple[_Region, ...],
    ) -> list[KnowledgePageBlock]:
        blocks: list[KnowledgePageBlock] = []
        for region in regions:
            selected = [item for item in words if item["upright"] and self._inside(item, region)]
            rendered_lines = [self._clean_body_line(self._render_line(line)) for line in self._lines(selected)]
            content = "\n".join(line for line in rendered_lines if line).strip()
            if content:
                blocks.append(
                    KnowledgePageBlock(
                        kind=KnowledgeContentKind.TEXT,
                        order=0,
                        bbox=KnowledgeBoundingBox(**region.__dict__),
                        content=content,
                    )
                )
        return blocks

    def _table_block(
        self,
        *,
        title: str,
        headers: tuple[str, ...],
        rows: list[KnowledgeTableRow],
        bbox: _Region,
    ) -> KnowledgePageBlock:
        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(headers, row.cells, strict=True) if cell)
            for row in rows
            if any(row.cells)
        )
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(**bbox.__dict__),
            content=content or "No indexable rows",
            headers=list(headers),
            rows=rows,
            column_count=len(headers),
            table_title=title,
            validation_errors=[],
        )

    def _lines(self, words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        lines: list[list[dict[str, Any]]] = []
        for item in sorted(words, key=lambda word: (word["top"], word["x0"])):
            if not lines or abs(lines[-1][0]["top"] - item["top"]) > self._LINE_TOP_TOLERANCE:
                lines.append([item])
            else:
                lines[-1].append(item)
        return lines

    def _cell(self, line: list[dict[str, Any]], x0: float, x1: float) -> str:
        selected = [item for item in line if x0 <= self._center_x(item) < x1]
        return self._render_line(selected)

    @staticmethod
    def _render_line(words: list[dict[str, Any]]) -> str:
        return " ".join(item["text"] for item in sorted(words, key=lambda word: word["x0"])).strip()

    def _clean(self, value: str) -> str:
        value = unicodedata.normalize("NFKC", value)
        value = self._CITATION_PATTERN.sub("", value)
        value = re.sub(r"(?<=[A-Za-z])etal\.", " et al.", value)
        value = re.sub(r"\betal\.", "et al.", value)
        value = value.replace("›", "↑")
        value = re.sub(r"^fl(?=[A-Z])", "↓", value)
        for source, replacement in self._VERIFIED_SPACING_REPLACEMENTS.items():
            value = value.replace(source, replacement)
        return re.sub(r"\s+", " ", value).strip()

    def _clean_body_line(self, value: str) -> str:
        compact = re.sub(r"\s+", "", value).casefold()
        if (
            "intjclinpract" in compact
            or "blackwellpublishingltd" in compact
            or ("h.-h.tsai" in compact and "g.b.mahady" in compact)
            or compact.isdigit()
        ):
            return ""
        return self._clean(value)

    @staticmethod
    def _restore_rotated_text(word: dict[str, Any]) -> str:
        chars = word.get("chars") or []
        if not chars:
            return word["text"][::-1]

        restored: list[str] = []
        previous: dict[str, Any] | None = None
        for char in reversed(chars):
            if previous is not None:
                gap = float(previous["top"]) - float(char["bottom"])
                if gap > 1.2:
                    restored.append(" ")
            restored.append(str(char["text"]))
            previous = char
        return "".join(restored).strip()

    @staticmethod
    def _inside(word: dict[str, Any], region: _Region) -> bool:
        x = HerbDrugReviewLayoutParser._center_x(word)
        y = HerbDrugReviewLayoutParser._center_y(word)
        return region.x0 <= x < region.x1 and region.top <= y < region.bottom

    @staticmethod
    def _center_x(word: dict[str, Any]) -> float:
        return (word["x0"] + word["x1"]) / 2

    @staticmethod
    def _center_y(word: dict[str, Any]) -> float:
        return (word["top"] + word["bottom"]) / 2

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
                extra_attrs=["upright"],
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
                "chars": list(word.get("chars") or []),
            }
            for word in raw_words
            if str(word.get("text", "")).strip()
        ]
