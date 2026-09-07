from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


def test_sidebar_exposes_challenge_management_links() -> None:
    sidebar = (STATIC_ROOT / "templates/partials/sidebar.html").read_text(encoding="utf-8")

    assert "챌린지관리" in sidebar
    assert 'href="challenge-management.html"' in sidebar
    assert 'data-nav="challenges"' in sidebar
    assert 'href="badge-management.html"' in sidebar
    assert 'data-nav="badges"' in sidebar


def test_challenge_and_badge_management_pages_load_their_scripts() -> None:
    challenge = (STATIC_ROOT / "templates/challenge-management.html").read_text(encoding="utf-8")
    badge = (STATIC_ROOT / "templates/badge-management.html").read_text(encoding="utf-8")

    assert 'data-active-nav="challenges"' in challenge
    assert "challenge-management.js" in challenge
    assert "data-challenge-rows" in challenge
    assert 'data-active-nav="badges"' in badge
    assert "badge-management.js" in badge
    assert "data-badge-rows" in badge
