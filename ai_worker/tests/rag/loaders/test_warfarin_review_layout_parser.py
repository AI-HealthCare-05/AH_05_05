from ai_worker.rag.loaders.warfarin_review_layout_parser import (
    WarfarinReviewLayoutParser,
)
from ai_worker.schemas.knowledge import KnowledgeContentKind


class FakeLayoutPage:
    width = 595.0
    height = 782.0

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kwargs):
        return self._words


def word(
    text: str,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    *,
    upright: bool = True,
    size: float = 8.0,
    fontname: str = "Body",
):
    return {
        "text": text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
        "upright": upright,
        "size": size,
        "fontname": fontname,
    }


def test_parse_front_page_separates_keywords_from_introduction() -> None:
    page = FakeLayoutPage(
        [
            word("Warfarin", 46, 109, 117, 127),
            word("interactions:", 436, 109, 535, 127),
            word("Aims:", 211, 222, 233, 231),
            word("Overview", 237, 222, 280, 231),
            word("K", 211, 516, 217, 525),
            word("E", 222, 516, 228, 525),
            word("Y", 233, 516, 239, 525),
            word("W", 244, 516, 252, 525),
            word("O", 257, 516, 263, 525),
            word("R", 268, 516, 274, 525),
            word("D", 279, 516, 285, 525),
            word("S", 290, 516, 296, 525),
            word("adverse", 306, 531, 340, 540),
            word("event,", 344, 531, 370, 540),
            word("warfarin", 500, 531, 545, 540),
            word("1", 46, 571, 53, 581),
            word("|", 59, 571, 62, 581),
            word("I", 68, 571, 72, 581),
            word("N", 76, 571, 81, 581),
            word("T", 85, 571, 90, 581),
            word("R", 94, 571, 99, 581),
            word("O", 103, 571, 108, 581),
            word("D", 112, 571, 117, 581),
            word("U", 121, 571, 126, 581),
            word("C", 130, 571, 135, 581),
            word("T", 139, 571, 144, 581),
            word("I", 148, 571, 152, 581),
            word("O", 156, 571, 161, 581),
            word("N", 165, 571, 170, 581),
            word("The", 46, 598, 60, 607),
            word("use", 64, 598, 78, 607),
            word("asked", 306, 571, 331, 580),
            word("to", 335, 571, 344, 580),
            word("advice", 348, 571, 379, 580),
            word("TAN", 45, 24, 65, 32),
            word("AND", 69, 24, 90, 32),
            word("LEE", 94, 24, 112, 32),
            word("Downloaded", 579, 60, 585, 120, upright=False),
            word("Br J Clin Pharmacol.", 400, 748, 485, 758),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Warfarin interactions:",
        "Aims: Overview",
        "KEYWORDS\nadverse event, warfarin",
        "1 | INTRODUCTION\nThe use",
        "asked to advice",
    ]


def test_parse_methods_page_orders_columns_and_removes_overlay_and_registration() -> None:
    page = FakeLayoutPage(
        [
            word("TAN", 45, 24, 65, 32),
            word("AND", 69, 24, 90, 32),
            word("LEE", 94, 24, 112, 32),
            word("2", 45, 453, 53, 463),
            word("|", 60, 453, 63, 463),
            word("M", 70, 453, 78, 463),
            word("E", 82, 453, 89, 463),
            word("T", 93, 453, 100, 463),
            word("H", 104, 453, 112, 463),
            word("O", 116, 453, 124, 463),
            word("D", 128, 453, 136, 463),
            word("S", 140, 453, 147, 463),
            word("2.1", 45, 479, 61, 489),
            word("|", 68, 479, 71, 489),
            word("Search", 78, 479, 108, 489),
            word("strategy", 112, 479, 150, 489),
            word("PROSPERO", 45, 728, 86, 737),
            word("(Registration", 89, 728, 149, 737),
            word("No:", 152, 728, 169, 737),
            word("CRD42020169696).", 172, 728, 250, 737),
            word("2.2", 306, 52, 322, 62),
            word("|", 329, 52, 332, 62),
            word("Study", 339, 52, 365, 62),
            word("inclusion", 369, 52, 410, 62),
            word("13652125,", 579, 18, 585, 70, upright=False),
            word("Downloaded", 579, 75, 585, 140, upright=False),
            word("See", 579, 330, 585, 350, upright=False),
            word("Conditions", 579, 360, 585, 420, upright=False),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    content = "\n".join(block.content for block in extraction.blocks)
    assert content == "2 | METHODS\n2.1 | Search strategy\n2.2 | Study inclusion"
    assert "Registration" not in content
    assert "registered with" not in content
    assert "Downloaded" not in content


def test_parse_results_page_reads_columns_and_drops_figure_caption() -> None:
    page = FakeLayoutPage(
        [
            word("hierarchy", 46, 52, 90, 62),
            word("follows", 94, 52, 130, 62),
            word("3", 46, 245, 53, 255),
            word("|", 60, 245, 63, 255),
            word("R", 70, 245, 77, 255),
            word("E", 81, 245, 88, 255),
            word("S", 92, 245, 99, 255),
            word("U", 103, 245, 110, 255),
            word("L", 114, 245, 121, 255),
            word("T", 125, 245, 132, 255),
            word("S", 136, 245, 143, 255),
            word("included", 307, 52, 345, 62),
            word("studies", 349, 52, 383, 62),
            word("4", 307, 258, 314, 268),
            word("|", 321, 258, 324, 268),
            word("O", 331, 258, 338, 268),
            word("U", 342, 258, 349, 268),
            word("T", 353, 258, 360, 268),
            word("C", 364, 258, 371, 268),
            word("O", 375, 258, 382, 268),
            word("M", 386, 258, 394, 268),
            word("E", 398, 258, 405, 268),
            word("S", 409, 258, 416, 268),
            word("F", 46, 727, 53, 737),
            word("I", 57, 727, 60, 737),
            word("G", 64, 727, 72, 737),
            word("U", 76, 727, 83, 737),
            word("R", 87, 727, 94, 737),
            word("E", 98, 727, 105, 737),
            word("1", 112, 727, 119, 737),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=3,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "hierarchy follows\n3 | RESULTS",
        "included studies\n4 | OUTCOMES",
    ]
    assert "FIGURE" not in "\n".join(block.content for block in extraction.blocks)


def test_parse_is_scoped_to_exact_document() -> None:
    extraction = WarfarinReviewLayoutParser().parse(
        page=FakeLayoutPage([]),
        page_number=1,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-another",
    )

    assert extraction is None


def test_parse_outcomes_page_separates_body_from_table_and_drops_citations() -> None:
    page = FakeLayoutPage(
        [
            word("probable,", 46, 52, 85, 62),
            word("these", 250, 104, 275, 114),
            word("were", 279, 104, 300, 114),
            word("described", 307, 52, 350, 62),
            word("the", 354, 52, 369, 62),
            word("inhibition", 373, 52, 417, 62),
            word("7,23,28–30,33,42,49–51", 420, 51, 490, 57, size=5.3),
            word("TABLE", 47, 133, 80, 143, fontname="Bold"),
            word("1", 84, 133, 90, 143, fontname="Bold"),
            word("Probability", 53, 153, 90, 163, fontname="Bold"),
            word("Potentiation", 115, 162, 165, 172, fontname="Bold"),
            word("Inhibition", 234, 162, 274, 172, fontname="Bold"),
            word("No", 372, 162, 383, 172, fontname="Bold"),
            word("effect", 387, 162, 410, 172, fontname="Bold"),
            word("Highly", 53, 177, 80, 187),
            word("probable", 53, 187, 88, 197),
            word("broccoli", 234, 177, 269, 187),
            word("folic", 393, 177, 411, 187),
            word("acid", 415, 177, 432, 187),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=4,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    text = "\n".join(block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT)
    tables = [block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE]
    assert text == "probable,\nthese were\ndescribed the inhibition"
    assert "7,23,28" not in text
    assert len(tables) == 1
    assert tables[0].headers == [
        "Probability scale",
        "Potentiation",
        "Inhibition",
        "No effect",
    ]
    assert tables[0].rows[0].cells == [
        "Highly probable",
        "",
        "broccoli",
        "folic acid",
    ]


def test_parse_table_two_page_preserves_rows_without_polluting_body() -> None:
    page = FakeLayoutPage(
        [
            word("dietary", 47, 51, 75, 61),
            word("supplement", 79, 51, 122, 61),
            word("as", 307, 51, 316, 61),
            word("well", 320, 51, 338, 61),
            word("TABLE", 47, 148, 80, 158, fontname="Bold"),
            word("2", 84, 148, 90, 158, fontname="Bold"),
            word("Alcohol", 52, 203, 83, 213),
            word("No", 160, 203, 171, 213),
            word("effect", 175, 203, 198, 213),
            word("Moderate", 274, 203, 311, 213),
            word("case", 323, 203, 342, 213),
            word("reports", 346, 203, 375, 213),
            word("Alcohol", 437, 203, 468, 213),
            word("is", 479, 203, 486, 213),
            word("thought", 490, 203, 520, 213),
            word("52,53", 376, 202, 392, 208, size=5.3),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=5,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    text = "\n".join(block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT)
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert text == "dietary supplement\nas well"
    assert table.rows[0].cells == [
        "Alcohol",
        "No effect",
        "Moderate",
        "case reports",
        "Alcohol is thought",
    ]


def test_parse_discussion_page_uses_verified_cross_column_order() -> None:
    page = FakeLayoutPage(
        [
            word("distribution", 47, 299, 90, 309),
            word("or", 94, 299, 103, 309),
            word("patients", 307, 390, 340, 400),
            word("taking", 344, 390, 369, 400),
            word("warfarin.", 373, 390, 410, 400),
            word("Another", 307, 415, 340, 425),
            word("common", 344, 415, 377, 425),
            word("source", 381, 415, 408, 425),
            word("FIGURE", 47, 705, 80, 715, fontname="Bold"),
            word("2", 84, 705, 90, 715, fontname="Bold"),
        ]
    )

    extraction = WarfarinReviewLayoutParser().parse(
        page=page,
        page_number=17,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-299edbe35f581616",
    )

    assert extraction is not None
    text_blocks = [block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT]
    assert text_blocks == [
        "distribution or",
        "patients taking warfarin.",
        "Another common source",
    ]
    assert "FIGURE" not in "\n".join(text_blocks)
