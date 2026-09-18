from scripts.build_ingredient_name_aliases import _catalog_match, _normalize_english

CATALOG = {"펜터민", "와파린", "이부프로펜", "로바스타틴", "아토르바스타틴"}


def test_catalog_match_accepts_a_whole_ingredient_name() -> None:
    assert _catalog_match("와파린", CATALOG) == "와파린"


def test_catalog_match_rejects_a_longer_compound_ingredient() -> None:
    """`클로르펜터민`을 `펜터민`으로 줄이면 다른 약의 근거가 정답으로 승격된다."""
    assert _catalog_match("클로르펜터민", CATALOG) is None


def test_catalog_match_rejects_a_sentence_tail() -> None:
    """앞 문장 꼬리가 붙은 포착은 버린다. 잘라서 구제하지 않는다."""
    assert _catalog_match("은저위험환자에게서아스피린", CATALOG) is None


def test_normalize_english_collapses_spacing_and_case() -> None:
    assert _normalize_english("  Zinc   Oxide ") == "zinc oxide"
