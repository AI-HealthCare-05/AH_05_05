import re
from collections.abc import Iterator
from dataclasses import dataclass

from ai_worker.schemas.knowledge import (
    KnowledgePage,
    KnowledgeSection,
    KnowledgeSectionType,
)


@dataclass(frozen=True)
class SupplementCodeField:
    section_type: KnowledgeSectionType
    title: str
    hierarchy: str
    patterns: tuple[str, ...]
    reference_path: tuple[str, str] | None = None


_FIELDS = (
    SupplementCodeField(
        section_type=KnowledgeSectionType.INGREDIENT,
        title="원료",
        hierarchy="제조기준 > 원료",
        patterns=(
            r"원료\s*\(\s*1\s*\)",
            r"\(\s*1\s*\)\s*원료",
            r"원료",
        ),
        reference_path=("1", "1"),
    ),
    SupplementCodeField(
        section_type=KnowledgeSectionType.STANDARD,
        title="규격",
        hierarchy="규격",
        patterns=(
            r"규격\s*2\s*\)",
            r"2\s*\)\s*규격",
            r"규격",
        ),
    ),
    SupplementCodeField(
        section_type=KnowledgeSectionType.FUNCTION,
        title="기능성 내용",
        hierarchy="제품의 요건 > 기능성 내용",
        patterns=(
            r"기능성\s*내용\s*\(\s*1\s*\)",
            r"\(\s*1\s*\)\s*기능성\s*내용",
            r"기능성\s*내용",
        ),
        reference_path=("3", "1"),
    ),
    SupplementCodeField(
        section_type=KnowledgeSectionType.DAILY_INTAKE,
        title="일일섭취량",
        hierarchy="제품의 요건 > 일일섭취량",
        patterns=(
            r"일일섭취량\s*\(\s*2\s*\)",
            r"\(\s*2\s*\)\s*일일섭취량",
            r"일일섭취량",
        ),
    ),
    SupplementCodeField(
        section_type=KnowledgeSectionType.CAUTION,
        title="섭취 시 주의사항",
        hierarchy="제품의 요건 > 섭취 시 주의사항",
        patterns=(
            r"섭취\s*시\s*주의사항\s*\(\s*3\s*\)",
            r"\(\s*3\s*\)\s*섭취\s*시\s*주의사항",
            r"섭취\s*시\s*주의사항",
        ),
    ),
    SupplementCodeField(
        section_type=KnowledgeSectionType.TEST_METHOD,
        title="시험법",
        hierarchy="시험법",
        patterns=(
            r"시험법\s*4\s*\)",
            r"4\s*\)\s*시험법",
            r"시험법",
        ),
    ),
)

_PARENT_MARKER = re.compile(
    r"(?m)^\s*(?:제조기준\s*1\s*\)|1\s*\)\s*제조기준|"
    r"제품의\s*요건\s*3\s*\)|3\s*\)\s*제품의\s*요건)\s*$"
)
_LETTER_ITEM = re.compile(
    r"(?ms)^\s*(?:\(\s*(?P<bracket>[가-하])\s*\)|"
    r"(?P<plain>[가-하])(?:\s*\(\s*\))?\s+)"
    r"(?P<body>.*?)"
    r"(?=^\s*(?:\(\s*[가-하]\s*\)|[가-하](?:\s*\(\s*\))?\s+)|\Z)"
)
SUPPLEMENT_REFERENCE_PATTERN = re.compile(
    r"(?P<top>\d+)\s*\)\s*\.?\s*"
    r"\(\s*(?P<sub>\d+)\s*\)\s*\.?\s*"
    r"\(\s*(?P<first>[가-하])\s*\)"
    r"(?P<tail>(?:\s*및\s*\(\s*[가-하]\s*\))*)"
)
_DISPLACED_MICROGRAM_RAE = re.compile(
    r"(?P<amount>\d[\d,.]*\s*~\s*\d[\d,.]*)\s+g\s+RAE\s*"
    r"\((?P<iu_min>[\d,.]+)\s*μ\s*~"
)


def iter_supplement_reference_keys(
    content: str,
) -> Iterator[tuple[str, str, str]]:
    for match in SUPPLEMENT_REFERENCE_PATTERN.finditer(content):
        yield (
            match.group("top"),
            match.group("sub"),
            match.group("first"),
        )
        for letter in re.findall(
            r"\(\s*([가-하])\s*\)",
            match.group("tail"),
        ):
            yield match.group("top"), match.group("sub"), letter


class SupplementCodeParser:
    """공전의 번호 계층을 독립 검색 가능한 근거 청크로 복원합니다."""

    def parse(
        self,
        pages: list[KnowledgePage],
    ) -> tuple[list[KnowledgeSection], list[tuple[int, int, int]]]:
        combined, page_ranges = self._combine_pages(pages)
        matches = self._find_field_matches(combined)
        if not matches:
            return [], page_ranges

        ingredient_name = self._ingredient_name(pages[0])
        raw_sections: list[tuple[SupplementCodeField, str, int, int]] = []
        for index, (start, heading_end, field) in enumerate(matches):
            end = matches[index + 1][0] if index + 1 < len(matches) else len(combined)
            raw_body = combined[heading_end:end]
            source_end = end
            for parent_match in _PARENT_MARKER.finditer(raw_body):
                if not raw_body[parent_match.end() :].strip():
                    source_end = heading_end + parent_match.start()
                    break
            body = self._normalize_extraction_artifacts(_PARENT_MARKER.sub("", raw_body).strip())
            if field.section_type == KnowledgeSectionType.STANDARD:
                body = self._normalize_standard_items(
                    body,
                    ingredient_name,
                )
            if body:
                raw_sections.append((field, body, start, source_end))

        references = self._build_reference_map(raw_sections)
        sections: list[KnowledgeSection] = []
        for field, body, start, end in raw_sections:
            normalized_body = re.sub(
                r"^\s*:\s*",
                "",
                body,
            )
            resolved_references = self._resolve_references(
                normalized_body,
                references,
            )
            content_parts = [
                f"성분: {ingredient_name}",
                f"분류: {field.hierarchy}",
                (
                    f"{field.title}:\n{normalized_body}"
                    if "\n" in normalized_body
                    else f"{field.title}: {normalized_body}"
                ),
            ]
            if resolved_references:
                content_parts.extend(["참조 내용:", *resolved_references])
            page_start, page_end = self._page_range_for(
                start,
                end,
                page_ranges,
            )
            sections.append(
                KnowledgeSection(
                    content="\n".join(content_parts),
                    section_type=field.section_type,
                    section_title=field.hierarchy,
                    page_start=page_start,
                    page_end=page_end,
                    source_start=start,
                    source_end=end,
                )
            )
        return sections, page_ranges

    @staticmethod
    def _find_field_matches(
        content: str,
    ) -> list[tuple[int, int, SupplementCodeField]]:
        matches: list[tuple[int, int, SupplementCodeField]] = []
        for field in _FIELDS:
            field_matches = []
            for pattern in field.patterns:
                field_matches = list(
                    re.finditer(
                        rf"(?m)^\s*(?:{pattern})(?=\s|:|$)",
                        content,
                        flags=re.IGNORECASE,
                    )
                )
                if field_matches:
                    break
            matches.extend((match.start(), match.end(), field) for match in field_matches)

        selected: list[tuple[int, int, SupplementCodeField]] = []
        for candidate in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
            if selected and candidate[0] < selected[-1][1]:
                continue
            selected.append(candidate)
        return selected

    def _build_reference_map(
        self,
        raw_sections: list[tuple[SupplementCodeField, str, int, int]],
    ) -> dict[tuple[str, str, str], str]:
        references: dict[tuple[str, str, str], str] = {}
        for field, body, _, _ in raw_sections:
            if field.reference_path is None:
                continue
            top, subsection = field.reference_path
            for match in _LETTER_ITEM.finditer(body):
                label = match.group("bracket") or match.group("plain")
                item_body = match.group("body")
                item_body = " ".join(item_body.split())
                if item_body:
                    references[(top, subsection, label)] = item_body
        return references

    @staticmethod
    def _resolve_references(
        content: str,
        references: dict[tuple[str, str, str], str],
    ) -> list[str]:
        resolved: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        for key in iter_supplement_reference_keys(content):
            if key in seen or key not in references:
                continue
            seen.add(key)
            resolved.append(f"- {key[0]}) > ({key[1]}) > ({key[2]}): {references[key]}")
        return resolved

    @staticmethod
    def _normalize_extraction_artifacts(content: str) -> str:
        normalized = _DISPLACED_MICROGRAM_RAE.sub(
            lambda match: (f"{match.group('amount')} μg RAE ({match.group('iu_min')} ~"),
            content,
        )
        normalized = re.sub(r"\bB\s+(\d+)\b", r"B\1", normalized)
        normalized = re.sub(r"\(\s*\)", "", normalized)
        normalized = re.sub(
            r"(?<!\()(?P<english>[A-Za-z][A-Za-z]*"
            r"(?:\s+[A-Za-z][A-Za-z]*)+)\)\(",
            r"(\g<english>)",
            normalized,
        )
        normalized = normalized.replace("・", "·")
        normalized = re.sub(r"\s*·\s*", "·", normalized)
        normalized = re.sub(r"[ \t]+([,;:])", r"\1", normalized)
        normalized = re.sub(
            r"섭취를\s*,\s*(?:\n\s*)?중단",
            "섭취를 중단",
            normalized,
        )
        normalized = re.sub(
            r"(?m)^\s*([가-하])\s*\(\s*\)\s*",
            r"(\1) ",
            normalized,
        )
        normalized = re.sub(
            r"(?m)^\s*([가-하])\s+",
            r"(\1) ",
            normalized,
        )
        return "\n".join(line.rstrip() for line in normalized.splitlines() if line.strip()).strip()

    @classmethod
    def _normalize_standard_items(
        cls,
        content: str,
        ingredient_name: str,
    ) -> str:
        item_pattern = re.compile(r"\(\s*(?P<number>\d+)\s*\)")
        items: list[tuple[str, list[str]]] = []
        preamble: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = item_pattern.search(stripped)
            if match:
                before = stripped[: match.start()].strip()
                after = stripped[match.end() :].strip()
                item_content = " ".join(part for part in (before, after) if part)
                items.append((match.group("number"), [item_content]))
            elif items:
                items[-1][1].append(stripped)
            else:
                preamble.append(stripped)

        if not items:
            return content

        rendered = list(preamble)
        rendered.extend(
            cls._render_standard_item(
                number,
                " ".join(parts),
                ingredient_name,
            )
            for number, parts in items
        )
        return "\n".join(rendered)

    @staticmethod
    def _render_standard_item(
        number: str,
        content: str,
        ingredient_name: str,
    ) -> str:
        normalized = " ".join(content.split()).strip(" :")
        if normalized.startswith("성상"):
            body = normalized.removeprefix("성상").strip(" :")
            body = re.sub(r"이미\s*:\s*·\s*이취", "이미·이취", body)
            return f"({number}) 성상: {body}"

        if "표시량의" in normalized:
            body = normalized[normalized.index("표시량의") :]
            range_match = re.search(
                r"\d[\d,.]*\s*~\s*\d[\d,.]*\s*%",
                body,
            )
            if range_match:
                body = f"표시량의 {range_match.group()}"
            else:
                body = re.sub(r"표시량의\s*:\s*", "표시량의 ", body)
            return f"({number}) {ingredient_name}: {body}"

        if normalized.startswith("대장균군"):
            body = normalized.removeprefix("대장균군").strip(" :")
            return f"({number}) 대장균군: {body}"

        return f"({number}) {normalized}"

    @staticmethod
    def _ingredient_name(page: KnowledgePage) -> str:
        if page.metadata.ingredient_names:
            return page.metadata.ingredient_names[0]
        return page.metadata.title

    @staticmethod
    def _combine_pages(
        pages: list[KnowledgePage],
    ) -> tuple[str, list[tuple[int, int, int]]]:
        parts: list[str] = []
        ranges: list[tuple[int, int, int]] = []
        offset = 0
        for page in pages:
            if parts:
                parts.append("\n\n")
                offset += 2
            start = offset
            parts.append(page.content)
            offset += len(page.content)
            ranges.append((start, offset, page.page_number))
        return "".join(parts), ranges

    @staticmethod
    def _page_range_for(
        start: int,
        end: int,
        page_ranges: list[tuple[int, int, int]],
    ) -> tuple[int, int]:
        pages = [
            page_number for page_start, page_end, page_number in page_ranges if start < page_end and end > page_start
        ]
        if not pages:
            return page_ranges[0][2], page_ranges[-1][2]
        return min(pages), max(pages)
