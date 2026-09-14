import re
import unicodedata

from ai_worker.schemas.knowledge import KnowledgeSectionType

_INVISIBLE_TEXT = re.compile(r"[\u00ad\u200b-\u200f\u2060\ufeff]")
_REPEATED_HORIZONTAL_SPACE = re.compile(r"[ \t]{2,}")
_REPEATED_BLANK_LINES = re.compile(r"\n{3,}")
_STANDALONE_PAGE_NUMBER = re.compile(r"(?m)^\s*(?:page|페이지)?\s*\d{1,4}\s*$")
_TABLE_DELIMITER = re.compile(r"\s*\|\s*")


def sanitize_embedding_content(content: str) -> str:
    """검색 입력에서 레이아웃 노이즈만 제거하고 근거 원문은 변경하지 않는다."""

    normalized = unicodedata.normalize("NFKC", content)
    normalized = _INVISIBLE_TEXT.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _STANDALONE_PAGE_NUMBER.sub("", normalized)
    normalized = _TABLE_DELIMITER.sub("\n", normalized)
    lines = [_REPEATED_HORIZONTAL_SPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    normalized = _REPEATED_BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


def build_medical_retrieval_query_text(
    *,
    question: str,
    entity_names: list[str],
    section_types: list[KnowledgeSectionType],
    pair_names: list[str],
) -> str:
    """질문 원문을 보존하면서 query plan의 검증된 검색 구조를 덧붙인다."""

    lines = [f"[질문] {question.strip()}"]
    if entity_names:
        lines.append(f"[대상] {', '.join(dict.fromkeys(entity_names))}")
    if section_types:
        lines.append(f"[요청 섹션] {', '.join(section.value for section in section_types)}")
    if pair_names:
        lines.append(f"[상호작용 조합] {', '.join(dict.fromkeys(pair_names))}")
    return "\n".join(lines)
