import re
from html.parser import HTMLParser
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "app" / "static" / "templates"
MANAGEMENT_CSS = TEMPLATE_DIR.parent / "css" / "management.css"
PAGE_ACTIVE_NAV = {
    "dashboard.html": "dashboard",
    "user-management.html": "users",
    "screen-4-admin-management.html": "admins",
    "screen-5-task-management.html": "tasks",
}


class SidebarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.asides: list[dict[str, str | None]] = []
        self.navigation_sections: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "aside":
            self.asides.append(attributes)
        if tag == "a" and attributes.get("data-nav"):
            self.navigation_sections.append(str(attributes["data-nav"]))
        if tag == "script" and attributes.get("src"):
            self.scripts.append(str(attributes["src"]))
        if tag == "link" and attributes.get("rel") == "stylesheet" and attributes.get("href"):
            self.stylesheets.append(str(attributes["href"]))


def parse_template(path: Path) -> SidebarParser:
    parser = SidebarParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def test_management_pages_use_the_shared_sidebar_placeholder() -> None:
    for filename, active_nav in PAGE_ACTIVE_NAV.items():
        page = parse_template(TEMPLATE_DIR / filename)

        assert len(page.asides) == 1, filename
        assert page.asides[0].get("data-sidebar") is None, filename
        assert page.asides[0].get("data-active-nav") == active_nav, filename
        assert page.navigation_sections == [], filename


def test_sidebar_partial_contains_every_navigation_target_once() -> None:
    sidebar = parse_template(TEMPLATE_DIR / "partials" / "sidebar.html")

    assert len(sidebar.asides) == 1
    assert sidebar.navigation_sections == ["dashboard", "users", "admins", "tasks", "logout"]


def test_active_sidebar_link_uses_reference_colors_and_bold_weight() -> None:
    css = MANAGEMENT_CSS.read_text(encoding="utf-8")
    base_rule = re.search(r"\.sidebar-link\s*\{([^}]*)\}", css)
    active_rule = re.search(r"\.sidebar-link\.is-active\s*\{([^}]*)\}", css)

    assert base_rule is not None
    assert active_rule is not None
    base_declarations = {
        name.strip(): value.strip() for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", base_rule.group(1))
    }
    declarations = {
        name.strip(): value.strip() for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+)", active_rule.group(1))
    }

    assert base_declarations["border"] == "2px solid transparent"
    assert declarations["background"] == "#eff6ff"
    assert declarations["color"] == "#1d4ed8"
    assert declarations["font-weight"] == "700"
    assert declarations["border-color"] == "#1d4ed8"
