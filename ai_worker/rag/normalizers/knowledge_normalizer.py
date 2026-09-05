import math
import re
import unicodedata
from collections import Counter
from enum import StrEnum

from pydantic import BaseModel, Field

from ai_worker.schemas.knowledge import (
    KnowledgeContentKind,
    KnowledgePage,
    KnowledgeTableRow,
)


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
    _PAGE_NUMBER_PATTERN = re.compile(
        r"^(?:-\s*)?\d{1,4}(?:(?:\s*/\s*|\s*of\s*)\d{1,4})?(?:\s*-)?$",
        flags=re.IGNORECASE,
    )
    _DOWNLOAD_AUDIT_PATTERN = re.compile(
        r"^https?://\S+\s+-\s+.*\bIP Address:\s*\S+$",
        flags=re.IGNORECASE,
    )
    _DOCUMENT_PRODUCTION_PATTERN = re.compile(
        r"^.+\.indd\s+\d+\s+\d{4}-\d{2}-\d{2}\s+"
        r"(?:오전|오후)\s+\d{1,2}:\d{2}:\d{2}$"
    )
    _PUBLISHER_BANNER_PATTERN = re.compile(
        r"^NATIONAL INSTITUTE OF FOOD AND DRUG SAFETY"
        r"(?:\s*/\s*www\.nifds\.go\.kr)?$",
        flags=re.IGNORECASE,
    )
    _CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _LONG_UNSPACED_PATTERN = re.compile(r"\S{120,}")
    _WRAPPED_LATIN_WORD_PATTERN = re.compile(
        r"(?P<left>[A-Za-z]{2,})\s*(?P<hyphen>[-–—])\s*\n"
        r"(?P<right>[A-Za-z]{2,})"
    )
    _SPLIT_LATIN_WORD_PATTERN = re.compile(r"\b(?P<left>[a-z]{2,8}) (?P<right>[a-z]{3,10})\b")
    _CAPITALIZED_SPLIT_LATIN_WORD_PATTERN = re.compile(r"\b(?P<left>[A-Z]) (?P<right>[a-z]{2,10})\b")
    _LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]{4,}")
    _FDA_CONTENTS_PATTERN = re.compile(
        r"^FULL PRESCRIBING INFORMATION:\s*CONTENTS\*?",
        flags=re.IGNORECASE,
    )
    _ACADEMIC_PAGE_FURNITURE_PATTERNS = (
        re.compile(
            r"^Nutrients\s*20\d{2},?\s*\d+,?\s*(?:\d+|x\s+FOR\s+PEER\s+REVIEW)\b.*$",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^Therapeutics and Clinical Risk Management\s+20\d{2}:\d+\b.*$",
            flags=re.IGNORECASE,
        ),
        re.compile(r"^(?:DovePress|Dovepress(?:\s+.+)?)$", flags=re.IGNORECASE),
        re.compile(r"^https?://doi\.org/\S+$", flags=re.IGNORECASE),
        re.compile(
            r"^https?://(?:www\.)?mdpi\.com/journal/\S+$",
            flags=re.IGNORECASE,
        ),
        re.compile(r"^.+\s+Dovepress$", flags=re.IGNORECASE),
    )
    _NUMERIC_CITATION_PATTERN = re.compile(r"[ \t]*\[\s*\d+(?:\s*(?:[,;]|[-–—])\s*\d+)*\s*\]")
    _FIGURE_CAPTION_PATTERN = re.compile(
        r"^\s*Figures?\s+\d+(?:\s*(?:,|and|&|[-–—])\s*\d+)*\s*[.:].*$",
        flags=re.IGNORECASE,
    )
    _PARENTHETICAL_FIGURE_REFERENCE_PATTERN = re.compile(
        r"\s*\(\s*Figures?\s+\d+"
        r"(?:\s*(?:,|and|&|[-–—])\s*\d+)*\s*\)",
        flags=re.IGNORECASE,
    )
    _PREPOSITIONAL_FIGURE_REFERENCE_PATTERN = re.compile(
        r"\s+in\s+Figures?\s+\d+"
        r"(?:\s*(?:,|and|&|[-–—])\s*\d+)*"
        r"(?=[,.;:)]|$)",
        flags=re.IGNORECASE,
    )
    _EMPTY_REFERENCE_FIELD_PATTERN = re.compile(
        r"(?:\s*\|\s*)?References=\s*(?=\||$)",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    _PAGE_END_WORD_FRAGMENT_PATTERN = re.compile(r"(?P<left>[A-Za-z]{2,})[-–—]\s*$")
    _PAGE_START_WORD_FRAGMENT_PATTERN = re.compile(r"^\s*(?P<right>[a-z]{2,})(?P<punctuation>[,;:]?)")
    _DOVE_LICENSE_BLOCK_PATTERN = re.compile(
        r"(?ims)^©\s*20\d{2}\s+.+?Dove Medical Press Limited\..*?"
        r"^Published:\s*[^\n]+\n?"
    )
    _BPS_PAGE_FOOTER_PATTERN = re.compile(
        r"(?ims)^British Journal of Clinical\s*\nPharmacology\s*\n"
        r"DOI:\S+\s*\n©\s*20\d{2}.+?$"
    )
    _FDA_FOOTER_PATTERNS = (
        re.compile(r"^Reference ID:\s*\d+$", flags=re.IGNORECASE),
        re.compile(r"^Revised:\s*\d{1,2}/\d{4}$", flags=re.IGNORECASE),
    )
    _INLINE_PUBLISHER_PREFIX_PATTERNS = (
        re.compile(
            r"(?im)^Copyright:\s*©\s*20\d{2}\s+by\s+the\s+authors\.\s*",
        ),
        re.compile(
            r"(?im)^Licensee\s+MDPI,\s*Basel,\s*Switzerland\.\s*",
        ),
        re.compile(
            r"(?im)^This\s*article\s*is\s*an\s*open\s*access\s*article\s*",
        ),
    )

    def normalize_pages(
        self,
        pages: list[KnowledgePage],
        *,
        verified_text_replacements: dict[str, str] | None = None,
    ) -> list[KnowledgePage]:
        if not pages:
            return []

        replacements = verified_text_replacements or {}
        normalized_texts = [
            self._apply_verified_text_replacements(
                self._normalize_text(page.content),
                replacements,
            )
            for page in pages
        ]
        intact_words = {
            word.casefold() for content in normalized_texts for word in self._LATIN_WORD_PATTERN.findall(content)
        }
        normalized_lines = [
            self._apply_verified_text_replacements(
                self._repair_split_latin_words(
                    self._repair_wrapped_latin_words(content, intact_words),
                    intact_words,
                ),
                replacements,
            ).splitlines()
            for content in normalized_texts
        ]
        repeated_edge_signatures = self._find_repeated_edge_signatures(normalized_lines)
        normalized_pages: list[KnowledgePage] = []

        for page, lines in zip(pages, normalized_lines, strict=True):
            if lines and self._FDA_CONTENTS_PATTERN.match(lines[0]):
                continue
            retained = self._retain_content_lines(
                lines,
                repeated_edge_signatures,
            )
            content = "\n".join(retained).strip()
            if not content:
                continue
            normalized_blocks = []
            for block in sorted(page.blocks, key=lambda item: item.order):
                block_content = self._normalize_block_content(
                    block.content,
                    intact_words=intact_words,
                    repeated_edge_signatures=repeated_edge_signatures,
                    verified_text_replacements=replacements,
                )
                if not block_content:
                    continue
                update: dict[str, object] = {
                    "content": block_content,
                    "order": len(normalized_blocks),
                }
                if block.kind == KnowledgeContentKind.TABLE:
                    update["headers"] = [
                        self._apply_verified_text_replacements(
                            self._normalize_text(header),
                            replacements,
                        )
                        for header in block.headers
                    ]
                    update["rows"] = [
                        KnowledgeTableRow(
                            cells=[
                                self._apply_verified_text_replacements(
                                    self._normalize_text(cell),
                                    replacements,
                                )
                                for cell in row.cells
                            ]
                        )
                        for row in block.rows
                    ]
                normalized_blocks.append(block.model_copy(update=update))
            normalized_pages.append(
                page.model_copy(
                    update={
                        "content": content,
                        "blocks": normalized_blocks,
                    }
                )
            )

        return self._repair_verified_page_boundaries(
            normalized_pages,
            intact_words=intact_words,
        )

    def _normalize_block_content(
        self,
        content: str,
        *,
        intact_words: set[str],
        repeated_edge_signatures: set[str],
        verified_text_replacements: dict[str, str],
    ) -> str:
        normalized = self._normalize_text(content)
        normalized = self._apply_verified_text_replacements(
            normalized,
            verified_text_replacements,
        )
        normalized = self._repair_wrapped_latin_words(
            normalized,
            intact_words,
        )
        normalized = self._repair_split_latin_words(
            normalized,
            intact_words,
        )
        normalized = self._apply_verified_text_replacements(
            normalized,
            verified_text_replacements,
        )
        retained = self._retain_content_lines(
            normalized.splitlines(),
            repeated_edge_signatures,
        )
        return "\n".join(retained).strip()

    @staticmethod
    def _apply_verified_text_replacements(
        content: str,
        replacements: dict[str, str],
    ) -> str:
        for source, replacement in replacements.items():
            content = content.replace(source, replacement)
        return content

    def _retain_content_lines(
        self,
        lines: list[str],
        repeated_edge_signatures: set[str],
    ) -> list[str]:
        return [
            line
            for line in lines
            if self._edge_signature(line) not in repeated_edge_signatures
            and not self._PAGE_NUMBER_PATTERN.fullmatch(line)
            and not self._DOWNLOAD_AUDIT_PATTERN.fullmatch(line)
            and not self._DOCUMENT_PRODUCTION_PATTERN.fullmatch(line)
            and not self._PUBLISHER_BANNER_PATTERN.fullmatch(line)
            and not self._FIGURE_CAPTION_PATTERN.fullmatch(line)
            and not any(pattern.fullmatch(line) for pattern in self._FDA_FOOTER_PATTERNS)
            and not any(pattern.fullmatch(line) for pattern in self._ACADEMIC_PAGE_FURNITURE_PATTERNS)
        ]

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
        normalized = normalized.replace("\u00ad", "")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = self._CONTROL_PATTERN.sub("", normalized)
        normalized = self._DOVE_LICENSE_BLOCK_PATTERN.sub("", normalized)
        normalized = self._BPS_PAGE_FOOTER_PATTERN.sub("", normalized)
        for pattern in self._INLINE_PUBLISHER_PREFIX_PATTERNS:
            normalized = pattern.sub("", normalized)
        normalized = self._NUMERIC_CITATION_PATTERN.sub("", normalized)
        normalized = self._PARENTHETICAL_FIGURE_REFERENCE_PATTERN.sub(
            "",
            normalized,
        )
        normalized = self._PREPOSITIONAL_FIGURE_REFERENCE_PATTERN.sub(
            "",
            normalized,
        )
        normalized = self._EMPTY_REFERENCE_FIELD_PATTERN.sub("", normalized)
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r" *\n *", "\n", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @classmethod
    def _repair_verified_page_boundaries(
        cls,
        pages: list[KnowledgePage],
        *,
        intact_words: set[str],
    ) -> list[KnowledgePage]:
        repaired = list(pages)
        for index in range(len(repaired) - 1):
            previous = repaired[index]
            following = repaired[index + 1]
            previous_match = cls._PAGE_END_WORD_FRAGMENT_PATTERN.search(previous.content)
            following_match = cls._PAGE_START_WORD_FRAGMENT_PATTERN.search(following.content)
            if not previous_match or not following_match:
                continue

            joined = previous_match.group("left") + following_match.group("right")
            if joined.casefold() not in intact_words:
                continue

            punctuation = following_match.group("punctuation")
            previous_content = (previous.content[: previous_match.start()] + joined + punctuation).rstrip()
            following_content = following.content[following_match.end() :].lstrip()
            previous_blocks = cls._repair_boundary_blocks(
                previous.blocks,
                at_end=True,
                fragment_pattern=cls._PAGE_END_WORD_FRAGMENT_PATTERN,
                replacement=joined + punctuation,
            )
            following_blocks = cls._repair_boundary_blocks(
                following.blocks,
                at_end=False,
                fragment_pattern=cls._PAGE_START_WORD_FRAGMENT_PATTERN,
                replacement="",
            )
            repaired[index] = previous.model_copy(
                update={
                    "content": previous_content,
                    "blocks": previous_blocks,
                }
            )
            repaired[index + 1] = following.model_copy(
                update={
                    "content": following_content,
                    "blocks": following_blocks,
                }
            )
        return repaired

    @staticmethod
    def _repair_boundary_blocks(
        blocks: list,
        *,
        at_end: bool,
        fragment_pattern: re.Pattern[str],
        replacement: str,
    ) -> list:
        if not blocks:
            return blocks
        repaired = list(blocks)
        indexes = range(len(repaired) - 1, -1, -1) if at_end else range(len(repaired))
        for block_index in indexes:
            block = repaired[block_index]
            if block.kind != KnowledgeContentKind.TEXT:
                continue
            if at_end:
                content = fragment_pattern.sub(replacement, block.content)
            else:
                content = fragment_pattern.sub(replacement, block.content, count=1).lstrip()
            repaired[block_index] = block.model_copy(update={"content": content})
            break
        return repaired

    @classmethod
    def _find_repeated_edge_signatures(
        cls,
        pages: list[list[str]],
    ) -> set[str]:
        candidates: Counter[str] = Counter()
        for lines in pages:
            edge_lines = {cls._edge_signature(line) for line in lines[:2] + lines[-2:] if 8 <= len(line) <= 120}
            candidates.update(edge_lines)

        minimum_count = max(2, math.ceil(len(pages) * 0.5))
        return {signature for signature, count in candidates.items() if signature and count >= minimum_count}

    @staticmethod
    def _edge_signature(line: str) -> str:
        normalized = re.sub(r"\d+", "#", line.casefold())
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _repair_wrapped_latin_words(
        cls,
        content: str,
        intact_words: set[str],
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            left = match.group("left")
            right = match.group("right")
            joined = f"{left}{right}"
            if joined.casefold() in intact_words:
                return joined
            return f"{left}{match.group('hyphen')}{right}"

        return cls._WRAPPED_LATIN_WORD_PATTERN.sub(replace, content)

    @classmethod
    def _repair_split_latin_words(
        cls,
        content: str,
        intact_words: set[str],
    ) -> str:
        def replace(match: re.Match[str]) -> str:
            left = match.group("left")
            right = match.group("right")
            joined = f"{left}{right}"
            is_capitalized_split = len(left) == 1 and left.isupper() and len(joined) >= 5
            if (
                (len(joined) >= 6 or is_capitalized_split)
                and min(len(left), len(right)) <= 4
                and joined.casefold() in intact_words
            ):
                return joined
            return match.group(0)

        repaired = cls._SPLIT_LATIN_WORD_PATTERN.sub(replace, content)
        return cls._CAPITALIZED_SPLIT_LATIN_WORD_PATTERN.sub(
            replace,
            repaired,
        )
