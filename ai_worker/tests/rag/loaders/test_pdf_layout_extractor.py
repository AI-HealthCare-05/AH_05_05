from ai_worker.rag.loaders.pdf_layout_extractor import (
    PdfLayoutExtraction,
    PdfLayoutExtractor,
)
from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


class FakeTableRow:
    def __init__(self, cells):
        self.cells = cells


class FakeTable:
    def __init__(self, bbox, rows, *, cell_rows=()):
        self.bbox = bbox
        self._rows = rows
        self.rows = [FakeTableRow(cells) for cells in cell_rows]

    def extract(self, **kwargs):
        return self._rows


class FakeLayoutPage:
    width = 600.0
    height = 800.0

    def __init__(self, *, words, tables=()):
        self._words = words
        self._tables = list(tables)
        self.extract_word_calls = []

    def extract_words(self, **kwargs):
        self.extract_word_calls.append(kwargs)
        return self._words

    def find_tables(self, table_settings=None):
        return self._tables


class FakeBorderlessTablePage(FakeLayoutPage):
    def __init__(self, *, words, table):
        super().__init__(words=words)
        self._borderless_table = table
        self.table_settings: list[dict | None] = []

    def find_tables(self, table_settings=None):
        self.table_settings.append(table_settings)
        if table_settings and table_settings.get("vertical_strategy") == "text":
            return [self._borderless_table]
        return []


class FakeDeduplicatedPage(FakeLayoutPage):
    def __init__(self, *, duplicated_words, clean_words):
        super().__init__(words=duplicated_words)
        self._clean_page = FakeLayoutPage(words=clean_words)
        self.dedupe_calls = 0
        self.dedupe_kwargs = {}

    def dedupe_chars(self, **kwargs):
        self.dedupe_calls += 1
        self.dedupe_kwargs = kwargs
        return self._clean_page


class FakeScientificTablePage(FakeLayoutPage):
    def __init__(self, *, words, text_table, line_table):
        super().__init__(words=words)
        self._text_table = text_table
        self._line_table = line_table

    def find_tables(self, table_settings=None):
        if not table_settings:
            return []
        if table_settings.get("horizontal_strategy") == "lines":
            return [self._line_table]
        return [self._text_table]


class FakeRuledTablePage(FakeLayoutPage):
    def __init__(self, *, words, default_tables, text_table, line_table):
        super().__init__(words=words)
        self._default_tables = default_tables
        self._text_table = text_table
        self._line_table = line_table

    def find_tables(self, table_settings=None):
        if not table_settings:
            return self._default_tables
        if table_settings.get("horizontal_strategy") == "lines":
            return [self._line_table]
        return [self._text_table]


class FakeLayeredTextPage(FakeLayoutPage):
    def __init__(self, *, layers):
        self._layers = layers
        words = [item for layer_words in layers.values() for item in layer_words]
        super().__init__(words=words)
        self.chars = [
            {"fontname": fontname}
            for fontname, layer_words in layers.items()
            for item in layer_words
            for _ in item["text"]
        ]

    def filter(self, predicate):
        retained = {
            fontname: layer_words for fontname, layer_words in self._layers.items() if predicate({"fontname": fontname})
        }
        return FakeLayeredTextPage(layers=retained)


class FakeOrderedLayerPage(FakeLayeredTextPage):
    def __init__(self, *, layers, events=None):
        super().__init__(layers=layers)
        self.events = events if events is not None else []

    def filter(self, predicate):
        self.events.append("filter")
        retained = {
            fontname: layer_words for fontname, layer_words in self._layers.items() if predicate({"fontname": fontname})
        }
        return FakeOrderedLayerPage(
            layers=retained,
            events=self.events,
        )

    def dedupe_chars(self, **kwargs):
        self.events.append("dedupe")
        return self


def word(text: str, x0: float, top: float, x1: float, bottom: float):
    return {
        "text": text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
    }


def test_extract_uses_tight_word_spacing_for_latin_body_text() -> None:
    page = FakeLayoutPage(
        words=[
            word("Drug", 40, 30, 68, 42),
            word("nutrient", 72, 30, 125, 42),
            word("interactions", 129, 30, 205, 42),
        ]
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert extraction.blocks[0].content == "Drug nutrient interactions"
    assert page.extract_word_calls == [
        {
            "return_chars": True,
            "x_tolerance": 1,
            "y_tolerance": 3,
        }
    ]


def test_extract_restores_superscript_scientific_notation_from_character_geometry() -> None:
    scientific_notation = word("105", 40, 30, 58, 42)
    scientific_notation["chars"] = [
        {"text": "1", "size": 10.0, "top": 30.0},
        {"text": "0", "size": 10.0, "top": 30.0},
        {"text": "5", "size": 7.5, "top": 28.0},
    ]
    square_centimeters = word("cm2", 62, 30, 82, 42)
    square_centimeters["chars"] = [
        {"text": "c", "size": 10.0, "top": 30.0},
        {"text": "m", "size": 10.0, "top": 30.0},
        {"text": "2", "size": 7.5, "top": 28.0},
    ]
    page = FakeLayoutPage(
        words=[
            word("2.7", 10, 30, 25, 42),
            word("×", 29, 30, 36, 42),
            scientific_notation,
            word("platelets", 86, 30, 130, 42),
            word("adherent/cm2", 134, 30, 205, 42),
            square_centimeters,
        ]
    )

    extraction = PdfLayoutExtractor().extract(page)
    content = "\n".join(block.content for block in extraction.blocks)

    assert "2.7 × 10^5" in content
    assert "cm^2" in content


def test_extract_does_not_mark_small_latin_glyphs_as_superscript() -> None:
    mixed_font_word = word("Clinical", 10, 30, 55, 42)
    mixed_font_word["chars"] = [
        {"text": "C", "size": 10.0, "top": 30.0},
        {"text": "l", "size": 7.5, "top": 28.0},
        {"text": "i", "size": 10.0, "top": 30.0},
        {"text": "n", "size": 10.0, "top": 30.0},
        {"text": "i", "size": 10.0, "top": 30.0},
        {"text": "c", "size": 10.0, "top": 30.0},
        {"text": "a", "size": 7.5, "top": 28.0},
        {"text": "l", "size": 10.0, "top": 30.0},
    ]
    page = FakeLayoutPage(words=[mixed_font_word])

    extraction = PdfLayoutExtractor().extract(page)

    assert extraction.blocks[0].content == "Clinical"


def test_extract_removes_duplicate_text_layer_from_different_font_family() -> None:
    page = FakeLayeredTextPage(
        layers={
            "AAAAAA+URWPalladioL-Roma": [
                word("Medication", 160, 90, 220, 100),
                word("can", 224, 90, 242, 100),
                word("affect", 246, 90, 280, 100),
                word("nutrient", 284, 90, 330, 100),
                word("absorption", 334, 90, 395, 100),
                word("through", 399, 90, 440, 100),
                word("several", 444, 90, 480, 100),
                word("mechanisms.", 484, 90, 555, 100),
            ],
            "BBBBBB+PalatinoLinotype": [
                word("Medicationcanaffectnutrientabsorption", 240, 82, 475, 92),
                word("throughseveralmechanisms.", 240, 94, 405, 104),
            ],
        }
    )

    extraction = PdfLayoutExtractor().extract(page)
    content = "\n".join(block.content for block in extraction.blocks)

    assert content == ("Medication can affect nutrient absorption through several mechanisms.")


def test_extract_removes_duplicate_font_layer_before_deduplicating_glyphs() -> None:
    page = FakeOrderedLayerPage(
        layers={
            "AAAAAA+URWPalladioL-Roma": [
                word("adequate", 40, 30, 90, 42),
                word("micronutrients", 94, 30, 180, 42),
                word("sustain", 184, 30, 230, 42),
                word("body", 234, 30, 263, 42),
                word("functions", 267, 30, 320, 42),
                word("but", 324, 30, 343, 42),
                word("also", 347, 30, 373, 42),
                word("today", 377, 30, 410, 42),
            ],
            "BBBBBB+PalatinoLinotype": [
                word(
                    "adequaemicronutrientstosusainbodyfunctionsbualsotoday",
                    40,
                    30,
                    410,
                    42,
                ),
            ],
        }
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert page.events[0] == "filter"
    assert page.events[-1] == "dedupe"
    assert extraction.blocks[0].content == ("adequate micronutrients sustain body functions but also today")


def test_extract_separates_table_words_and_serializes_rows() -> None:
    page = FakeLayoutPage(
        words=[
            word("Results", 40, 30, 100, 42),
            word("Ingredient", 40, 110, 110, 122),
            word("Result", 300, 110, 345, 122),
            word("Iron", 40, 140, 68, 152),
            word("Reduced", 300, 140, 355, 152),
            word("absorption", 360, 140, 430, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 180),
                [
                    ["Ingredient", "Result"],
                    ["Iron", "Reduced absorption"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    text = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT)
    assert table.headers == ["Ingredient", "Result"]
    assert table.rows[0].cells == ["Iron", "Reduced absorption"]
    assert table.content == "Ingredient=Iron | Result=Reduced absorption"
    assert "Iron" not in text.content
    assert text.content == "Results"
    assert extraction.warnings == []


def test_extract_deduplicates_overlapping_character_layer() -> None:
    page = FakeDeduplicatedPage(
        duplicated_words=[word("LLiimmiittaattiioonnss", 40, 30, 180, 42)],
        clean_words=[word("Limitations", 40, 30, 110, 42)],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert page.dedupe_calls == 1
    assert page.dedupe_kwargs == {"tolerance": 2, "extra_attrs": ()}
    assert extraction.blocks[0].content == "Limitations"
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE not in extraction.warnings


def test_extract_prefers_line_bounded_rows_for_scientific_table() -> None:
    text_table = FakeTable(
        (30, 100, 800, 300),
        [
            ["Nutriment", "Effect", "Number", "Study Design", "Patients", "Dosage", "Result", "References"],
            ["", "", "", "", "", "2.5 mg warfarin/day", "INR jumped", ""],
            ["niacin (B3)", "synergistic effect", "1", "case report", "1", "", "", "[271]"],
        ],
    )
    line_table = FakeTable(
        (30, 100, 800, 300),
        [
            ["Nutriment", "Effect", "Number", "Study Design", "Patients", "Dosage", "Result", "References"],
            [
                "niacin (B3)",
                "synergistic effect",
                "1",
                "case report",
                "1",
                "2.5 mg warfarin/day + 1000 mg Niacin/day",
                "INR jumped from 18 months stable INR 2.0-2.9 to 12.3 in a week",
                "[271]",
            ],
        ],
    )
    page = FakeScientificTablePage(
        words=[
            word("Table", 40, 70, 75, 82),
            word("2.", 78, 70, 88, 82),
            word("niacin", 40, 140, 85, 152),
        ],
        text_table=text_table,
        line_table=line_table,
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert len(table.rows) == 1
    assert table.rows[0].cells[0] == "niacin (B3)"
    assert "INR jumped from 18 months stable INR 2.0-2.9 to 12.3 in a week" in table.content


def test_extract_prefers_valid_default_ruled_table_over_fragmented_candidates() -> None:
    default_table = FakeTable(
        (30, 100, 500, 240),
        [
            ["Drug or Drug Class", "Effect"],
            ["Calcium Carbonate", "May reduce levothyroxine absorption."],
        ],
    )
    fragmented_table = FakeTable(
        (30, 100, 500, 240),
        [
            ["Drug", "or", "Drug", "Class", "Effect"],
            ["Calcium", "Carbonate", "May", "reduce", "absorption"],
        ],
    )
    page = FakeRuledTablePage(
        words=[
            word("Table", 40, 70, 75, 82),
            word("2.", 78, 70, 88, 82),
            word("Interactions", 92, 70, 160, 82),
            word("Calcium", 40, 140, 90, 152),
        ],
        default_tables=[default_table],
        text_table=fragmented_table,
        line_table=fragmented_table,
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == ["Drug or Drug Class", "Effect"]
    assert table.rows[0].cells == [
        "Calcium Carbonate",
        "May reduce levothyroxine absorption.",
    ]
    assert table.table_title == "Interactions"


def test_extract_preserves_first_row_of_headerless_continued_table() -> None:
    page = FakeLayoutPage(
        words=[
            word("Salicylates", 40, 140, 100, 152),
            word("inhibit", 300, 140, 340, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 200),
                [
                    ["Salicylates (> 2 g/day)", "Salicylates inhibit T4 and T3 binding."],
                    ["Other drugs", "May displace thyroid hormones."],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == ["열 1", "열 2"]
    assert table.rows[0].cells == [
        "Salicylates (> 2 g/day)",
        "Salicylates inhibit T4 and T3 binding.",
    ]

    inherited = PdfLayoutExtractor().inherit_continued_table_headers(
        extraction,
        ["Drug or Drug Class", "Effect"],
    )

    continued = next(block for block in inherited.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert continued.headers == ["Drug or Drug Class", "Effect"]
    assert "Drug or Drug Class=Salicylates (> 2 g/day)" in continued.content


def test_extract_keeps_spanning_table_context_as_metadata() -> None:
    page = FakeLayoutPage(
        words=[
            word("Potential", 40, 110, 95, 122),
            word("impact:", 100, 110, 145, 122),
            word("Drug", 40, 140, 68, 152),
            word("Effect", 300, 140, 345, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 220),
                [
                    ["Potential impact: Concurrent use may reduce efficacy.", ""],
                    ["Drug or Drug Class", "Effect"],
                    ["Calcium Carbonate", "May reduce absorption."],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == ["Drug or Drug Class", "Effect"]
    assert table.table_super_headers == ["Potential impact: Concurrent use may reduce efficacy."]
    assert table.rows[0].cells == [
        "Calcium Carbonate",
        "May reduce absorption.",
    ]


def test_extract_rejects_single_column_false_table() -> None:
    false_table = FakeTable(
        (30, 100, 500, 300),
        [["Body sentence"], ["Another body sentence"]],
    )
    page = FakeLayoutPage(
        words=[
            word("Table", 40, 70, 75, 82),
            word("1.", 78, 70, 88, 82),
            word("Body", 40, 140, 75, 152),
            word("sentence", 78, 140, 140, 152),
        ],
        tables=[false_table],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert all(block.kind != KnowledgeContentKind.TABLE for block in extraction.blocks)


def test_extract_removes_publication_sidebar_without_removing_article_body() -> None:
    page = FakeLayoutPage(
        words=[
            word("Citation:", 35, 200, 90, 212),
            word("Renaud", 95, 200, 145, 212),
            word("Drug-nutrient", 300, 200, 390, 212),
            word("interaction", 395, 200, 460, 212),
            word("Received:", 35, 220, 95, 232),
            word("2024", 100, 220, 130, 232),
            word("Main", 300, 220, 335, 232),
            word("content", 340, 220, 395, 232),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)
    content = "\n".join(block.content for block in extraction.blocks)

    assert "Citation" not in content
    assert "Renaud" not in content
    assert "Drug-nutrient interaction" in content
    assert "Main content" in content


def test_extract_keeps_keywords_and_introduction_beside_publication_sidebar() -> None:
    page = FakeLayoutPage(
        words=[
            word("Citation:", 35, 200, 90, 212),
            word("Renaud", 95, 200, 145, 212),
            word("interaction;", 165, 204, 230, 216),
            word("triage", 235, 204, 275, 216),
            word("theory", 280, 204, 320, 216),
            word("Received:", 35, 220, 95, 232),
            word("2024", 100, 220, 130, 232),
            word("1.", 165, 225, 175, 237),
            word("Introduction", 180, 225, 260, 237),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)
    content = "\n".join(block.content for block in extraction.blocks)

    assert "Citation" not in content
    assert "Received" not in content
    assert "interaction; triage theory" in content
    assert "1. Introduction" in content


def test_inherit_continued_table_headers_replaces_placeholders() -> None:
    extraction = PdfLayoutExtraction(
        blocks=[
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TABLE,
                order=0,
                bbox=KnowledgeBoundingBox(
                    x0=30,
                    top=100,
                    x1=500,
                    bottom=200,
                ),
                content="열 1=niacin | 열 2=synergistic effect",
                headers=["열 1", "열 2"],
                rows=[
                    KnowledgeTableRow(
                        cells=["niacin", "synergistic effect"],
                    )
                ],
                column_count=2,
            )
        ],
        warnings=[],
    )

    inherited = PdfLayoutExtractor().inherit_continued_table_headers(
        extraction,
        ["Nutriment", "Effect"],
    )

    table = inherited.blocks[0]
    assert table.headers == ["Nutriment", "Effect"]
    assert table.content == "Nutriment=niacin | Effect=synergistic effect"


def test_extract_inherits_primary_entity_for_continued_table_row() -> None:
    page = FakeLayoutPage(
        words=[
            word("Nutriment", 40, 110, 110, 122),
            word("Result", 300, 110, 345, 122),
            word("iron", 40, 140, 68, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 200),
                [
                    ["Nutriment", "Result"],
                    ["iron", "lower ferritin"],
                    ["", "increased anemia"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.rows[1].cells == ["iron", "increased anemia"]
    assert "Nutriment=iron | Result=increased anemia" in table.content


def test_extract_marks_multiple_primary_entities_in_one_row_unsafe() -> None:
    page = FakeLayoutPage(
        words=[
            word("Nutriment", 40, 110, 110, 122),
            word("Result", 300, 110, 345, 122),
            word("calciferol", 40, 140, 100, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 200),
                [
                    ["Nutriment", "Result"],
                    ["calciferol (D)\nK vitamin", "mixed results"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert "MULTI_ENTITY_ROW" in table.validation_errors
    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE in extraction.warnings


def test_extract_separates_scientific_table_caption_and_super_headers() -> None:
    headers = [
        "Nutriment",
        "Effect on Nutrient Status or Function",
        "Number",
        "Study Design",
        "Number of Patients",
        "Dosage",
        "Result",
        "References",
    ]
    page = FakeLayoutPage(
        words=[
            word("Effect", 40, 50, 75, 62),
            word("on", 80, 50, 95, 62),
            word("Nutrient", 100, 50, 160, 62),
            word("Human", 240, 70, 285, 82),
            word("Studies", 290, 70, 340, 82),
            word("Table", 40, 90, 75, 102),
            word("2.", 80, 90, 92, 102),
            word("Summary", 96, 90, 150, 102),
        ],
        tables=[
            FakeTable(
                (30, 100, 800, 220),
                [
                    headers,
                    [
                        "niacin (B3)",
                        "synergistic effect",
                        "1",
                        "case report",
                        "1",
                        "1000 mg/day",
                        "INR increased",
                        "[271]",
                    ],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    text = "\n".join(block.content for block in extraction.blocks if block.kind == KnowledgeContentKind.TEXT)
    assert table.table_title == "Summary"
    assert table.table_super_headers == [
        "Effect on Nutrient",
        "Human Studies",
    ]
    assert "Table 2" not in text
    assert "Human Studies" not in text


def test_extract_restores_scientific_rows_from_cell_coordinates() -> None:
    headers = [
        "Nutriment",
        "Effect on Nutrient Status or Function",
        "Number",
        "Study Design",
        "Number of Patients",
        "Dosage",
        "Result",
        "References",
    ]
    cells = [
        (30, 100, 120, 130),
        (120, 100, 240, 130),
        (240, 100, 310, 130),
        (310, 100, 420, 130),
        (420, 100, 500, 130),
        (500, 100, 640, 130),
        (640, 100, 780, 130),
        (780, 100, 810, 130),
    ]
    body_cells = [(x0, 130, x1, 260) for x0, _, x1, _ in cells]
    page = FakeLayoutPage(
        words=[
            word("calciferol", 40, 140, 90, 152),
            word("(D)", 94, 140, 112, 152),
            word("low", 130, 140, 150, 152),
            word("status", 155, 140, 190, 152),
            word("1", 250, 140, 258, 152),
            word("normal", 650, 140, 690, 152),
            word("vascular", 130, 170, 180, 182),
            word("calcification", 184, 170, 230, 182),
            word("4", 250, 170, 258, 182),
            word("K", 45, 190, 54, 202),
            word("vitamin", 58, 190, 100, 202),
            word("bone", 130, 200, 155, 212),
            word("density-pediatrics", 160, 200, 230, 212),
            word("1", 250, 200, 258, 212),
            word("bone", 130, 225, 155, 237),
            word("density-adults", 160, 225, 225, 237),
            word("1", 250, 225, 258, 237),
        ],
        tables=[
            FakeTable(
                (30, 100, 810, 260),
                [
                    headers,
                    [
                        "calciferol (D)\nK vitamin",
                        "low status\nvascular calcification\nbone density-pediatrics\nbone density-adults",
                        "1\n4\n1\n1",
                        "",
                        "",
                        "",
                        "normal",
                        "",
                    ],
                ],
                cell_rows=[cells, body_cells],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert [row.cells[:3] for row in table.rows] == [
        ["calciferol (D)", "low status", "1"],
        ["K vitamin", "vascular calcification", "4"],
        ["K vitamin", "bone density-pediatrics", "1"],
        ["K vitamin", "bone density-adults", "1"],
    ]
    assert "MULTI_ENTITY_ROW" not in table.validation_errors
    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE not in extraction.warnings


def test_extract_marks_residual_duplicated_glyph_line_unsafe() -> None:
    page = FakeLayoutPage(
        words=[
            word(
                "Human ccoohhoorrtts tsutuddieisesa raerere",
                40,
                140,
                400,
                152,
            ),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in extraction.warnings


def test_extract_marks_corrupted_single_letter_fragments_unsafe() -> None:
    page = FakeLayoutPage(
        words=[
            word(
                "should contain the adequa e micronutrients to sus a n body functions b t also",
                40,
                140,
                500,
                152,
            ),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in extraction.warnings


def test_extract_accepts_scientific_single_letter_labels() -> None:
    page = FakeLayoutPage(
        words=[
            word(
                "Vitamins A, D, E, and K were reviewed; R and S enantiomers were compared.",
                40,
                140,
                500,
                152,
            ),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE not in extraction.warnings


def test_extract_marks_mismatched_table_row_unsafe() -> None:
    page = FakeLayoutPage(
        words=[
            word("Ingredient", 40, 110, 110, 122),
            word("Result", 300, 110, 345, 122),
            word("Iron", 40, 140, 68, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 180),
                [
                    ["Ingredient", "Result"],
                    ["Iron"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE in extraction.warnings
    table = extraction.blocks[0]
    assert "COLUMN_COUNT_MISMATCH" in table.validation_errors


def test_extract_uses_text_table_strategy_only_when_table_caption_exists() -> None:
    table = FakeTable(
        (30, 100, 500, 180),
        [["Ingredient", "Result"], ["Iron", "Reduced"]],
    )
    page = FakeBorderlessTablePage(
        words=[
            word("Table1.", 40, 70, 92, 82),
            word("Ingredient", 40, 110, 110, 122),
            word("Result", 300, 110, 345, 122),
            word("Iron", 40, 140, 68, 152),
            word("Reduced", 300, 140, 355, 152),
        ],
        table=table,
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert any(block.kind == KnowledgeContentKind.TABLE for block in extraction.blocks)
    assert page.table_settings[0] is None
    assert page.table_settings[1]["vertical_strategy"] == "text"


def test_extract_keeps_source_numbers_and_units_in_their_cells() -> None:
    page = FakeLayoutPage(
        words=[
            word("Group", 40, 110, 80, 122),
            word("Dose", 300, 110, 335, 122),
            word("Calcium", 40, 140, 95, 152),
            word("500", 300, 140, 324, 152),
            word("mg", 330, 140, 350, 152),
        ],
        tables=[
            FakeTable(
                (30, 100, 500, 180),
                [["Group", "Dose"], ["Calcium", "500 mg"]],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert extraction.blocks[0].content == "Group=Calcium | Dose=500 mg"
    assert extraction.warnings == []


def test_extract_orders_spanning_title_before_columns_and_footer() -> None:
    page = FakeLayoutPage(
        words=[
            word("Article", 40, 20, 90, 32),
            word("title", 100, 20, 135, 32),
            word("Left", 40, 100, 70, 112),
            word("one", 75, 100, 100, 112),
            word("Left", 40, 130, 70, 142),
            word("two", 75, 130, 100, 142),
            word("Right", 330, 95, 370, 107),
            word("one", 375, 95, 400, 107),
            word("Right", 330, 125, 370, 137),
            word("two", 375, 125, 400, 137),
            word("Page", 40, 760, 70, 772),
            word("footer", 80, 760, 120, 772),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert [block.content for block in extraction.blocks] == [
        "Article title",
        "Left one\nLeft two",
        "Right one\nRight two",
        "Page footer",
    ]
    assert KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT in (extraction.warnings)


def test_extract_expands_same_as_reference_with_previous_row_context() -> None:
    page = FakeLayoutPage(
        words=[],
        tables=[
            FakeTable(
                (30, 100, 500, 200),
                [
                    ["Nutrient", "Recommendation"],
                    ["Calcium", "Separate by 4 hours"],
                    ["Iron", "Same as calcium supplement"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert "참조 행: Nutrient=Calcium | Recommendation=Separate by 4 hours" in (extraction.blocks[0].content)


def test_extract_does_not_treat_non_overlapping_left_and_right_lines_as_columns() -> None:
    page = FakeLayoutPage(
        words=[
            word("Left", 40, 20, 70, 32),
            word("heading", 75, 20, 130, 32),
            word("Centered", 240, 240, 300, 252),
            word("content", 305, 240, 350, 252),
            word("Right", 330, 500, 370, 512),
            word("footer", 375, 500, 420, 512),
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT not in (extraction.warnings)
    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE not in (extraction.warnings)
    assert [block.content for block in extraction.blocks] == [
        "Left heading",
        "Centered content",
        "Right footer",
    ]


def test_extract_marks_long_unspaced_body_token_as_unsafe() -> None:
    merged_text = "Numberofpapersreportinginteractions" * 4
    page = FakeLayoutPage(
        words=[word(merged_text, 40, 100, 500, 112)],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.READING_ORDER_UNSAFE in (extraction.warnings)


def test_extract_marks_incorrect_numeric_total_as_unsafe() -> None:
    page = FakeLayoutPage(
        words=[],
        tables=[
            FakeTable(
                (30, 100, 500, 200),
                [
                    ["Group", "Cases"],
                    ["A", "6"],
                    ["B", "8"],
                    ["Total", "15"],
                ],
            )
        ],
    )

    extraction = PdfLayoutExtractor().extract(page)

    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE in (extraction.warnings)
    assert "TOTAL_MISMATCH" in extraction.blocks[0].validation_errors
