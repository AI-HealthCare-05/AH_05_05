from html.parser import HTMLParser
from pathlib import Path

SIDEBAR_PATH = Path(__file__).resolve().parents[2] / "static/templates/partials/sidebar.html"


class SidebarGroupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.toggles: list[dict[str, str | None]] = []
        self.subnavs: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "button" and "data-sidebar-group-toggle" in attributes:
            self.toggles.append(attributes)
        if tag == "div" and "data-sidebar-subnav" in attributes:
            self.subnavs.append(attributes)


def test_management_groups_are_collapsed_accessible_toggle_controls() -> None:
    parser = SidebarGroupParser()
    parser.feed(SIDEBAR_PATH.read_text(encoding="utf-8"))

    assert len(parser.toggles) == 3
    assert len(parser.subnavs) == 3
    assert all(toggle["aria-expanded"] == "false" for toggle in parser.toggles)
    assert all(toggle.get("aria-controls") for toggle in parser.toggles)
    assert {toggle["aria-controls"] for toggle in parser.toggles} == {subnav["id"] for subnav in parser.subnavs}
    assert all("hidden" in subnav for subnav in parser.subnavs)
