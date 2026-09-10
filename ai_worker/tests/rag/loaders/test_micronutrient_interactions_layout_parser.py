from ai_worker.rag.loaders.micronutrient_interactions_layout_parser import (
    MicronutrientInteractionsLayoutParser,
)


class FakeLayoutPage:
    width = 595.0
    height = 794.0

    def __init__(self, words: list[dict[str, object]]) -> None:
        self._words = words

    def extract_words(self, **kwargs: object) -> list[dict[str, object]]:
        return self._words


def word(
    text: str,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    *,
    upright: bool = True,
    size: float = 10.0,
) -> dict[str, object]:
    return {
        "text": text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
        "upright": upright,
        "size": size,
        "fontname": "Body",
    }


def test_parse_front_page_keeps_title_abstract_and_left_to_right_body() -> None:
    page = FakeLayoutPage(
        [
            word("Micronutrient", 57, 95, 150, 111, size=16),
            word("interactions", 155, 95, 245, 111, size=16),
            word("A", 120, 190, 128, 200, size=9),
            word("potential", 132, 190, 170, 200, size=9),
            word("risk.", 174, 190, 200, 200, size=9),
            word("Introduction", 42, 452, 110, 463),
            word("Iron-zinc", 42, 470, 86, 480),
            word("interactions.", 90, 470, 155, 480),
            word("Calcium", 305, 452, 350, 462),
            word("affects", 354, 452, 395, 462),
            word("iron.", 399, 452, 425, 462),
            word("Downloaded", 580, 120, 588, 220, upright=False),
        ]
    )

    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Micronutrient interactions",
        "A potential risk.",
        "Introduction\nIron-zinc interactions.",
        "Calcium affects iron.",
    ]
    assert extraction.warnings == []


def test_parse_front_page_removes_corresponding_author_contact_line() -> None:
    page = FakeLayoutPage(
        [
            word("Iron-zinc", 42, 470, 86, 480),
            word("interactions.", 90, 470, 155, 480),
            word("Corresponding", 42, 715, 110, 725),
            word("author:", 114, 715, 150, 725),
            word("editor@example.com", 154, 715, 240, 725),
        ]
    )

    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert extraction.blocks[-1].content == "Iron-zinc interactions."


def test_parse_front_page_keeps_the_abstract_last_line_before_body_columns() -> None:
    page = FakeLayoutPage(
        [
            word("Abstract", 120, 380, 160, 390),
            word("status.", 120, 392, 155, 402),
        ]
    )

    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == ["Abstract\nstatus."]


def test_parse_front_page_removes_stray_email_in_body_column() -> None:
    page = FakeLayoutPage(
        [
            word("The", 42, 470, 58, 480),
            word("review", 62, 470, 90, 480),
            word("continues.", 94, 470, 140, 480),
            word("bsa@kvl.dk", 42, 486, 105, 496),
            word("The", 42, 502, 58, 512),
            word("next", 62, 502, 84, 512),
            word("sentence.", 88, 502, 135, 512),
        ]
    )

    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert extraction.blocks[-1].content == "The review continues.\nThe next sentence."


def test_parse_second_page_skips_table_and_keeps_body_columns() -> None:
    page = FakeLayoutPage(
        [
            word("Table", 42, 66, 70, 76),
            word("1", 74, 66, 79, 76),
            word("Zinc", 42, 100, 65, 110),
            word("40", 42, 115, 54, 125),
            word("Calcium", 42, 520, 90, 531),
            word("interactions", 94, 520, 170, 531),
            word("Single-meal", 42, 538, 104, 548),
            word("studies.", 108, 538, 160, 548),
            word("Zinc-copper-iron", 305, 397, 408, 408),
            word("interactions", 412, 397, 488, 408),
            word("Vitamin", 305, 598, 350, 609),
            word("C", 354, 598, 362, 609),
            word("promotes", 366, 598, 422, 609),
            word("iron.", 426, 598, 452, 609),
        ]
    )

    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Calcium interactions\nSingle-meal studies.",
        "Zinc-copper-iron interactions\nVitamin C promotes iron.",
    ]


def test_parse_excludes_reference_only_pages() -> None:
    extraction = MicronutrientInteractionsLayoutParser().parse(
        page=FakeLayoutPage([word("References", 42, 80, 100, 90)]),
        page_number=4,
        source_id="research_micronutrient_interactions",
        document_id="research_micronutrient_interactions-e3b164ce9cc98cc6",
    )

    assert extraction is not None
    assert extraction.blocks == []
