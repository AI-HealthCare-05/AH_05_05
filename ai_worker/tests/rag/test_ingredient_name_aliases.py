from ai_worker.rag.ingredient_name_aliases import (
    english_aliases_for,
    korean_alias_for,
    load_ingredient_name_aliases,
)


def test_alias_asset_is_derived_from_the_indexed_collection() -> None:
    aliases = load_ingredient_name_aliases()

    assert aliases.source_collection
    assert aliases.aliases


def test_known_korean_ingredient_resolves_to_its_english_name() -> None:
    assert "warfarin" in english_aliases_for("와파린")


def test_english_metadata_name_resolves_back_to_korean() -> None:
    assert korean_alias_for("warfarin") == "와파린"


def test_unknown_names_resolve_to_nothing_instead_of_guessing() -> None:
    """카탈로그로 확인하지 못한 이름은 잇지 않는다. 억지 연결은 없는 근거를 만든다."""
    assert english_aliases_for("등록되지않은성분") == ()
    assert korean_alias_for("not-an-indexed-ingredient") is None
