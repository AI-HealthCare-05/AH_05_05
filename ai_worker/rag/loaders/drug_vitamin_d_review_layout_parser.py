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


class DrugVitaminDReviewLayoutParser:
    """검수된 NIH 원고 지면에서 약물–비타민 D 본문만 복원합니다."""

    _SOURCE_ID = "research_drug_nutrient_interactions"
    _DOCUMENT_ID = "research_drug_nutrient_interactions-80c3d674cbc86d03"
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
        # 14쪽부터 부록·감사의 글·참고문헌이며 이후에는 그림과 표만 있다.
        if page_number >= 14:
            return PdfLayoutExtraction(blocks=[], warnings=[])

        words = self._words(page)
        if page_number == 1:
            regions = (
                _Region(85.0, 120.0, 530.0, 155.0),
                _Region(85.0, 380.0, 530.0, 690.0),
            )
        elif page_number == 2:
            regions = (
                _Region(85.0, 65.0, 530.0, 115.0),
                _Region(85.0, 120.0, 530.0, 700.0),
            )
        else:
            regions = (_Region(85.0, 55.0, 530.0, 700.0),)

        blocks = [block for region in regions if (block := self._text_block(words, region)) is not None]
        return PdfLayoutExtraction(
            blocks=[block.model_copy(update={"order": index}) for index, block in enumerate(blocks)],
            warnings=[],
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
        ordered = sorted(words, key=lambda item: item["x0"])
        regular = [word for word in ordered if float(word["size"]) >= 9.0]
        if not regular:
            return ""
        baseline_top = sum(float(word["top"]) for word in regular) / len(regular)
        rendered: list[str] = []
        previous: dict[str, Any] | None = None
        for word in ordered:
            size = float(word["size"])
            if size < 9.0:
                # 위첨자 숫자는 인용 번호이므로 제외하고, 아래첨자 숫자만 화학식에 붙인다.
                if previous is None or float(word["top"]) <= baseline_top + 2.0:
                    continue
                rendered[-1] = f"{rendered[-1]}{word['text']}"
                continue
            rendered.append(str(word["text"]))
            previous = word
        return " ".join(rendered)

    @staticmethod
    def _clean_content(content: str) -> str:
        content = re.sub(r"(?im)^\s*(?:Author|Manuscript)\s*$", "", content)
        content = re.sub(r"(?i)^Keywords\s*\n\s*", "Keywords: ", content)
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
                "size": float(word.get("size", 10.0)),
                "fontname": str(word.get("fontname", "")),
            }
            for word in raw_words
            if str(word.get("text", "")).strip()
        ]
