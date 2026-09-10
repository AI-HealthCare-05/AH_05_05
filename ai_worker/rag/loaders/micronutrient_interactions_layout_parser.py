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


class MicronutrientInteractionsLayoutParser:
    """검수된 2단 구성의 미량영양소 상호작용 논문에서 본문만 복원합니다."""

    _SOURCE_ID = "research_micronutrient_interactions"
    _DOCUMENT_ID = "research_micronutrient_interactions-e3b164ce9cc98cc6"
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
        if page_number > 3:
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
                _Region(50.0, 80.0, 545.0, 120.0),
                _Region(115.0, 180.0, 475.0, 410.0),
                _Region(40.0, 445.0, 285.0, 735.0),
                _Region(305.0, 445.0, 550.0, 735.0),
            )
        if page_number == 2:
            return (
                _Region(40.0, 270.0, 285.0, 735.0),
                _Region(305.0, 270.0, 550.0, 735.0),
            )
        return (
            _Region(40.0, 50.0, 285.0, 735.0),
            _Region(305.0, 50.0, 550.0, 575.0),
        )

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
        content = "\n".join(
            line
            for line in content.splitlines()
            if not re.match(r"^Corresponding author:", line.strip(), flags=re.IGNORECASE)
            and not re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", line)
        )
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
