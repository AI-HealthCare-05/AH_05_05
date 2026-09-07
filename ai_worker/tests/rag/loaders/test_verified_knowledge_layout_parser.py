from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.rag.loaders.verified_knowledge_layout_parser import (
    VerifiedKnowledgeLayoutParser,
)
from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


class FakeLayoutPage:
    width = 612.0
    height = 792.0

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kwargs):
        return self._words


def layout_word(
    text: str,
    x0: float,
    top: float,
    x1: float,
    bottom: float,
    *,
    upright: bool = True,
    size: float = 10.0,
):
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


def build_text(content: str, *, order: int) -> KnowledgePageBlock:
    return KnowledgePageBlock(
        kind=KnowledgeContentKind.TEXT,
        order=order,
        bbox=KnowledgeBoundingBox(x0=0, top=order * 10, x1=100, bottom=order * 10 + 9),
        content=content,
    )


def build_table(
    *,
    order: int,
    title: str | None,
    headers: list[str] | None = None,
    rows: list[list[str]],
) -> KnowledgePageBlock:
    headers = headers or ["Drug or Drug Class", "Effect"]
    return KnowledgePageBlock(
        kind=KnowledgeContentKind.TABLE,
        order=order,
        bbox=KnowledgeBoundingBox(x0=0, top=order * 10, x1=100, bottom=order * 10 + 9),
        content="\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(headers, row, strict=True)) for row in rows
        ),
        headers=headers,
        rows=[KnowledgeTableRow(cells=row) for row in rows],
        column_count=len(headers),
        table_title=title,
        validation_errors=["MULTI_ENTITY_ROW"],
    )


def test_repair_fda_page_nine_keeps_table_note_and_group_context() -> None:
    impact = (
        "Potential impact (below): Administration of these agents with LEVO-T "
        "results in an initial transient increase in FT4."
    )
    absorption = build_table(
        order=0,
        title="Drugs That May Decrease T4 Absorption (Hypothyroidism)",
        rows=[
            [
                "Other drugs:; Proton Pump Inhibitors; Sucralfate; Antacids; "
                "- Aluminum & Magnesium; Hydroxides; - Simethicone",
                "Shared effect",
            ]
        ],
    )
    transport = build_table(
        order=2,
        title="Drugs That May Alter T4 and Triiodothyronine (T3) Serum Transport Without",
        rows=[
            [
                "Clofibrate; Estrogen-containing oral; contraceptives",
                "Transport effect",
            ]
        ],
    )
    extraction = PdfLayoutExtraction(
        blocks=[
            absorption,
            build_text(
                "Affecting Free Thyroxine (FT4) Concentration (Euthyroidism)",
                order=1,
            ),
            transport,
            build_text(impact, order=3),
        ],
        warnings=[KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE],
    )

    repaired = VerifiedKnowledgeLayoutParser().repair(
        extraction=extraction,
        page_number=9,
        source_id="fda_regulatory_drug_labels",
    )

    assert all(impact not in block.content for block in repaired.blocks)
    assert all(
        block.content.strip() != "Affecting Free Thyroxine (FT4) Concentration (Euthyroidism)"
        for block in repaired.blocks
    )
    repaired_tables = [block for block in repaired.blocks if block.kind == KnowledgeContentKind.TABLE]
    assert repaired_tables[1].table_super_headers == [impact]
    assert repaired_tables[1].table_title == (
        "Drugs That May Alter T4 and Triiodothyronine (T3) Serum Transport "
        "Without Affecting Free Thyroxine (FT4) Concentration (Euthyroidism)"
    )
    assert repaired_tables[0].rows[-1].cells[0] == (
        "Other drugs: Proton Pump Inhibitors; Other drugs: Sucralfate; "
        "Other drugs: Antacids - Aluminum & Magnesium Hydroxides; "
        "Other drugs: Antacids - Simethicone"
    )
    assert repaired_tables[1].rows[0].cells[0] == ("Clofibrate; Estrogen-containing oral contraceptives")
    assert repaired.warnings == []


def test_repair_fda_table_titles_link_descriptions_across_pages() -> None:
    dosage_table = build_table(
        order=0,
        title=None,
        headers=["Tablet Strength", "Tablet Color/Shape", "Tablet Markings"],
        rows=[["25 mcg", "Orange/Round", "25/TV"]],
    )
    supplied_table = build_table(
        order=0,
        title=None,
        headers=[
            "Strength (mcg)",
            "Color/Shape",
            "Tablet Markings",
            "NDC# for bottles of 90",
            "NDC # for bottles of 1000",
        ],
        rows=[["25", "Orange/Round", "25/TV", "0007-4485-13", "0007-4485-19"]],
    )

    repaired_dosage = VerifiedKnowledgeLayoutParser().repair(
        extraction=PdfLayoutExtraction(blocks=[dosage_table], warnings=[]),
        page_number=6,
        source_id="fda_regulatory_drug_labels",
    )
    repaired_supplied = VerifiedKnowledgeLayoutParser().repair(
        extraction=PdfLayoutExtraction(
            blocks=[supplied_table],
            warnings=[KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE],
        ),
        page_number=16,
        source_id="fda_regulatory_drug_labels",
    )

    assert repaired_dosage.blocks[0].table_title == ("LEVO-T tablets are available as follows")
    assert repaired_supplied.blocks[0].table_title == (
        "LEVO-T (levothyroxine sodium, USP) tablets are supplied as follows"
    )


def test_repair_fda_pediatric_table_moves_footnote_out_of_age_rows() -> None:
    malformed_footnote = (
        "a. The dose should be adjusted based on clinical response and "
        "laboratory parameters [see Dosage and; Administration (2.4) and "
        "Use in Specific Populations (8.4)]."
    )
    repaired_footnote = (
        "a. The dose should be adjusted based on clinical response and "
        "laboratory parameters [see Dosage and Administration (2.4) and "
        "Use in Specific Populations (8.4)]."
    )
    table = build_table(
        order=0,
        title="LEVO-T Dosing Guidelines for Pediatric Hypothyroidism",
        headers=["AGE", "Daily Dose Per Kg Body Weighta"],
        rows=[
            ["Growth and puberty complete", "1.6 mcg/kg/day"],
            [malformed_footnote, ""],
        ],
    )

    repaired = VerifiedKnowledgeLayoutParser().repair(
        extraction=PdfLayoutExtraction(blocks=[table], warnings=[]),
        page_number=5,
        source_id="fda_regulatory_drug_labels",
    )

    assert [row.cells for row in repaired.blocks[0].rows] == [["Growth and puberty complete", "1.6 mcg/kg/day"]]
    assert repaired.blocks[0].table_super_headers == [repaired_footnote]
    assert malformed_footnote not in repaired.blocks[0].content


def test_parse_vitamin_d_review_keeps_only_title_and_abstract_on_front_page() -> None:
    page = FakeLayoutPage(
        [
            layout_word("HHS", 131, 21, 178, 43),
            layout_word("Author", 131, 44, 171, 58),
            layout_word("Manuscript", 40, 200, 50, 270, upright=False),
            layout_word("Published", 90, 79, 129, 89),
            layout_word("Drug-vitamin", 90, 130, 160, 144),
            layout_word("D", 164, 130, 172, 144),
            layout_word("interactions:", 176, 130, 240, 144),
            layout_word("Kim", 90, 161, 110, 175),
            layout_word("Robien,", 114, 161, 155, 175),
            layout_word("Abstract", 90, 387, 139, 399),
            layout_word("Evidence", 108, 407, 154, 419),
            layout_word("was", 158, 407, 178, 419),
            layout_word("reviewed.", 182, 407, 232, 419),
            layout_word("Correspondence", 90, 713, 152, 721),
            layout_word("to:", 156, 713, 168, 721),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-80c3d674cbc86d03",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Drug-vitamin D interactions:",
        "Abstract\nEvidence was reviewed.",
    ]


def test_parse_vitamin_d_review_removes_running_matter_and_preserves_sections() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Robien", 78, 39, 101, 47),
            layout_word("Page", 501, 39, 516, 47),
            layout_word("2", 518, 39, 522, 47),
            layout_word("Keywords", 90, 75, 137, 85),
            layout_word("vitamin", 108, 92, 145, 102),
            layout_word("D;", 149, 92, 160, 102),
            layout_word("drug-nutrient", 164, 92, 225, 102),
            layout_word("interactions", 229, 92, 280, 102),
            layout_word("Introduction", 90, 127, 160, 139),
            layout_word("Vitamin", 150, 149, 190, 159),
            layout_word("D,", 194, 149, 205, 159),
            layout_word("a", 209, 149, 215, 159),
            layout_word("steroid", 219, 149, 250, 159),
            layout_word("hormone", 254, 149, 295, 159),
            layout_word("Author", 40, 200, 50, 250, upright=False),
            layout_word("Manuscript", 40, 255, 50, 330, upright=False),
            layout_word("Nutr", 159, 715, 176, 723),
            layout_word("Author", 212, 715, 235, 723),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-80c3d674cbc86d03",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Keywords: vitamin D; drug-nutrient interactions",
        "Introduction\nVitamin D, a steroid hormone",
    ]


def test_parse_vitamin_d_review_excludes_back_matter_from_page_fourteen() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Supplementary", 90, 65, 177, 77),
            layout_word("Material", 180, 65, 226, 77),
            layout_word("Acknowledgments", 90, 116, 196, 128),
            layout_word("References", 90, 163, 155, 175),
            layout_word("Cohen-Lahav", 163, 184, 220, 194),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=14,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-80c3d674cbc86d03",
    )

    assert extraction is not None
    assert extraction.blocks == []


def test_parse_statins_vitamin_d_review_orders_front_page_without_author_metadata() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Review", 35, 100, 75, 112),
            layout_word("Statins,", 35, 120, 85, 136),
            layout_word("Vitamin", 89, 120, 140, 136),
            layout_word("D", 144, 120, 155, 136),
            layout_word("Authors", 35, 170, 90, 182),
            layout_word("Abstract", 165, 320, 220, 334),
            layout_word("Statins", 165, 345, 205, 357),
            layout_word("are", 209, 345, 227, 357),
            layout_word("widely", 231, 345, 270, 357),
            layout_word("used", 274, 345, 302, 357),
            layout_word("Academic", 35, 550, 85, 562),
            layout_word("Editor", 89, 550, 125, 562),
            layout_word("Keywords:", 165, 600, 225, 612),
            layout_word("endothelial", 229, 600, 295, 612),
            layout_word("inflammation", 299, 600, 375, 612),
            layout_word("modulation", 379, 600, 440, 612),
            layout_word("1.", 165, 665, 176, 679),
            layout_word("Introduction", 180, 665, 250, 679),
            layout_word("Statins", 165, 690, 205, 702),
            layout_word("are", 209, 690, 227, 702),
            layout_word("prescribed", 231, 690, 290, 702),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-186668a2a92b533c",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Review\nStatins, Vitamin D",
        "Abstract\nStatins are widely used\nKeywords: endothelial inflammation modulation",
        "1. Introduction\nStatins are prescribed",
    ]


def test_parse_statins_vitamin_d_review_excludes_figure_and_table_regions() -> None:
    parser = VerifiedKnowledgeLayoutParser()
    page_five = FakeLayoutPage(
        [
            layout_word("Figure", 165, 400, 200, 412),
            layout_word("1.", 204, 400, 215, 412),
            layout_word("Understanding", 165, 540, 245, 552),
            layout_word("these", 249, 540, 280, 552),
            layout_word("interactions", 284, 540, 350, 552),
        ]
    )
    page_seven = FakeLayoutPage(
        [
            layout_word("Narrative", 165, 100, 220, 112),
            layout_word("before", 224, 100, 265, 112),
            layout_word("Table", 35, 250, 70, 262),
            layout_word("cell", 74, 250, 98, 262),
            layout_word("3.", 165, 550, 176, 564),
            layout_word("Changes", 180, 550, 230, 564),
        ]
    )

    fifth = parser.parse(
        page=page_five,
        page_number=5,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-186668a2a92b533c",
    )
    seventh = parser.parse(
        page=page_seven,
        page_number=7,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-186668a2a92b533c",
    )

    assert fifth is not None
    assert [block.content for block in fifth.blocks] == ["Understanding these interactions"]
    assert seventh is not None
    assert [block.content for block in seventh.blocks] == ["Narrative before", "3. Changes"]


def test_parse_statins_vitamin_d_review_restores_first_four_column_table() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Narrative", 170, 170, 225, 182),
            layout_word("Mechanism/Pathway", 42, 223, 150, 234),
            layout_word("Statin Mechanism", 173, 223, 275, 234),
            layout_word("Vitamin D Mechanism", 303, 223, 415, 234),
            layout_word("Representative Evidence", 434, 219, 552, 230),
            layout_word("Anti-inflammatory/immuno-", 42, 251, 158, 262),
            layout_word("modulation", 42, 261, 100, 272),
            layout_word(
                "↓ IL-6, CRP, TNF- α; suppress macrophage activation in plaques",
                173,
                246,
                292,
                272,
            ),
            layout_word(
                "VDR activation; suppress pro-inflammatory genes; ↑ IL-10",
                303,
                246,
                424,
                272,
            ),
            layout_word(
                "Review of clinical and experimental studies on cardiovascular inflammation [1]",
                434,
                242,
                555,
                272,
            ),
            layout_word("Section 3", 170, 560, 225, 572),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=7,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-186668a2a92b533c",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == [
        "Mechanism/Pathway",
        "Statin Mechanism",
        "Vitamin D Mechanism",
        "Representative Evidence (Study Type/Population)",
    ]
    assert table.rows[0].cells == [
        "Anti-inflammatory/immunomodulation",
        "↓ IL-6, CRP, TNF-α; suppress macrophage activation in plaques",
        "VDR activation; suppress pro-inflammatory genes; ↑ IL-10",
        "Review of clinical and experimental studies on cardiovascular inflammation [1]",
    ]


def test_parse_statins_vitamin_d_review_restores_second_four_column_table() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Clinical evidence", 170, 420, 250, 432),
            layout_word("Statin(s) Studied", 42, 473, 150, 484),
            layout_word("Study Design", 173, 473, 260, 484),
            layout_word("Effect on Vitamin D Levels", 303, 473, 450, 484),
            layout_word("Remarks/Limitations", 463, 473, 558, 484),
            layout_word("Rosuvastatin", 42, 495, 120, 506),
            layout_word("Observational study. [34]", 173, 495, 270, 506),
            layout_word(
                "Substantial increase (~14 to 36 ng/mL over 8 weeks)",
                303,
                489,
                450,
                506,
            ),
            layout_word("Possible confounding, small sample", 463, 489, 558, 506),
            layout_word("Key Point", 170, 740, 225, 752),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=8,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-186668a2a92b533c",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == [
        "Statin(s) Studied",
        "Study Design",
        "Effect on Vitamin D Levels",
        "Remarks/Limitations",
    ]
    assert table.rows[0].cells == [
        "Rosuvastatin",
        "Observational study [34]",
        "Substantial increase (~14 to 36 ng/mL over 8 weeks)",
        "Possible confounding, small sample",
    ]
