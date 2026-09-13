from html.parser import HTMLParser
from pathlib import Path

CHALLENGE_PAGE = Path(__file__).resolve().parents[2] / "static/templates/challenge-management.html"


class _DisplayCheckboxParser(HTMLParser):
    _VOID_ELEMENTS = {"input", "link", "meta"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.checkbox_parent: str | None = None
        self.text_parent: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "input" and attributes.get("type") == "checkbox" and attributes.get("name") == "is_displayed":
            self.checkbox_parent = self.stack[-1] if self.stack else None
        if tag not in self._VOID_ELEMENTS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.stack:
            del self.stack[self.stack.index(tag) :]

    def handle_data(self, data: str) -> None:
        if data.strip() == "사용자 화면에 전시":
            self.text_parent = self.stack[-1] if self.stack else None


def test_display_text_is_not_part_of_the_checkbox_click_target() -> None:
    parser = _DisplayCheckboxParser()
    parser.feed(CHALLENGE_PAGE.read_text(encoding="utf-8"))

    assert parser.checkbox_parent == "div"
    assert parser.text_parent == "span"
