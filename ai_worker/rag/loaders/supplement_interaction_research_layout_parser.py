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


class SupplementInteractionResearchLayoutParser:
    """검수된 영양제 상호작용 연구 PDF의 본문 읽기 순서를 복원합니다.

    두 논문은 일반 추출 시 두 단·회전된 여백·표가 섞입니다. 좌표 영역을
    명시해 본문만 좌→우 순서로 읽고, 수동 검수에서 제외한 저자·각주·표는
    결과에서 제외합니다.
    """

    _SOURCE_ID = "research_supplement_interactions"
    _CALCIUM_IRON_DOCUMENT_ID = "research_supplement_interactions-016c81c9a3e29ebd"
    _ZINC_IRON_DOCUMENT_ID = "research_supplement_interactions-ce2c45272c5bd272"
    _VITAMIN_C_COPPER_DOCUMENT_ID = "research_supplement_interactions-7cc01e25b07044ff"
    _VITAMIN_C_IRON_TRIAL_DOCUMENT_ID = "research_supplement_interactions-6152f916c012be79"
    _LINE_TOP_TOLERANCE = 4.0

    def parse(
        self,
        *,
        page: Any,
        page_number: int,
        source_id: str,
        document_id: str | None = None,
    ) -> PdfLayoutExtraction | None:
        if source_id != self._SOURCE_ID:
            return None

        words = self._words(page)
        if document_id == self._CALCIUM_IRON_DOCUMENT_ID:
            regions = self._calcium_iron_regions(page_number=page_number, page=page)
        elif document_id == self._ZINC_IRON_DOCUMENT_ID:
            regions = self._zinc_iron_regions(page_number=page_number, page=page)
        elif document_id == self._VITAMIN_C_COPPER_DOCUMENT_ID:
            regions = self._vitamin_c_copper_regions(page_number=page_number, page=page)
        elif document_id == self._VITAMIN_C_IRON_TRIAL_DOCUMENT_ID:
            regions = self._vitamin_c_iron_trial_regions(page_number=page_number, page=page)
        else:
            return None

        if regions is None:
            return None

        blocks = [
            block
            for region in regions
            if (
                block := self._region_text_block(
                    document_id=document_id,
                    page=page,
                    words=words,
                    region=region,
                )
            )
            is not None
        ]
        return PdfLayoutExtraction(
            blocks=[block.model_copy(update={"order": index}) for index, block in enumerate(blocks)],
            warnings=[],
        )

    @staticmethod
    def _calcium_iron_regions(*, page_number: int, page: Any) -> tuple[_Region, ...]:
        width = float(page.width)
        if page_number == 1:
            return (
                _Region(55.0, 115.0, width - 55.0, 245.0),
                _Region(60.0, 330.0, width - 60.0, 570.0),
                _Region(55.0, 590.0, 300.0, 730.0),
                _Region(300.0, 590.0, width - 50.0, 730.0),
            )
        if 2 <= page_number <= 7:
            return (
                _Region(55.0, 65.0, 300.0, 730.0),
                _Region(300.0, 65.0, width - 50.0, 730.0),
            )
        return ()

    @staticmethod
    def _vitamin_c_copper_regions(*, page_number: int, page: Any) -> tuple[_Region, ...] | None:
        """2쪽의 Materials/Cell Culture 본문만 전용 좌표로 읽습니다.

        이 쪽은 이전 Introduction의 끝과 2.1 본문이 일반 추출에서 섞였고,
        페이지 번호가 2.2 소제목에 붙었습니다. 다른 페이지는 기존의 일반
        추출기에서 충분히 읽히므로 이 검수 완료 구간만 대체합니다.
        """
        if page_number != 2:
            return None
        return (
            _Region(65.0, 440.0, float(page.width) - 15.0, 690.0),
            _Region(65.0, 690.0, float(page.width) - 15.0, float(page.height) - 50.0),
        )

    @staticmethod
    def _vitamin_c_iron_trial_regions(*, page_number: int, page: Any) -> tuple[_Region, ...]:
        """JAMA 임상시험에서 본문만 보존하고 흐름도·표·서지 영역을 제외합니다."""
        width = float(page.width)
        if page_number == 1:
            return (_Region(34.0, 80.0, width - 34.0, 132.0),)
        if page_number == 2:
            return (_Region(34.0, 165.0, width - 34.0, 720.0),)
        if page_number == 3:
            return (_Region(34.0, 104.0, width - 34.0, 460.0),)
        if page_number == 4:
            return (_Region(34.0, 55.0, width - 34.0, 720.0),)
        if page_number == 5:
            return (_Region(34.0, 55.0, width - 34.0, 420.0),)
        if page_number == 6:
            return (_Region(34.0, 55.0, width - 34.0, 590.0),)
        if page_number == 8:
            return (_Region(34.0, 55.0, width - 34.0, 430.0),)
        return ()

    @staticmethod
    def _zinc_iron_regions(*, page_number: int, page: Any) -> tuple[_Region, ...]:
        width = float(page.width)
        if page_number == 1:
            return (
                _Region(33.0, 100.0, width - 60.0, 140.0),
                _Region(33.0, 225.0, width - 30.0, 430.0),
                _Region(33.0, 445.0, 298.0, 620.0),
                _Region(299.0, 565.0, width - 30.0, 625.0),
            )
        if page_number == 2:
            return (
                _Region(33.0, 60.0, 298.0, 625.0),
                _Region(299.0, 60.0, width - 30.0, 700.0),
                _Region(33.0, 700.0, 298.0, 735.0),
            )
        if page_number == 3:
            return (
                _Region(33.0, 60.0, 298.0, 535.0),
                _Region(299.0, 450.0, width - 30.0, 735.0),
            )
        if page_number == 4:
            return (
                _Region(33.0, 60.0, 298.0, 735.0),
                _Region(299.0, 60.0, width - 30.0, 450.0),
            )
        return ()

    def _text_block(self, *, words: list[dict[str, Any]], region: _Region) -> KnowledgePageBlock | None:
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

    def _region_text_block(
        self,
        *,
        document_id: str | None,
        page: Any,
        words: list[dict[str, Any]],
        region: _Region,
    ) -> KnowledgePageBlock | None:
        if document_id == self._VITAMIN_C_COPPER_DOCUMENT_ID:
            text_block = self._vitamin_c_copper_text_block(page=page, region=region)
            if text_block is not None:
                return text_block
        return self._text_block(words=words, region=region)

    def _vitamin_c_copper_text_block(self, *, page: Any, region: _Region) -> KnowledgePageBlock | None:
        """문자 간 공백이 사라진 원문은 영역 단위 텍스트 추출을 우선합니다.

        이 논문의 2쪽은 ``extract_words``가 한 줄 전체를 하나의 단어로 반환해
        약품명과 문장 내 공백이 사라집니다. pdfplumber의 영역 텍스트 추출은 문자
        위치로 공백을 복원하므로, 검수한 Materials·Cell Culture 본문에만 적용합니다.
        """
        crop = getattr(page, "crop", None)
        if not callable(crop):
            return None
        try:
            cropped_page = crop((region.x0, region.top, region.x1, region.bottom))
            extract_text = getattr(cropped_page, "extract_text", None)
            if not callable(extract_text):
                return None
            raw_content = extract_text(x_tolerance=1, y_tolerance=3)
        except (AttributeError, TypeError, ValueError):
            return None
        if not raw_content:
            return None

        content = self._clean_vitamin_c_copper_region_text(str(raw_content))
        if not content:
            return None
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(**region.__dict__),
            content=content,
        )

    def _clean_vitamin_c_copper_region_text(self, content: str) -> str:
        content = re.sub(r"CuSO\s*;\s*Cu2\+", "CuSO4; Cu2+", content)
        content = re.sub(r"\n\s*4\s*\n", "\n", content)
        content = self._clean_content(content)
        content = re.sub(r"\bGibco-\s+BRL\b", "Gibco-BRL", content)
        content = re.sub(
            r"\bCO\s*/\s*95%(\s+air\s+at\s+37\s+◦C\.\s+For\s+experiments,\s+cells)\s+2\s+were",
            r"CO2/95%\1 were",
            content,
        )

        rendered_lines: list[str] = []
        paragraph_lines: list[str] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^2(?:\.\d+)?\.\s+", line):
                if paragraph_lines:
                    rendered_lines.append(" ".join(paragraph_lines))
                    paragraph_lines = []
                rendered_lines.append(line)
                continue
            paragraph_lines.append(line)
        if paragraph_lines:
            rendered_lines.append(" ".join(paragraph_lines))
        return "\n".join(rendered_lines).strip()

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
        content = re.sub(r"(?m)^\s*\d+\s+of\s+\d+\s*$", "", content)
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
