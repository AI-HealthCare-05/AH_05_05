from ai_worker.rag.loaders.botanical_review_layout_parser import (
    BotanicalReviewLayoutParser,
)
from ai_worker.schemas.knowledge import KnowledgeContentKind


class FakeLayoutPage:
    width = 594.0
    height = 783.0

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kwargs):
        return self._words


def word(text: str, x0: float, top: float, x1: float, bottom: float):
    return {
        "text": text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
    }


def test_parse_page_three_excludes_non_content_plant_inventory_table() -> None:
    page = FakeLayoutPage(
        [
            word("Plants", 42, 61, 80, 72),
            word("included", 84, 61, 125, 72),
            word("Abies", 50, 130, 80, 141),
            word("and", 42, 385, 60, 396),
            word("interactions", 64, 385, 125, 396),
            word("drugs;", 311, 385, 345, 396),
            word("assessment", 349, 385, 410, 396),
        ]
    )

    extraction = BotanicalReviewLayoutParser().parse(
        page=page,
        page_number=3,
        source_id="research_supplement_adverse_effects",
    )

    assert extraction is not None
    assert all(block.kind == KnowledgeContentKind.TEXT for block in extraction.blocks)
    assert [block.content for block in extraction.blocks] == [
        "and interactions",
        "drugs; assessment",
    ]
    assert "Plants included" not in " ".join(block.content for block in extraction.blocks)


def test_parse_page_four_separates_who_table_from_two_column_body() -> None:
    page = FakeLayoutPage(
        [
            word("Causality", 50, 106, 90, 117),
            word("classification", 94, 106, 140, 117),
            word("Details", 150, 106, 185, 117),
            word("Certain", 50, 123, 82, 134),
            word("A", 150, 123, 157, 134),
            word("clinical", 161, 123, 195, 134),
            word("event", 199, 123, 225, 134),
            word("Probable/likely", 50, 224, 118, 235),
            word("Reasonable", 150, 224, 205, 235),
            word("sequence", 209, 224, 250, 235),
            word("ranging", 42, 576, 80, 587),
            word("from", 84, 576, 108, 587),
            word("cases", 311, 61, 340, 72),
            word("were", 344, 61, 368, 72),
            word("Cimicifuga", 311, 612, 370, 623),
        ]
    )

    extraction = BotanicalReviewLayoutParser().parse(
        page=page,
        page_number=4,
        source_id="research_supplement_adverse_effects",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    text = [block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT]
    assert table.headers == ["Causality classification", "Details"]
    assert table.rows[0].cells == ["Certain", "A clinical event"]
    assert table.rows[1].cells == ["Probable/likely", "Reasonable sequence"]
    assert text == ["ranging from", "cases were", "Cimicifuga"]


def test_parse_ignores_other_sources() -> None:
    extraction = BotanicalReviewLayoutParser().parse(
        page=FakeLayoutPage([]),
        page_number=4,
        source_id="another_research_source",
    )

    assert extraction is None


def test_parse_page_six_keeps_adverse_event_and_interaction_tables_separate() -> None:
    page = FakeLayoutPage(
        [
            word("Glycine", 50, 141, 85, 152),
            word("max", 89, 141, 110, 152),
            word("91", 250, 141, 262, 152),
            word("58", 320, 141, 332, 152),
            word("11", 390, 141, 402, 152),
            word("22", 470, 141, 482, 152),
            word("Citrus", 50, 408, 82, 419),
            word("aurantium", 86, 408, 135, 419),
            word("18", 250, 408, 262, 419),
            word("6", 320, 408, 326, 419),
            word("11", 390, 408, 402, 419),
            word("1", 470, 408, 476, 419),
        ]
    )

    extraction = BotanicalReviewLayoutParser().parse(
        page=page,
        page_number=6,
        source_id="research_supplement_adverse_effects",
    )

    assert extraction is not None
    tables = [block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE]
    assert len(tables) == 2
    assert tables[0].rows[0].cells == ["Glycine max", "91", "58", "11", "22"]
    assert tables[1].rows[0].cells == ["Citrus aurantium", "18", "6", "11", "1"]


def test_parse_page_seven_keeps_five_column_product_form_table() -> None:
    page = FakeLayoutPage(
        [
            word("Hypericum", 50, 150, 100, 161),
            word("perforatum", 104, 150, 160, 161),
            word("Flowering", 185, 150, 225, 161),
            word("herb", 229, 150, 248, 161),
            word("–", 260, 150, 266, 161),
            word("Tablets", 350, 150, 390, 161),
            word("Unspecified", 460, 150, 520, 161),
            word("extracts", 460, 160, 500, 171),
        ]
    )

    extraction = BotanicalReviewLayoutParser().parse(
        page=page,
        page_number=7,
        source_id="research_supplement_adverse_effects",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers[-2:] == ["Plant food supplement (type)", "Others"]
    populated_row = next(row for row in table.rows if any(row.cells))
    assert populated_row.cells == [
        "Hypericum perforatum",
        "Flowering herb",
        "–",
        "Tablets",
        "Unspecified extracts",
    ]
