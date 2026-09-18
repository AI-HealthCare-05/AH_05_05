import re

from ai_worker.rag.ingredient_name_aliases import (
    aliases_match_collection,
    english_aliases_for,
    korean_alias_for,
    load_ingredient_name_aliases,
    use_collection,
)


def test_known_korean_ingredient_resolves_to_its_english_name() -> None:
    assert "warfarin" in english_aliases_for("와파린")


def test_english_metadata_name_resolves_back_to_korean() -> None:
    assert korean_alias_for("warfarin") == "와파린"


def test_unknown_names_resolve_to_nothing_instead_of_guessing() -> None:
    """카탈로그로 확인하지 못한 이름은 잇지 않는다. 억지 연결은 없는 근거를 만든다."""
    assert english_aliases_for("등록되지않은성분") == ()
    assert korean_alias_for("not-an-indexed-ingredient") is None


def test_alias_is_rejected_when_built_from_another_collection() -> None:
    """말뭉치가 교체되면 낡은 사전을 쓰지 않도록 호출자가 확인할 수 있어야 한다."""
    aliases = load_ingredient_name_aliases()

    assert aliases_match_collection(aliases.source_collection) is True
    assert aliases_match_collection("medication_knowledge_full_v999") is False


def test_asset_never_links_a_longer_ingredient_to_a_shorter_different_one() -> None:
    """접두가 다른 성분을 같은 성분으로 잇지 않는다.

    `클로르펜터민(chlorphentermine)`을 `펜터민`으로 줄이면 다른 약의 근거가
    정답 근거로 승격된다. 실제로 그렇게 생성된 적이 있어 불변식으로 고정한다.
    """
    aliases = load_ingredient_name_aliases().aliases
    korean_to_english: dict[str, list[str]] = {}
    for english, korean in aliases.items():
        korean_to_english.setdefault(korean, []).append(english)

    contained_pairs = [
        (shorter, longer, korean)
        for korean, englishes in korean_to_english.items()
        for shorter in englishes
        for longer in englishes
        if shorter != longer and shorter in longer and not longer.startswith(f"{shorter} ")
    ]

    assert contained_pairs == []


def test_asset_values_are_korean_ingredient_names() -> None:
    aliases = load_ingredient_name_aliases().aliases

    assert all(re.fullmatch(r"[가-힣0-9·\-]{2,}", korean) for korean in aliases.values())


def test_aliases_are_disabled_when_the_asset_came_from_another_collection() -> None:
    """말뭉치가 교체되면 별칭 없이 동작한다. 서비스를 막지는 않는다."""
    original = load_ingredient_name_aliases().source_collection
    try:
        use_collection("medication_knowledge_full_v999")

        assert english_aliases_for("와파린") == ()
        assert korean_alias_for("warfarin") is None
    finally:
        use_collection(original)

    assert "warfarin" in english_aliases_for("와파린")
