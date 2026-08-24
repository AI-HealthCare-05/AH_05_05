import math
import re
import unicodedata
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from ai_worker.schemas.knowledge import KnowledgePage


class TextQualityStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    OCR_REQUIRED = "OCR_REQUIRED"


class TextQualityReasonCode(StrEnum):
    TOO_SHORT = "TOO_SHORT"
    REPLACEMENT_CHARACTER = "REPLACEMENT_CHARACTER"
    LONG_UNSPACED_RUN = "LONG_UNSPACED_RUN"


class TextQualityReport(BaseModel):
    status: TextQualityStatus
    reason_codes: list[TextQualityReasonCode] = Field(default_factory=list)
    character_count: int = Field(ge=0)


class KnowledgeNormalizer:
    _PAGE_NUMBER_PATTERN = re.compile(r"^(?:-\s*)?\d{1,4}(?:\s*/\s*\d{1,4})?(?:\s*-)?$")
    _CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _LONG_UNSPACED_PATTERN = re.compile(r"\S{120,}")

    def normalize_pages(
        self,
        pages: list[KnowledgePage],
    ) -> list[KnowledgePage]:
        if not pages:
            return []

        normalized_lines = [self._normalize_lines(page.content) for page in pages]
        repeated_edges = self._find_repeated_edge_lines(normalized_lines)
        normalized_pages: list[KnowledgePage] = []

        for page, lines in zip(pages, normalized_lines, strict=True):
            retained = [
                line for line in lines if line not in repeated_edges and not self._PAGE_NUMBER_PATTERN.fullmatch(line)
            ]
            content = "\n".join(retained).strip()
            if not content:
                continue
            normalized_pages.append(page.model_copy(update={"content": content}))

        return normalized_pages

    def assess_quality(self, content: str) -> TextQualityReport:
        normalized = self._normalize_text(content)
        return self._build_quality_report(
            character_count=len(normalized),
            has_replacement_character="�" in normalized,
            has_long_unspaced_run=bool(self._LONG_UNSPACED_PATTERN.search(normalized)),
        )

    def assess_pages_quality(
        self,
        pages: list[KnowledgePage],
    ) -> TextQualityReport:
        contents = [self._normalize_text(page.content) for page in pages]
        character_count = sum(len(content) for content in contents)
        if contents:
            character_count += 2 * (len(contents) - 1)
        return self._build_quality_report(
            character_count=character_count,
            has_replacement_character=any("�" in content for content in contents),
            has_long_unspaced_run=any(self._LONG_UNSPACED_PATTERN.search(content) for content in contents),
        )

    @staticmethod
    def _build_quality_report(
        *,
        character_count: int,
        has_replacement_character: bool,
        has_long_unspaced_run: bool,
    ) -> TextQualityReport:
        reason_codes: list[TextQualityReasonCode] = []

        if character_count < 60:
            reason_codes.append(TextQualityReasonCode.TOO_SHORT)

        if has_replacement_character:
            reason_codes.append(TextQualityReasonCode.REPLACEMENT_CHARACTER)

        if has_long_unspaced_run:
            reason_codes.append(TextQualityReasonCode.LONG_UNSPACED_RUN)

        if (
            TextQualityReasonCode.LONG_UNSPACED_RUN in reason_codes
            or TextQualityReasonCode.REPLACEMENT_CHARACTER in reason_codes
        ):
            status = TextQualityStatus.OCR_REQUIRED
        elif reason_codes:
            status = TextQualityStatus.REVIEW
        else:
            status = TextQualityStatus.PASS

        return TextQualityReport(
            status=status,
            reason_codes=reason_codes,
            character_count=character_count,
        )

    def _normalize_lines(self, content: str) -> list[str]:
        normalized = self._normalize_text(content)
        return [line for line in normalized.splitlines() if line]

    def _normalize_text(self, content: str) -> str:
        normalized = unicodedata.normalize("NFKC", content)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = self._CONTROL_PATTERN.sub("", normalized)
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r" *\n *", "\n", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _find_repeated_edge_lines(pages: list[list[str]]) -> set[str]:
        candidates: Counter[str] = Counter()
        for lines in pages:
            edge_lines = set(lines[:2] + lines[-2:])
            candidates.update(line for line in edge_lines if 8 <= len(line) <= 120)

        minimum_count = max(2, math.ceil(len(pages) * 0.5))
        return {line for line, count in candidates.items() if count >= minimum_count}
