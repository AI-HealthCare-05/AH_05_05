from pathlib import Path

STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"


def test_sidebar_exposes_challenge_management_links() -> None:
    sidebar = (STATIC_ROOT / "templates/partials/sidebar.html").read_text(encoding="utf-8")

    assert "챌린지 관리" in sidebar
    assert "공식 챌린지 관리" in sidebar
    assert "맞춤 챌린지 템플릿 관리" in sidebar
    assert "배지 관리" in sidebar
    assert 'href="challenge-management.html"' in sidebar
    assert 'data-nav="challenges"' in sidebar
    assert 'href="custom-challenge-template-management.html"' in sidebar
    assert 'data-nav="custom-challenge-templates"' in sidebar
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
    assert "<th>배지 유형</th>" in badge
    assert "badge-management.js?v=20260909-4" in badge
    assert "data-badge-type-filter" in badge


def test_challenge_page_uses_inline_official_badge_select() -> None:
    challenge = (STATIC_ROOT / "templates/challenge-management.html").read_text(encoding="utf-8")

    assert '<input class="ui-control" type="search" name="name"' in challenge
    assert '<option value="">챌린지유형</option>' in challenge
    assert '<option value="">전시여부</option>' in challenge
    assert '챌린지유형<select class="ui-control" name="challenge_type_id" required>' in challenge
    assert '<label>지급 배지<select class="ui-control" name="reward_badge_id">' in challenge
    assert "data-badge-search-dialog" not in challenge
    assert "data-open-badge-search" not in challenge


def test_custom_challenge_template_management_page_loads_its_script() -> None:
    page = (STATIC_ROOT / "templates/custom-challenge-template-management.html").read_text(encoding="utf-8")

    assert 'data-active-nav="custom-challenge-templates"' in page
    assert "custom-challenge-template-management.js" in page
    assert "data-custom-template-rows" in page
    assert "data-custom-template-search" in page
    assert "data-custom-template-dialog" in page
    assert "<th>챌린지 유형</th>" in page
    assert "custom-challenge-template-management.js?v=20260909-4" in page
    assert 'name="challenge_type"' in page
    assert "custom-template-search-form" in page
    assert "배지유형" not in page
    assert "<span>지급배지</span>" in page
    assert page.count('name="reward_badge_id"') == 1


def test_badge_management_page_exposes_badge_type_field() -> None:
    page = (STATIC_ROOT / "templates/badge-management.html").read_text(encoding="utf-8")

    assert 'name="type"' in page
