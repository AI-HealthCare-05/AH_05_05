CHAT_CONTENT_MAX_LENGTH = 2000
HISTORY_COMPACTION_MARKER = "[이전 대화 축약]"
ANSWER_COMPACTION_MARKER = "[긴 답변 축약]"


def compact_chat_content(
    content: str,
    *,
    marker: str,
    max_length: int = CHAT_CONTENT_MAX_LENGTH,
) -> str:
    normalized = content.strip()
    if len(normalized) <= max_length:
        return normalized

    separator = f"\n\n{marker}\n\n"
    available = max_length - len(separator)
    tail_length = min(300, available // 4)
    head_length = available - tail_length
    head = _complete_head(normalized, limit=head_length)
    tail = _complete_tail(normalized, limit=tail_length)
    return head + separator + tail


def _complete_head(content: str, *, limit: int) -> str:
    candidate = content[:limit].rstrip()
    minimum_boundary = limit // 2
    boundaries = [candidate.rfind("\n")]
    boundaries.extend(candidate.rfind(mark) for mark in (".", "!", "?", "。", "！", "？"))
    boundary = max(boundaries)
    if boundary >= minimum_boundary:
        return candidate[: boundary + 1].rstrip()
    return candidate


def _complete_tail(content: str, *, limit: int) -> str:
    start = max(0, len(content) - limit)
    paragraph_boundary = content.find("\n\n", start)
    if paragraph_boundary >= 0:
        return content[paragraph_boundary + 2 :].lstrip()

    line_boundary = content.find("\n", start)
    if line_boundary >= 0:
        return content[line_boundary + 1 :].lstrip()
    return content[-limit:].lstrip()
