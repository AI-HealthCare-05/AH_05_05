import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.metadata.knowledge_entity_extractor import (
    KnowledgeEntityExtractor,
)
from ai_worker.rag.parsers.supplement_code_parser import (
    SupplementCodeParser,
)
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgePage,
    KnowledgeSection,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class WordTokenCounter:
    """테스트와 오프라인 규칙 검증에 사용하는 단순 카운터입니다."""

    def count(self, text: str) -> int:
        return len(text.split())


class TiktokenTokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


@dataclass(frozen=True)
class ChunkingPolicy:
    target_min_tokens: int
    hard_max_tokens: int
    overlap_tokens: int


_POLICIES = {
    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE: ChunkingPolicy(150, 450, 0),
    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE: ChunkingPolicy(250, 600, 40),
    KnowledgeDocumentType.SUPPLEMENT_CODE: ChunkingPolicy(200, 500, 0),
    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA: ChunkingPolicy(250, 600, 50),
    KnowledgeDocumentType.ADVERSE_CASE_REPORT: ChunkingPolicy(300, 700, 0),
    KnowledgeDocumentType.PHARM_REVIEW: ChunkingPolicy(400, 750, 80),
    KnowledgeDocumentType.RESEARCH_ARTICLE: ChunkingPolicy(400, 800, 100),
    KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH: ChunkingPolicy(150, 450, 0),
}


_INTERACTION_LABELS = {
    "DRUG_DRUG": "약-약",
    "DRUG_SUPPLEMENT": "약-영양제",
    "SUPPLEMENT_SUPPLEMENT": "영양제-영양제",
    "DRUG_FOOD": "약-음식",
}

_EVIDENCE_LABELS = {
    "REGULATORY": "공인 규정·가이드",
    "SYSTEMATIC_REVIEW": "체계적 문헌고찰",
    "REVIEW_ARTICLE": "종설",
    "CLINICAL_STUDY": "임상시험",
    "OBSERVATIONAL_STUDY": "관찰연구",
    "CASE_REPORT": "사례보고",
    "PRECLINICAL": "전임상 연구",
}

_POPULATION_LABELS = {
    "HUMAN": "사람",
    "ANIMAL": "동물",
    "CELL": "세포",
    "MIXED": "혼합",
    "NOT_APPLICABLE": "해당 없음",
}


_COMMON_CAUTION_HEADINGS = {
    "섭취 시 주의사항": KnowledgeSectionType.CAUTION,
    "사용상의 주의사항": KnowledgeSectionType.CAUTION,
    "주의사항": KnowledgeSectionType.CAUTION,
    "부작용": KnowledgeSectionType.ADVERSE_EVENT,
    "상호작용": KnowledgeSectionType.INTERACTION,
}


_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS = {
    "요약": KnowledgeSectionType.SUMMARY,
    "약리작용": KnowledgeSectionType.OVERVIEW,
    "효능.효과": KnowledgeSectionType.FUNCTION,
    "용법": KnowledgeSectionType.DAILY_INTAKE,
    "용법·용량": KnowledgeSectionType.DAILY_INTAKE,
    "용법․용량": KnowledgeSectionType.DAILY_INTAKE,
    "경고": KnowledgeSectionType.CAUTION,
    "금기": KnowledgeSectionType.CAUTION,
    "주의사항": KnowledgeSectionType.CAUTION,
    "접종권장대상": KnowledgeSectionType.FUNCTION,
    "종류": KnowledgeSectionType.OVERVIEW,
    "부작용": KnowledgeSectionType.ADVERSE_EVENT,
    "다른백신과의동시접종": KnowledgeSectionType.INTERACTION,
}


_HEADINGS: dict[KnowledgeDocumentType, dict[str, KnowledgeSectionType]] = {
    KnowledgeDocumentType.SUPPLEMENT_CODE: {
        "원료": KnowledgeSectionType.INGREDIENT,
        "규격": KnowledgeSectionType.STANDARD,
        "기능성 내용": KnowledgeSectionType.FUNCTION,
        "일일섭취량": KnowledgeSectionType.DAILY_INTAKE,
        "시험법": KnowledgeSectionType.TEST_METHOD,
        **_COMMON_CAUTION_HEADINGS,
    },
    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE: {
        "기능성 내용": KnowledgeSectionType.FUNCTION,
        "기능성 원료": KnowledgeSectionType.INGREDIENT,
        "일일섭취량": KnowledgeSectionType.DAILY_INTAKE,
        "섭취 시 주의사항": KnowledgeSectionType.CAUTION,
    },
    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA: {
        "개요": KnowledgeSectionType.OVERVIEW,
        "효능·효과": KnowledgeSectionType.FUNCTION,
        "효능․효과": KnowledgeSectionType.FUNCTION,
        "용법·용량": KnowledgeSectionType.DAILY_INTAKE,
        "용법․용량": KnowledgeSectionType.DAILY_INTAKE,
        **_COMMON_CAUTION_HEADINGS,
        **_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS,
    },
    KnowledgeDocumentType.ADVERSE_CASE_REPORT: {
        "환자 정보": KnowledgeSectionType.CASE_SUMMARY,
        "이상사례": KnowledgeSectionType.ADVERSE_EVENT,
        "복용 의약품 정보": KnowledgeSectionType.INGREDIENT,
        "상세 사항": KnowledgeSectionType.ASSESSMENT,
        "평가 의견 및 참고 사항": KnowledgeSectionType.ASSESSMENT,
        "WHO-UMC 인과성 평가 기준": KnowledgeSectionType.ASSESSMENT,
    },
    KnowledgeDocumentType.PHARM_REVIEW: {
        "개요": KnowledgeSectionType.OVERVIEW,
        "키워드": KnowledgeSectionType.SUMMARY,
        "서론": KnowledgeSectionType.INTRODUCTION,
        "결론": KnowledgeSectionType.CONCLUSION,
        "참고문헌": KnowledgeSectionType.REFERENCES,
        "◘ 참고문헌 ◘": KnowledgeSectionType.REFERENCES,
    },
    KnowledgeDocumentType.RESEARCH_ARTICLE: {
        "Abstract": KnowledgeSectionType.SUMMARY,
        "Introduction": KnowledgeSectionType.INTRODUCTION,
        "Materials and Methods": KnowledgeSectionType.METHODS,
        "Methods": KnowledgeSectionType.METHODS,
        "Results": KnowledgeSectionType.RESULTS,
        "Discussion": KnowledgeSectionType.DISCUSSION,
        "Limitations": KnowledgeSectionType.DISCUSSION,
        "Conclusion": KnowledgeSectionType.CONCLUSION,
        "Conclusions": KnowledgeSectionType.CONCLUSION,
        "References": KnowledgeSectionType.REFERENCES,
        "Bibliography": KnowledgeSectionType.REFERENCES,
    },
    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE: {
        "의약품-식품간 상호작용 요약서": KnowledgeSectionType.INTERACTION,
        "그밖에 안전한 약복용 방법": KnowledgeSectionType.CAUTION,
        "발 행 일": KnowledgeSectionType.REFERENCES,
    },
    KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH: {
        **_COMMON_CAUTION_HEADINGS,
    },
}


_ATTACHED_BODY_HEADINGS_BY_SOURCE = {
    "kpicia_drug_encyclopedia": frozenset(_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS),
}

_ATTACHED_BODY_PROSE_CONTINUATION = re.compile(r"^(?:하면|하자면|은|는|이|가|을|를|의|도|만|에서|에는|으로)(?:\s|$)")


class KnowledgeSplitter:
    _SEPARATORS = [
        "\n\n",
        "\n",
        "다. ",
        ". ",
        "? ",
        "! ",
        "; ",
        ", ",
        " ",
        "",
    ]

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        interaction_annotations: KnowledgeInteractionAnnotationRegistry | None = None,
    ) -> None:
        self._token_counter = token_counter or TiktokenTokenCounter()
        self._supplement_code_parser = SupplementCodeParser()
        self._entity_extractor = KnowledgeEntityExtractor(
            interaction_annotations=interaction_annotations,
        )

    def split(self, pages: list[KnowledgePage]) -> list[KnowledgeChunk]:
        if not pages:
            return []

        self._validate_single_document(pages)
        metadata = pages[0].metadata
        policy = _POLICIES[metadata.document_type]
        sections, page_ranges = self._split_sections(pages)
        sections = self._merge_leading_context(
            sections,
            policy,
        )
        chunks: list[KnowledgeChunk] = []

        for section in sections:
            if section.section_type == KnowledgeSectionType.REFERENCES:
                continue
            if metadata.document_type == KnowledgeDocumentType.SUPPLEMENT_CODE and section.section_type in {
                KnowledgeSectionType.STANDARD,
                KnowledgeSectionType.TEST_METHOD,
            }:
                continue
            if not self._has_meaningful_body(section):
                continue

            contents = self._split_section_content(section.content, policy)
            for content, local_start, local_end in contents:
                cleaned = content.strip()
                if not cleaned or not self._has_meaningful_text(
                    cleaned,
                    section.section_title,
                ):
                    continue
                if metadata.document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
                    page_start, page_end = (
                        section.page_start,
                        section.page_end,
                    )
                else:
                    page_start, page_end = self._page_range_for(
                        section.source_start + local_start,
                        section.source_start + local_end,
                        page_ranges,
                    )
                chunk_section = section.model_copy(
                    update={
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )
                chunks.append(
                    self._build_chunk(
                        content=cleaned,
                        section=chunk_section,
                        chunk_index=len(chunks),
                        metadata=metadata,
                    )
                )

        return chunks

    @staticmethod
    def _has_meaningful_body(section: KnowledgeSection) -> bool:
        return KnowledgeSplitter._has_meaningful_text(
            section.content,
            section.section_title,
        )

    @staticmethod
    def _has_meaningful_text(
        content: str,
        section_title: str | None,
    ) -> bool:
        body = content
        if section_title:
            body = re.sub(
                rf"^\s*{re.escape(section_title)}",
                "",
                body,
                count=1,
                flags=re.IGNORECASE,
            )
        meaningful_characters = re.findall(r"[A-Za-z0-9가-힣]", body)
        return len(meaningful_characters) >= 2

    def _merge_leading_context(
        self,
        sections: list[KnowledgeSection],
        policy: ChunkingPolicy,
    ) -> list[KnowledgeSection]:
        if len(sections) < 2:
            return sections

        leading, following = sections[0], sections[1]
        if (
            leading.section_type != KnowledgeSectionType.OTHER
            or self._token_counter.count(leading.content) >= policy.target_min_tokens
        ):
            return sections

        merged_content = f"{leading.content}\n\n{following.content}"
        if self._token_counter.count(merged_content) > policy.hard_max_tokens:
            return sections

        merged = following.model_copy(
            update={
                "content": merged_content,
                "page_start": min(leading.page_start, following.page_start),
                "source_start": leading.source_start,
                "source_end": following.source_end,
            }
        )
        return [merged, *sections[2:]]

    @staticmethod
    def policy_for(document_type: KnowledgeDocumentType) -> ChunkingPolicy:
        return _POLICIES[document_type]

    def _split_sections(
        self,
        pages: list[KnowledgePage],
    ) -> tuple[list[KnowledgeSection], list[tuple[int, int, int]]]:
        metadata = pages[0].metadata
        if metadata.document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            supplement_sections, supplement_page_ranges = self._supplement_code_parser.parse(pages)
            if supplement_sections:
                return supplement_sections, supplement_page_ranges
        headings = _HEADINGS.get(metadata.document_type, {})
        combined, page_ranges = self._combine_pages(pages)
        matches = self._find_heading_matches(
            combined,
            headings,
            attached_body_headings=_ATTACHED_BODY_HEADINGS_BY_SOURCE.get(
                metadata.source_id,
                frozenset(),
            ),
        )

        if not matches:
            content = combined.strip()
            source_start = len(combined) - len(combined.lstrip())
            return [
                KnowledgeSection(
                    content=content,
                    section_type=KnowledgeSectionType.OTHER,
                    page_start=pages[0].page_number,
                    page_end=pages[-1].page_number,
                    source_start=source_start,
                    source_end=source_start + len(content),
                )
            ], page_ranges

        boundaries = [(0, None, KnowledgeSectionType.OTHER), *matches]
        sections: list[KnowledgeSection] = []

        for index, (start, title, section_type) in enumerate(boundaries):
            end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(combined)
            raw_content = combined[start:end]
            content = raw_content.strip()
            if not content:
                continue
            source_start = start + len(raw_content) - len(raw_content.lstrip())
            source_end = source_start + len(content)
            page_start, page_end = self._page_range_for(
                source_start,
                source_end,
                page_ranges,
            )
            sections.append(
                KnowledgeSection(
                    content=content,
                    section_type=section_type,
                    section_title=title,
                    page_start=page_start,
                    page_end=page_end,
                    source_start=source_start,
                    source_end=source_end,
                )
            )

        return sections, page_ranges

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
    def _find_heading_matches(
        content: str,
        headings: dict[str, KnowledgeSectionType],
        *,
        attached_body_headings: frozenset[str],
    ) -> list[tuple[int, str, KnowledgeSectionType]]:
        candidates: list[tuple[int, int, str, KnowledgeSectionType]] = []

        for heading, section_type in sorted(headings.items(), key=lambda item: len(item[0]), reverse=True):
            for match in re.finditer(re.escape(heading), content, flags=re.IGNORECASE):
                if not KnowledgeSplitter._is_heading_boundary(
                    content,
                    match.start(),
                    match.end(),
                    allow_attached_body=(heading in attached_body_headings),
                ):
                    continue
                candidates.append((match.start(), match.end(), heading, section_type))

        selected: list[tuple[int, int, str, KnowledgeSectionType]] = []
        last_selected_end = -1
        last_start_by_heading: dict[str, int] = {}
        for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
            start, end, heading, _ = candidate
            if start < last_selected_end:
                continue
            normalized_heading = heading.casefold()
            previous_start = last_start_by_heading.get(normalized_heading)
            if previous_start is not None and start - previous_start < 120:
                continue
            selected.append(candidate)
            last_selected_end = end
            last_start_by_heading[normalized_heading] = start

        return [(start, heading, section_type) for start, _, heading, section_type in sorted(selected)]

    @staticmethod
    def _is_heading_boundary(
        content: str,
        start: int,
        end: int,
        *,
        allow_attached_body: bool = False,
    ) -> bool:
        at_line_start = start == 0
        if start > 0:
            prefix = content[:start]
            at_line_start = not prefix.rsplit("\n", maxsplit=1)[-1].strip()
            previous_non_space = prefix.rstrip()
            if not at_line_start and previous_non_space:
                if previous_non_space[-1] not in ".!?。:;)]}":
                    return False

        if end < len(content):
            following_text = content[end:]
            following = following_text[0]
            if not following.isspace() and following not in ":：-–—([{•·":
                if not (allow_attached_body and (at_line_start or following.isdigit())):
                    return False
                if _ATTACHED_BODY_PROSE_CONTINUATION.match(following_text):
                    return False

        return True

    def _split_section_content(
        self,
        content: str,
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        if self._token_counter.count(content) <= policy.hard_max_tokens:
            return [(content, 0, len(content))]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=policy.hard_max_tokens,
            chunk_overlap=policy.overlap_tokens,
            length_function=self._token_counter.count,
            separators=self._SEPARATORS,
            is_separator_regex=False,
        )
        chunks: list[tuple[str, int, int]] = []
        previous_start = -1
        for chunk in splitter.split_text(content):
            start = content.find(chunk, previous_start + 1)
            if start < 0:
                raise ValueError("재귀 분할 청크의 원문 위치를 찾지 못했습니다.")
            previous_start = start
            chunks.append(
                (
                    chunk,
                    start,
                    start + len(chunk),
                )
            )
        return self._merge_small_fragments(
            content,
            chunks,
            policy,
        )

    def _merge_small_fragments(
        self,
        source: str,
        chunks: list[tuple[str, int, int]],
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        merged: list[tuple[str, int, int]] = []

        for content, start, end in chunks:
            if merged and self._token_counter.count(content) < policy.target_min_tokens:
                _, previous_start, _ = merged[-1]
                combined = source[previous_start:end].strip()
                if self._token_counter.count(combined) <= policy.hard_max_tokens:
                    merged[-1] = (
                        combined,
                        previous_start,
                        end,
                    )
                    continue
            merged.append((content, start, end))

        return merged

    def _build_chunk(
        self,
        *,
        content: str,
        section: KnowledgeSection,
        chunk_index: int,
        metadata,
    ) -> KnowledgeChunk:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_key = "|".join(
            [
                metadata.document_id,
                section.section_type.value,
                str(section.page_start),
                str(section.page_end),
                str(chunk_index),
                content_hash,
            ]
        )
        chunk_id = hashlib.sha256(chunk_key.encode("utf-8")).hexdigest()
        entities = self._entity_extractor.extract_from_chunk(
            document_type=metadata.document_type,
            title=metadata.title,
            content=content,
            document_id=metadata.document_id,
            section_type=section.section_type,
        )
        metadata_values = metadata.model_dump()
        metadata_values.update(
            {
                "drug_names": entities.drug_names or metadata.drug_names,
                "ingredient_names": entities.ingredient_names or metadata.ingredient_names,
                "interaction_type": entities.interaction_type or metadata.interaction_type,
                "interaction_pair_keys": (entities.interaction_pair_keys or metadata.interaction_pair_keys),
                "evidence_level": (
                    entities.evidence_level
                    if entities.evidence_level != KnowledgeEvidenceLevel.UNKNOWN
                    else metadata.evidence_level
                ),
                "study_population": (
                    entities.study_population
                    if entities.study_population != KnowledgeStudyPopulation.UNKNOWN
                    else metadata.study_population
                ),
            }
        )
        chunk_metadata = KnowledgeChunkMetadata(
            **metadata_values,
            section_type=section.section_type,
            section_title=section.section_title,
            page_start=section.page_start,
            page_end=section.page_end,
            chunk_index=chunk_index,
            content_hash=content_hash,
        )

        return KnowledgeChunk(
            chunk_id=chunk_id,
            content=content,
            embedding_text=self._build_embedding_text(
                content=content,
                metadata=chunk_metadata,
            ),
            token_count=self._token_counter.count(content),
            metadata=chunk_metadata,
        )

    @staticmethod
    def _build_embedding_text(
        *,
        content: str,
        metadata: KnowledgeChunkMetadata,
    ) -> str:
        prefixes = [f"[문서] {metadata.title}"]
        if metadata.drug_names:
            prefixes.append(f"[약] {', '.join(metadata.drug_names)}")
        if metadata.ingredient_names:
            prefixes.append(f"[성분] {', '.join(metadata.ingredient_names)}")
        if metadata.interaction_type:
            label = _INTERACTION_LABELS.get(
                metadata.interaction_type,
                metadata.interaction_type,
            )
            prefixes.append(f"[상호작용] {label}")
        evidence_label = _EVIDENCE_LABELS.get(metadata.evidence_level.value)
        if evidence_label:
            prefixes.append(f"[근거 수준] {evidence_label}")
        population_label = _POPULATION_LABELS.get(metadata.study_population.value)
        if population_label:
            prefixes.append(f"[연구 대상] {population_label}")
        section_name = metadata.section_title or metadata.section_type.value
        prefixes.append(f"[섹션] {section_name}")
        return "\n".join([*prefixes, "[원문]", content])

    @staticmethod
    def _page_range_for(
        start: int,
        end: int,
        page_ranges: list[tuple[int, int, int]],
    ) -> tuple[int, int]:
        overlapping = [
            page_number for page_start, page_end, page_number in page_ranges if start < page_end and end > page_start
        ]
        if not overlapping:
            return page_ranges[0][2], page_ranges[-1][2]
        return min(overlapping), max(overlapping)

    @staticmethod
    def _validate_single_document(pages: list[KnowledgePage]) -> None:
        document_ids = {page.metadata.document_id for page in pages}
        if len(document_ids) != 1:
            raise ValueError("한 번에 하나의 지식 문서만 청킹할 수 있습니다.")
