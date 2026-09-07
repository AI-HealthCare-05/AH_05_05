import re
from dataclasses import dataclass
from typing import Any

from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgePageBlock,
)


@dataclass(frozen=True)
class _Region:
    x0: float
    top: float
    x1: float
    bottom: float


class LevothyroxineCalciumReviewLayoutParser:
    """검수된 levothyroxine-calcium 연구의 2단 본문만 읽습니다."""

    _SOURCE_ID = "research_drug_nutrient_interactions"
    _DOCUMENT_ID = "research_drug_nutrient_interactions-502801c809b5ec8d"
    _LINE_TOP_TOLERANCE = 4.0
    _NUMERIC_CITATION_PATTERN = re.compile(r"\s*\(\s*\d+(?:\s*(?:[,;]|[-–—])\s*\d+)*\s*\)")
    _FIGURE_REFERENCE_PATTERN = re.compile(
        r"\s*[\[(]\s*Fig\.?\s*\d+\s*[\])]",
        flags=re.IGNORECASE,
    )

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
        if page_number > 4:
            return PdfLayoutExtraction(blocks=[], warnings=[])

        words = self._words(page)
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
                _Region(55.0, 95.0, 555.0, 150.0),
                _Region(55.0, 215.0, 555.0, 425.0),
                _Region(55.0, 460.0, 305.0, 710.0),
                _Region(305.0, 460.0, 555.0, 555.0),
                _Region(305.0, 555.0, 555.0, 710.0),
            )
        if page_number == 2:
            return (
                _Region(55.0, 55.0, 305.0, 110.0),
                _Region(55.0, 110.0, 305.0, 435.0),
                _Region(55.0, 435.0, 305.0, 585.0),
                _Region(55.0, 585.0, 305.0, 745.0),
                _Region(305.0, 55.0, 555.0, 440.0),
                _Region(305.0, 440.0, 555.0, 655.0),
            )
        if page_number == 3:
            return (
                _Region(55.0, 310.0, 305.0, 745.0),
                _Region(305.0, 55.0, 555.0, 120.0),
                _Region(305.0, 120.0, 555.0, 515.0),
                _Region(305.0, 515.0, 555.0, 745.0),
            )
        return (_Region(55.0, 55.0, 305.0, 245.0),)

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

    @classmethod
    def _clean_content(cls, content: str) -> str:
        content = re.sub(r"(?<=[A-Za-z])[-‐]\n(?=[a-z])", "", content)
        content = cls._NUMERIC_CITATION_PATTERN.sub("", content)
        content = cls._FIGURE_REFERENCE_PATTERN.sub("", content)
        content = re.sub(r"\b(Synthroid|PhosLo)\s+\(cid:2\)", r"\1", content)
        content = re.sub(r"\(cid:2\)\s*(?=\d)", "−", content)
        content = content.replace("(cid:3)", "±")
        content = re.sub(r"\bm\s+g(?=/)", "μg", content)
        content = re.sub(r"\bþ\s*(?=\d)", "+", content)
        content = re.sub(r"\(\s*F\s+1⁄4\s+", "(F = ", content)
        content = re.sub(r"−(\d+)\s+8\s+C\b", r"−\1°C", content)
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
