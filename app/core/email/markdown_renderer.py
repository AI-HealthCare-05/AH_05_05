import html
import re
from urllib.parse import urlsplit

from markupsafe import Markup

_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")
_LIST_ITEM = re.compile(r"^[-*]\s+(.+)$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def render_safe_markdown(markdown: str) -> Markup:  # noqa: C901
    """Render the report's small Markdown subset without allowing supplied HTML."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if _is_table_start(lines, index):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            blocks.append(_render_table(table_lines))
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if _LIST_ITEM.match(line):
            items: list[str] = []
            while index < len(lines):
                item = _LIST_ITEM.match(lines[index])
                if item is None:
                    break
                items.append(f"<li>{_inline(item.group(1))}</li>")
                index += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not _is_table_start(lines, index):
            if paragraph and (_HEADING.match(lines[index]) or _LIST_ITEM.match(lines[index])):
                break
            paragraph.append(lines[index])
            index += 1
        blocks.append(f"<p>{'<br>'.join(_inline(part) for part in paragraph)}</p>")
    return Markup("\n".join(blocks))


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and lines[index].strip().startswith("|")
        and _is_table_divider(lines[index + 1])
    )


def _is_table_divider(line: str) -> bool:
    cells = [cell.strip().replace(":", "") for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r"-+", cell) for cell in cells)


def _render_table(lines: list[str]) -> str:
    rows = [_table_cells(line) for line in lines]
    header = rows[0]
    body = rows[2:]
    header_html = "".join(
        '<th style="padding:10px;border:1px solid #d9e1e5;background:#f7fbfa;text-align:left;overflow-wrap:anywhere">'
        f"{_inline(cell)}</th>"
        for cell in header
    )
    body_html = "".join(
        "<tr>"
        + "".join(
            '<td style="padding:10px;border:1px solid #d9e1e5;vertical-align:top;overflow-wrap:anywhere;word-break:break-word">'
            f"{_inline(cell)}</td>"
            for cell in row
        )
        + "</tr>"
        for row in body
    )
    return (
        '<table style="width:100%;border-collapse:collapse;table-layout:fixed;margin:16px 0">'
        f"<thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"
    )


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _inline(value: str) -> str:
    pieces: list[str] = []
    last_end = 0
    for match in _LINK.finditer(value):
        pieces.append(_format_text(value[last_end : match.start()]))
        label, url = match.groups()
        pieces.append(_render_link(label, url))
        last_end = match.end()
    pieces.append(_format_text(value[last_end:]))
    return "".join(pieces)


def _format_text(value: str) -> str:
    # Detect trusted Markdown before decoding literal entities. Evidence text
    # may contain brackets/stars that must display as text, never new markup.
    def escaped_text(part: str) -> str:
        return html.escape(html.unescape(part), quote=True)

    pieces: list[str] = []
    last_end = 0
    for match in _BOLD.finditer(value):
        pieces.append(escaped_text(value[last_end : match.start()]))
        pieces.append(f"<strong>{escaped_text(match.group(1))}</strong>")
        last_end = match.end()
    pieces.append(escaped_text(value[last_end:]))
    return "".join(pieces)


def _render_link(label: str, url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return _format_text(label)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return _format_text(label)
    safe_url = html.escape(url, quote=True)
    return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{_format_text(label)}</a>'
