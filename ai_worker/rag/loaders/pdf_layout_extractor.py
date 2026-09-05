import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgePageBlock,
    KnowledgeTableRow,
)

_SOURCE_TOKEN_PATTERN = re.compile(
    r"[A-Za-z가-힣]+|\d+(?:[.,]\d+)*|[%µμ㎍]+",
)
_SAME_AS_PATTERN = re.compile(r"(?i)\bsame\s+as\b")
_TOTAL_PATTERN = re.compile(r"(?i)^(?:total|합계)$")
_SIMPLE_NUMBER_PATTERN = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*$")
_TABLE_CAPTION_PATTERN = re.compile(
    r"(?i)\btable\s*(?:\d+|[IVXLCDM]+)\b",
)
_TABLE_CAPTION_LINE_PATTERN = re.compile(
    r"(?i)^\s*table\s*(?:\d+|[IVXLCDM]+)\b[.:]?\s*(?P<title>.*)$",
)
_TABLE_SUPER_HEADER_PATTERN = re.compile(
    r"(?i)^\s*(?:effect\s+on\s+nutrient(?:\s+status(?:\s+or\s+function)?)?|"
    r"human\s+studies|animal\s+studies|in\s+vitro\s+studies)\s*$",
)
_LOGICAL_ROW_ANCHOR_PATTERN = re.compile(r"^\s*\d+\b")
_PUBLICATION_SIDEBAR_PATTERN = re.compile(
    r"(?i)^\s*(?:Citation|Received|Revised|Accepted|Published|Copyright)\s*:",
)
_SCIENTIFIC_INTERACTION_HEADERS = [
    "Nutriment",
    "Effect on Nutrient Status or Function",
    "Number",
    "Study Design",
    "Number of Patients",
    "Dosage",
    "Result",
    "References",
]
_DUPLICATED_GLYPH_PATTERN = re.compile(r"(?i)([a-z])\1")
_SUSPICIOUS_SINGLE_LETTER_PATTERN = re.compile(r"\b(?!a\b|i\b)[a-z]\b")
_TABLE_HEADER_CELL_PATTERN = re.compile(
    r"(?i)\b(?:age|dose|weight|drug|class|effect|ingredient|result|"
    r"strength|color|shape|markings|hormone|ratio|potency|binding|"
    r"number|study|patients|dosage|nutriment|nutrient|references?|ndc|"
    r"group|cases|recommendation)\b"
)


@dataclass(frozen=True)
class PdfLayoutExtraction:
    blocks: list[KnowledgePageBlock]
    warnings: list[KnowledgeExtractionWarning]


@dataclass(frozen=True)
class _Line:
    content: str
    bbox: KnowledgeBoundingBox
    word_ids: tuple[int, ...]


class PdfLayoutExtractor:
    """PDF 단어·셀 좌표를 이용해 본문과 표를 안전하게 분리합니다."""

    _LINE_TOP_TOLERANCE = 3.0
    _BLOCK_GAP = 24.0
    _WORD_X_TOLERANCE = 1
    _WORD_Y_TOLERANCE = 3
    _DUPLICATE_LAYER_MIN_CHARACTERS = 50
    _DUPLICATE_LAYER_SIMILARITY = 0.55
    _TABLE_CONTEXT_MAX_GAP = 120.0
    _ROW_ANCHOR_TOLERANCE = 10.0
    _TEXT_TABLE_SETTINGS = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "min_words_vertical": 2,
        "min_words_horizontal": 2,
        "intersection_tolerance": 5,
    }
    _LINE_BOUNDED_TABLE_SETTINGS = {
        "vertical_strategy": "text",
        "horizontal_strategy": "lines",
        "min_words_vertical": 2,
        "intersection_tolerance": 5,
    }

    def extract(self, page: Any) -> PdfLayoutExtraction:
        page = self._remove_duplicate_text_layers(page)
        page = self._deduplicate_page(page)
        words = self._normalized_words(
            page.extract_words(
                return_chars=True,
                x_tolerance=self._WORD_X_TOLERANCE,
                y_tolerance=self._WORD_Y_TOLERANCE,
            )
            or []
        )
        page_text = " ".join(word["text"] for _, word in words)
        tables = [table for table in self._find_tables(page, page_text) if self._table_column_count(table) > 1]
        table_bboxes = [self._bbox(table.bbox) for table in tables]
        warnings: list[KnowledgeExtractionWarning] = []
        table_blocks = [
            self._build_table_block(
                table=table,
                bbox=table_bbox,
                words=words,
                warnings=warnings,
            )
            for table, table_bbox in zip(
                tables,
                table_bboxes,
                strict=True,
            )
        ]

        body_words = [
            item for item in words if not any(self._center_is_inside(item, table_bbox) for table_bbox in table_bboxes)
        ]
        text_blocks, reading_order_safe, is_multi_column = self._build_text_blocks(
            body_words,
            page_width=float(page.width),
        )
        text_blocks, table_blocks = self._separate_table_context(
            text_blocks=text_blocks,
            table_blocks=table_blocks,
        )
        if is_multi_column:
            warnings.append(KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT)
        has_merged_body_token = any(re.search(r"\S{120,}", block.content) for block in text_blocks)
        has_residual_duplicated_glyphs = any(
            len(_DUPLICATED_GLYPH_PATTERN.findall(line)) >= 5
            for block in text_blocks
            for line in block.content.splitlines()
        )
        has_fragmented_body_line = any(
            len(_SUSPICIOUS_SINGLE_LETTER_PATTERN.findall(line)) >= 3
            for block in text_blocks
            for line in block.content.splitlines()
        )
        if (
            not reading_order_safe
            or has_merged_body_token
            or has_residual_duplicated_glyphs
            or has_fragmented_body_line
        ):
            warnings.append(KnowledgeExtractionWarning.READING_ORDER_UNSAFE)

        blocks = list(text_blocks)
        for table_block in sorted(
            table_blocks,
            key=lambda block: (block.bbox.top, block.bbox.x0),
        ):
            insertion_index = next(
                (index for index, block in enumerate(blocks) if block.bbox.top > table_block.bbox.bottom),
                len(blocks),
            )
            blocks.insert(insertion_index, table_block)
        blocks = [block.model_copy(update={"order": order}) for order, block in enumerate(blocks)]
        return PdfLayoutExtraction(
            blocks=blocks,
            warnings=list(dict.fromkeys(warnings)),
        )

    def inherit_continued_table_headers(
        self,
        extraction: PdfLayoutExtraction,
        previous_headers: list[str] | None,
    ) -> PdfLayoutExtraction:
        if not previous_headers:
            return extraction
        blocks: list[KnowledgePageBlock] = []
        for block in extraction.blocks:
            has_placeholder = any(header.startswith("열 ") for header in block.headers)
            if (
                block.kind != KnowledgeContentKind.TABLE
                or not has_placeholder
                or block.column_count != len(previous_headers)
            ):
                blocks.append(block)
                continue
            source_rows = [row.cells for row in block.rows]
            serialized_rows = [self._serialize_row(previous_headers, row) for row in source_rows if any(row)]
            content = "\n".join(
                self._expand_row_references(
                    serialized_rows,
                    source_rows,
                )
            ).strip()
            blocks.append(
                block.model_copy(
                    update={
                        "headers": list(previous_headers),
                        "content": content or block.content,
                    }
                )
            )
        return PdfLayoutExtraction(
            blocks=blocks,
            warnings=extraction.warnings,
        )

    def _find_tables(self, page: Any, page_text: str) -> list[Any]:
        default_tables = page.find_tables() or []
        if not _TABLE_CAPTION_PATTERN.search(page_text):
            return default_tables

        if any(self._table_column_count(table) > 1 for table in default_tables):
            return default_tables

        text_tables = page.find_tables(self._TEXT_TABLE_SETTINGS) or []
        line_tables = page.find_tables(self._LINE_BOUNDED_TABLE_SETTINGS) or []
        if self._prefer_line_bounded_tables(
            line_tables=line_tables,
            text_tables=text_tables,
        ):
            return line_tables
        if not default_tables:
            return text_tables
        default_columns = max(
            (
                max(
                    (len(row) for row in (table.extract(x_tolerance=1) or [])),
                    default=0,
                )
                for table in default_tables
            ),
            default=0,
        )
        text_columns = max(
            (
                max(
                    (len(row) for row in (table.extract(x_tolerance=1) or [])),
                    default=0,
                )
                for table in text_tables
            ),
            default=0,
        )
        if default_columns <= 1 < text_columns:
            return text_tables
        return default_tables

    @staticmethod
    def _deduplicate_page(page: Any) -> Any:
        dedupe_chars = getattr(page, "dedupe_chars", None)
        if not callable(dedupe_chars):
            return page
        try:
            return dedupe_chars(
                tolerance=2,
                extra_attrs=(),
            )
        except TypeError:
            return dedupe_chars()

    @classmethod
    def _remove_duplicate_text_layers(cls, page: Any) -> Any:
        chars = getattr(page, "chars", None)
        page_filter = getattr(page, "filter", None)
        if not chars or not callable(page_filter):
            return page

        family_counts = Counter(family for char in chars for family in [cls._font_family(char)] if family)
        if len(family_counts) < 2:
            return page

        primary_family, primary_count = family_counts.most_common(1)[0]
        if primary_count < cls._DUPLICATE_LAYER_MIN_CHARACTERS:
            return page

        primary_text = cls._font_family_text(page, primary_family)
        if len(primary_text) < cls._DUPLICATE_LAYER_MIN_CHARACTERS:
            return page

        duplicate_families: set[str] = set()
        for family, count in family_counts.most_common()[1:]:
            if count < cls._DUPLICATE_LAYER_MIN_CHARACTERS:
                continue
            candidate_text = cls._font_family_text(page, family)
            if len(candidate_text) < cls._DUPLICATE_LAYER_MIN_CHARACTERS:
                continue
            similarity = SequenceMatcher(
                None,
                primary_text,
                candidate_text,
                autojunk=False,
            ).ratio()
            if similarity >= cls._DUPLICATE_LAYER_SIMILARITY:
                duplicate_families.add(family)

        if not duplicate_families:
            return page
        return page_filter(lambda item: cls._font_family(item) not in duplicate_families)

    @classmethod
    def _font_family_text(cls, page: Any, family: str) -> str:
        filtered_page = page.filter(lambda item: cls._font_family(item) == family)
        words = (
            filtered_page.extract_words(
                x_tolerance=cls._WORD_X_TOLERANCE,
                y_tolerance=cls._WORD_Y_TOLERANCE,
            )
            or []
        )
        content = "".join(str(word.get("text", "")) for word in words)
        return re.sub(r"[^A-Za-z0-9가-힣]", "", content).casefold()

    @staticmethod
    def _font_family(item: dict[str, Any]) -> str:
        font_name = str(item.get("fontname", ""))
        if not font_name:
            return ""
        family = font_name.split("+", 1)[-1].split(",", 1)[0]
        return re.sub(
            r"-(?:Bold|Italic|Ital|Roman|Roma|Regular|Medium).*$",
            "",
            family,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _table_column_count(table: Any) -> int:
        return max(
            (len(row) for row in (table.extract(x_tolerance=1) or []) if row is not None),
            default=0,
        )

    @staticmethod
    def _prefer_line_bounded_tables(
        *,
        line_tables: list[Any],
        text_tables: list[Any],
    ) -> bool:
        if not line_tables:
            return False
        if not text_tables:
            return True

        def dimensions(tables: list[Any]) -> tuple[int, int]:
            rows = [row for table in tables for row in (table.extract(x_tolerance=1) or []) if row is not None]
            return (
                max((len(row) for row in rows), default=0),
                len(rows),
            )

        line_columns, line_rows = dimensions(line_tables)
        text_columns, text_rows = dimensions(text_tables)
        return line_columns > 1 and line_columns >= text_columns and line_rows <= text_rows

    @staticmethod
    def _normalized_words(
        raw_words: list[dict[str, Any]],
    ) -> list[tuple[int, dict[str, Any]]]:
        normalized: list[tuple[int, dict[str, Any]]] = []
        for word_id, raw_word in enumerate(raw_words):
            text = PdfLayoutExtractor._restore_superscript_text(raw_word).strip()
            if not text:
                continue
            normalized.append(
                (
                    word_id,
                    {
                        "text": text,
                        "x0": float(raw_word["x0"]),
                        "top": float(raw_word["top"]),
                        "x1": float(raw_word["x1"]),
                        "bottom": float(raw_word["bottom"]),
                    },
                )
            )
        return normalized

    @staticmethod
    def _restore_superscript_text(raw_word: dict[str, Any]) -> str:
        text = str(raw_word.get("text", ""))
        chars = raw_word.get("chars")
        if not isinstance(chars, list) or len(chars) < 2:
            return text

        char_text = "".join(str(char.get("text", "")) for char in chars)
        if char_text != text:
            return text

        sizes = [float(char.get("size", 0.0)) for char in chars]
        base_size = max(sizes, default=0.0)
        if base_size <= 0:
            return text
        normal_tops = [
            float(char.get("top", 0.0)) for char, size in zip(chars, sizes, strict=True) if size >= base_size * 0.9
        ]
        if not normal_tops:
            return text
        base_top = sum(normal_tops) / len(normal_tops)

        restored: list[str] = []
        in_superscript = False
        for char, size in zip(chars, sizes, strict=True):
            glyph = str(char.get("text", ""))
            is_superscript = (
                glyph.isdigit() and size <= base_size * 0.85 and float(char.get("top", base_top)) <= base_top - 0.5
            )
            if is_superscript and not in_superscript:
                restored.append("^")
            restored.append(glyph)
            in_superscript = is_superscript
        return "".join(restored)

    @staticmethod
    def _bbox(values: Any) -> KnowledgeBoundingBox:
        x0, top, x1, bottom = values
        return KnowledgeBoundingBox(
            x0=float(x0),
            top=float(top),
            x1=float(x1),
            bottom=float(bottom),
        )

    @staticmethod
    def _center_is_inside(
        indexed_word: tuple[int, dict[str, Any]],
        bbox: KnowledgeBoundingBox,
    ) -> bool:
        _, word = indexed_word
        center_x = (word["x0"] + word["x1"]) / 2
        center_y = (word["top"] + word["bottom"]) / 2
        return bbox.x0 <= center_x <= bbox.x1 and bbox.top <= center_y <= bbox.bottom

    def _build_table_block(
        self,
        *,
        table: Any,
        bbox: KnowledgeBoundingBox,
        words: list[tuple[int, dict[str, Any]]],
        warnings: list[KnowledgeExtractionWarning],
    ) -> KnowledgePageBlock:
        raw_rows = [list(row or []) for row in (table.extract(x_tolerance=1) or [])]
        rows = [[self._normalize_cell(cell) for cell in row] for row in raw_rows if row is not None]
        validation_errors: list[str] = []
        table_super_headers: list[str] = []
        column_count = max((len(row) for row in rows), default=1)
        if not rows:
            validation_errors.append("EMPTY_TABLE")
            headers = ["열 1"]
            body_rows: list[list[str]] = []
        else:
            if any(len(row) != column_count for row in rows):
                validation_errors.append("COLUMN_COUNT_MISMATCH")
            rows = [[*row, *([""] * (column_count - len(row)))] for row in rows]
            headers, data_rows, raw_data_rows, table_super_headers = self._prepare_table_rows(
                rows=rows,
                raw_rows=raw_rows,
                column_count=column_count,
            )
            restored_rows = self._restore_scientific_merged_rows(
                table=table,
                raw_rows=[headers, *raw_data_rows],
                words=words,
                headers=headers,
            )
            if restored_rows is not None:
                normalized_restored = [[self._normalize_cell(cell) for cell in row] for row in restored_rows]
                normalized_restored = [[*row, *([""] * (column_count - len(row)))] for row in normalized_restored]
                data_rows = normalized_restored[1:]
                raw_data_rows = restored_rows[1:]
            if any(self._has_multiple_primary_entities(row[0]) for row in raw_data_rows if row):
                validation_errors.append("MULTI_ENTITY_ROW")
            body_rows = self._inherit_primary_entity(data_rows)

        serialized_rows = [self._serialize_row(headers, row) for row in body_rows if any(row)]
        serialized_rows = self._expand_row_references(
            serialized_rows,
            body_rows,
        )
        content = "\n".join(serialized_rows).strip()
        if not content:
            content = self._serialize_row(headers, rows[0] if rows else [""])

        table_words = [
            word["text"]
            for indexed_word in words
            if self._center_is_inside(indexed_word, bbox)
            for word in [indexed_word[1]]
        ]
        if table_words and not self._tokens_are_preserved(
            source=" ".join(table_words),
            rendered=" ".join([*table_super_headers, *headers, content]),
        ):
            validation_errors.append("SOURCE_TOKEN_LOSS")
        if not self._totals_are_consistent(body_rows):
            validation_errors.append("TOTAL_MISMATCH")
        if validation_errors:
            warnings.append(KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE)

        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=bbox,
            content=content,
            headers=headers,
            rows=[KnowledgeTableRow(cells=row) for row in body_rows],
            column_count=column_count,
            table_super_headers=table_super_headers,
            validation_errors=list(dict.fromkeys(validation_errors)),
        )

    def _prepare_table_rows(
        self,
        *,
        rows: list[list[str]],
        raw_rows: list[list[Any]],
        column_count: int,
    ) -> tuple[list[str], list[list[str]], list[list[Any]], list[str]]:
        leading_context_count = 0
        table_super_headers: list[str] = []
        while (
            leading_context_count + 1 < len(rows)
            and sum(bool(cell) for cell in rows[leading_context_count]) == 1
            and self._looks_like_table_header(rows[leading_context_count + 1])
        ):
            table_super_headers.extend(cell for cell in rows[leading_context_count] if cell)
            leading_context_count += 1

        table_rows = rows[leading_context_count:]
        raw_table_rows = raw_rows[leading_context_count:]
        if table_rows and self._looks_like_table_header(table_rows[0]):
            return (
                self._headers(table_rows[0], column_count),
                table_rows[1:],
                raw_table_rows[1:],
                table_super_headers,
            )
        return (
            [f"열 {index + 1}" for index in range(column_count)],
            table_rows,
            raw_table_rows,
            table_super_headers,
        )

    @staticmethod
    def _looks_like_table_header(row: list[str]) -> bool:
        nonempty = [cell.strip() for cell in row if cell.strip()]
        if len(nonempty) < 2:
            return False
        return sum(bool(_TABLE_HEADER_CELL_PATTERN.search(cell)) for cell in nonempty) >= min(2, len(nonempty))

    @staticmethod
    def _is_scientific_interaction_table(headers: list[str]) -> bool:
        return headers == _SCIENTIFIC_INTERACTION_HEADERS

    def _restore_scientific_merged_rows(
        self,
        *,
        table: Any,
        raw_rows: list[list[Any]],
        words: list[tuple[int, dict[str, Any]]],
        headers: list[str],
    ) -> list[list[str]] | None:
        if not self._is_scientific_interaction_table(headers):
            return None
        row_objects = list(getattr(table, "rows", ()) or ())
        if len(row_objects) != len(raw_rows):
            return None

        restored: list[list[str]] = [[self._normalize_cell(cell) for cell in raw_rows[0]]]
        changed = False
        for row_index, row in enumerate(raw_rows[1:], start=1):
            if not row or not self._has_multiple_primary_entities(row[0]):
                restored.append([self._normalize_cell(cell) for cell in row])
                continue
            split_rows = self._restore_scientific_merged_row(
                row_object=row_objects[row_index],
                words=words,
                column_count=len(headers),
            )
            if not split_rows:
                restored.append([self._normalize_cell(cell) for cell in row])
                continue
            restored.extend(split_rows)
            changed = True
        return restored if changed else None

    def _restore_scientific_merged_row(
        self,
        *,
        row_object: Any,
        words: list[tuple[int, dict[str, Any]]],
        column_count: int,
    ) -> list[list[str]] | None:
        raw_cells = list(getattr(row_object, "cells", ()) or ())
        if len(raw_cells) != column_count or any(cell is None for cell in raw_cells):
            return None
        cell_lines = [self._lines_inside_bbox(words, self._bbox(cell)) for cell in raw_cells]
        primary_lines = cell_lines[0]
        anchor_lines = [line for line in cell_lines[2] if _LOGICAL_ROW_ANCHOR_PATTERN.match(line.content)]
        if len(primary_lines) < 2 or len(anchor_lines) < 2:
            return None

        anchor_centers = [self._line_center(line) for line in anchor_lines]
        primary_centers = [self._line_center(line) for line in primary_lines]
        rows = [[""] * column_count for _ in anchor_centers]
        for row_index, anchor_center in enumerate(anchor_centers):
            primary_index = min(
                range(len(primary_lines)),
                key=lambda index: abs(primary_centers[index] - anchor_center),
            )
            rows[row_index][0] = primary_lines[primary_index].content

        for column_index, lines in enumerate(cell_lines[1:], start=1):
            segments = self._segment_cell_lines(
                lines=lines,
                anchor_centers=anchor_centers,
            )
            for row_index, segment in enumerate(segments):
                rows[row_index][column_index] = segment
        return rows

    def _lines_inside_bbox(
        self,
        words: list[tuple[int, dict[str, Any]]],
        bbox: KnowledgeBoundingBox,
    ) -> list[_Line]:
        inside = [item for item in words if self._center_is_inside(item, bbox)]
        if not inside:
            return []
        rows: list[list[tuple[int, dict[str, Any]]]] = []
        for indexed_word in sorted(
            inside,
            key=lambda item: (item[1]["top"], item[1]["x0"]),
        ):
            if not rows or abs(rows[-1][0][1]["top"] - indexed_word[1]["top"]) > self._LINE_TOP_TOLERANCE:
                rows.append([indexed_word])
            else:
                rows[-1].append(indexed_word)
        return [
            _Line(
                content=" ".join(item[1]["text"] for item in sorted(row, key=lambda item: item[1]["x0"])),
                bbox=KnowledgeBoundingBox(
                    x0=min(item[1]["x0"] for item in row),
                    top=min(item[1]["top"] for item in row),
                    x1=max(item[1]["x1"] for item in row),
                    bottom=max(item[1]["bottom"] for item in row),
                ),
                word_ids=tuple(item[0] for item in row),
            )
            for row in rows
        ]

    @staticmethod
    def _line_center(line: _Line) -> float:
        return (line.bbox.top + line.bbox.bottom) / 2

    def _segment_cell_lines(
        self,
        *,
        lines: list[_Line],
        anchor_centers: list[float],
    ) -> list[str]:
        if not lines:
            return [""] * len(anchor_centers)
        line_centers = [self._line_center(line) for line in lines]
        starts: dict[int, int] = {}
        minimum_line_index = 0
        for row_index, anchor_center in enumerate(anchor_centers):
            candidates = [
                index
                for index in range(minimum_line_index, len(lines))
                if abs(line_centers[index] - anchor_center) <= self._ROW_ANCHOR_TOLERANCE
            ]
            if not candidates:
                continue
            selected = min(
                candidates,
                key=lambda index: abs(line_centers[index] - anchor_center),
            )
            starts[row_index] = selected
            minimum_line_index = selected + 1

        if not starts:
            return [""] * len(anchor_centers)
        segments = [""] * len(anchor_centers)
        selected_rows = sorted(starts)
        for selected_index, row_index in enumerate(selected_rows):
            start = starts[row_index]
            if selected_index == 0:
                start = 0
            end = starts[selected_rows[selected_index + 1]] if selected_index + 1 < len(selected_rows) else len(lines)
            segments[row_index] = " ".join(line.content for line in lines[start:end]).strip()
        return segments

    def _separate_table_context(
        self,
        *,
        text_blocks: list[KnowledgePageBlock],
        table_blocks: list[KnowledgePageBlock],
    ) -> tuple[list[KnowledgePageBlock], list[KnowledgePageBlock]]:
        updated_text_blocks = list(text_blocks)
        updated_table_blocks: list[KnowledgePageBlock] = []
        for table_block in table_blocks:
            table_title: str | None = None
            super_headers: list[str] = list(table_block.table_super_headers)
            block_updates: dict[int, list[str]] = {}
            for block_index, block in enumerate(updated_text_blocks):
                gap = table_block.bbox.top - block.bbox.bottom
                if gap < -self._LINE_TOP_TOLERANCE or gap > self._TABLE_CONTEXT_MAX_GAP:
                    continue
                retained_lines, candidate_title, candidate_headers = self._extract_table_context_lines(block.content)
                if candidate_title:
                    table_title = candidate_title
                super_headers.extend(candidate_headers)
                block_updates[block_index] = retained_lines

            rebuilt_text_blocks: list[KnowledgePageBlock] = []
            for block_index, block in enumerate(updated_text_blocks):
                if block_index not in block_updates:
                    rebuilt_text_blocks.append(block)
                    continue
                content = "\n".join(block_updates[block_index]).strip()
                if content:
                    rebuilt_text_blocks.append(block.model_copy(update={"content": content}))
            updated_text_blocks = rebuilt_text_blocks
            updated_table_blocks.append(
                table_block.model_copy(
                    update={
                        "table_title": table_title,
                        "table_super_headers": list(dict.fromkeys(super_headers)),
                    }
                )
            )
        return updated_text_blocks, updated_table_blocks

    @staticmethod
    def _extract_table_context_lines(
        content: str,
    ) -> tuple[list[str], str | None, list[str]]:
        retained_lines: list[str] = []
        table_title: str | None = None
        super_headers: list[str] = []
        for line in content.splitlines():
            normalized = re.sub(r"\s+", " ", line).strip()
            caption_match = _TABLE_CAPTION_LINE_PATTERN.match(normalized)
            if caption_match:
                table_title = caption_match.group("title").strip(" .:-") or None
            elif _TABLE_SUPER_HEADER_PATTERN.match(normalized):
                super_headers.append(normalized)
            else:
                retained_lines.append(line)
        return retained_lines, table_title, super_headers

    @staticmethod
    def _normalize_cell(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _has_multiple_primary_entities(value: Any) -> bool:
        lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
        if len(lines) < 2:
            return False
        return not (lines[0].endswith(("/", "-", "–", "—", "and")) or lines[1].startswith(("(", "/")))

    @staticmethod
    def _inherit_primary_entity(rows: list[list[str]]) -> list[list[str]]:
        inherited: list[list[str]] = []
        previous_primary = ""
        for row in rows:
            current = list(row)
            if current and current[0]:
                previous_primary = current[0]
            elif current and previous_primary:
                current[0] = previous_primary
            inherited.append(current)
        return inherited

    @staticmethod
    def _headers(first_row: list[str], column_count: int) -> list[str]:
        header_signature = " ".join(first_row).casefold()
        if column_count == len(_SCIENTIFIC_INTERACTION_HEADERS) and all(
            marker in header_signature
            for marker in (
                "number",
                "study design",
                "patients",
                "dosage",
            )
        ):
            return list(_SCIENTIFIC_INTERACTION_HEADERS)
        seen: Counter[str] = Counter()
        headers: list[str] = []
        for index in range(column_count):
            base = first_row[index].strip() or f"열 {index + 1}"
            seen[base] += 1
            headers.append(base if seen[base] == 1 else f"{base} {seen[base]}")
        return headers

    @staticmethod
    def _serialize_row(headers: list[str], row: list[str]) -> str:
        return " | ".join(f"{header}={cell}" for header, cell in zip(headers, row, strict=True) if cell)

    @staticmethod
    def _expand_row_references(
        serialized_rows: list[str],
        source_rows: list[list[str]],
    ) -> list[str]:
        expanded: list[str] = []
        serialized_index = 0
        previous_serialized: str | None = None
        for row in source_rows:
            if not any(row):
                continue
            serialized = serialized_rows[serialized_index]
            serialized_index += 1
            if previous_serialized and any(_SAME_AS_PATTERN.search(cell) for cell in row):
                serialized = f"{serialized} | 참조 행: {previous_serialized}"
            expanded.append(serialized)
            previous_serialized = serialized_rows[serialized_index - 1]
        return expanded

    @staticmethod
    def _tokens_are_preserved(*, source: str, rendered: str) -> bool:
        source_tokens = Counter(token.casefold() for token in _SOURCE_TOKEN_PATTERN.findall(source))
        rendered_tokens = Counter(token.casefold() for token in _SOURCE_TOKEN_PATTERN.findall(rendered))
        return all(rendered_tokens[token] >= count for token, count in source_tokens.items())

    @staticmethod
    def _totals_are_consistent(rows: list[list[str]]) -> bool:
        for total_index, row in enumerate(rows):
            if not row or not _TOTAL_PATTERN.fullmatch(row[0].strip()):
                continue
            preceding = rows[:total_index]
            for column_index in range(1, len(row)):
                total_match = _SIMPLE_NUMBER_PATTERN.fullmatch(row[column_index].replace(",", ""))
                values = [
                    _SIMPLE_NUMBER_PATTERN.fullmatch(candidate[column_index].replace(",", ""))
                    for candidate in preceding
                    if len(candidate) > column_index
                ]
                if not total_match or not values or any(value is None for value in values):
                    continue
                expected = sum(float(value.group(1)) for value in values if value)
                if abs(expected - float(total_match.group(1))) > 1e-6:
                    return False
        return True

    def _build_text_blocks(
        self,
        words: list[tuple[int, dict[str, Any]]],
        *,
        page_width: float,
    ) -> tuple[list[KnowledgePageBlock], bool, bool]:
        if not words:
            return [], True, False
        lines = self._cluster_lines(
            words,
            page_width=page_width,
        )
        midpoint = page_width / 2
        lines, excluded_word_ids = self._exclude_publication_sidebar(
            lines,
            midpoint=midpoint,
        )
        left_lines = [line for line in lines if line.bbox.x1 <= midpoint]
        right_lines = [line for line in lines if line.bbox.x0 >= midpoint]
        crossing_lines = [line for line in lines if line not in left_lines and line not in right_lines]

        column_top = 0.0
        column_bottom = 0.0
        if left_lines and right_lines:
            column_top = max(
                min(line.bbox.top for line in left_lines),
                min(line.bbox.top for line in right_lines),
            )
            column_bottom = min(
                max(line.bbox.bottom for line in left_lines),
                max(line.bbox.bottom for line in right_lines),
            )
        is_multi_column = bool(left_lines and right_lines and column_bottom > column_top)
        if not is_multi_column:
            grouped_lines = self._group_lines(lines)
        else:
            # 다단 자체는 오류가 아니지만 수동 검수 위치를 남긴다.
            top_lines = [line for line in lines if line.bbox.bottom < column_top]
            bottom_lines = [line for line in lines if line.bbox.top > column_bottom]
            body_left = [line for line in left_lines if line not in top_lines and line not in bottom_lines]
            body_right = [line for line in right_lines if line not in top_lines and line not in bottom_lines]
            middle_crossing = [line for line in crossing_lines if line not in top_lines and line not in bottom_lines]
            grouped_lines = [
                *self._group_lines(top_lines),
                *self._group_lines(body_left),
                *self._group_lines(body_right),
                *self._group_lines(middle_crossing),
                *self._group_lines(bottom_lines),
            ]

        assigned_ids = [word_id for group in grouped_lines for line in group for word_id in line.word_ids]
        source_ids = [word_id for word_id, _ in words if word_id not in excluded_word_ids]
        reading_order_safe = Counter(assigned_ids) == Counter(source_ids)
        blocks = [self._text_block(group) for group in grouped_lines if group]
        return blocks, reading_order_safe, is_multi_column

    @staticmethod
    def _exclude_publication_sidebar(
        lines: list[_Line],
        *,
        midpoint: float,
    ) -> tuple[list[_Line], set[int]]:
        starts = [
            line
            for line in lines
            if _PUBLICATION_SIDEBAR_PATTERN.search(line.content)
            and (line.bbox.x1 <= midpoint or line.bbox.x0 >= midpoint)
        ]
        if not starts:
            return lines, set()

        excluded: set[int] = set()
        for start in starts:
            on_left = start.bbox.x1 <= midpoint
            for line in lines:
                same_side = line.bbox.x1 <= midpoint if on_left else line.bbox.x0 >= midpoint
                aligned_with_sidebar = (
                    line.bbox.x0 <= start.bbox.x0 + 36 if on_left else line.bbox.x1 >= start.bbox.x1 - 36
                )
                if same_side and aligned_with_sidebar and line.bbox.top >= start.bbox.top:
                    excluded.update(line.word_ids)
        return (
            [line for line in lines if not set(line.word_ids).intersection(excluded)],
            excluded,
        )

    def _cluster_lines(
        self,
        words: list[tuple[int, dict[str, Any]]],
        *,
        page_width: float,
    ) -> list[_Line]:
        rows: list[list[tuple[int, dict[str, Any]]]] = []
        for indexed_word in sorted(
            words,
            key=lambda item: (item[1]["top"], item[1]["x0"]),
        ):
            _, word = indexed_word
            if not rows or abs(rows[-1][0][1]["top"] - word["top"]) > self._LINE_TOP_TOLERANCE:
                rows.append([indexed_word])
            else:
                rows[-1].append(indexed_word)

        split_rows: list[list[tuple[int, dict[str, Any]]]] = []
        horizontal_gap = max(28.0, page_width * 0.07)
        for row in rows:
            current: list[tuple[int, dict[str, Any]]] = []
            for indexed_word in sorted(
                row,
                key=lambda item: item[1]["x0"],
            ):
                if current and indexed_word[1]["x0"] - current[-1][1]["x1"] > horizontal_gap:
                    split_rows.append(current)
                    current = []
                current.append(indexed_word)
            if current:
                split_rows.append(current)

        return [
            _Line(
                content=" ".join(item[1]["text"] for item in sorted(row, key=lambda item: item[1]["x0"])),
                bbox=KnowledgeBoundingBox(
                    x0=min(item[1]["x0"] for item in row),
                    top=min(item[1]["top"] for item in row),
                    x1=max(item[1]["x1"] for item in row),
                    bottom=max(item[1]["bottom"] for item in row),
                ),
                word_ids=tuple(item[0] for item in row),
            )
            for row in split_rows
        ]

    def _group_lines(self, lines: list[_Line]) -> list[list[_Line]]:
        groups: list[list[_Line]] = []
        for line in sorted(lines, key=lambda item: (item.bbox.top, item.bbox.x0)):
            if not groups or line.bbox.top - groups[-1][-1].bbox.bottom > self._BLOCK_GAP:
                groups.append([line])
            else:
                groups[-1].append(line)
        return groups

    @staticmethod
    def _text_block(lines: list[_Line]) -> KnowledgePageBlock:
        return KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=0,
            bbox=KnowledgeBoundingBox(
                x0=min(line.bbox.x0 for line in lines),
                top=min(line.bbox.top for line in lines),
                x1=max(line.bbox.x1 for line in lines),
                bottom=max(line.bbox.bottom for line in lines),
            ),
            content="\n".join(line.content for line in lines),
        )
