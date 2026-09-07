from ai_worker.rag.loaders.levothyroxine_calcium_review_layout_parser import (
    LevothyroxineCalciumReviewLayoutParser,
)
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


class FakeCroppedPage(FakeLayoutPage):
    def __init__(self, words, *, extracted_text: str):
        super().__init__(words)
        self._extracted_text = extracted_text
        self._crop_bbox = None

    def crop(self, bbox):
        self._crop_bbox = bbox
        return self

    def extract_text(self, **kwargs):
        if self._crop_bbox is not None and self._crop_bbox[1] >= 690:
            return ""
        return self._extracted_text


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


def test_parse_calcium_iron_review_orders_columns_and_excludes_running_matter() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Int.", 57, 42, 70, 51, size=8.7),
            layout_word("DOI", 57, 742, 74, 751, size=8.7),
            layout_word("Article", 358, 85, 398, 101, size=16),
            layout_word("Calcium", 271, 120, 391, 159, size=38),
            layout_word("and", 401, 120, 456, 159, size=38),
            layout_word("Iron", 466, 120, 524, 159, size=38),
            layout_word("Absorption", 76, 162, 237, 200, size=38),
            layout_word("–", 247, 162, 266, 200, size=38),
            layout_word("Mechanisms", 275, 162, 460, 200, size=38),
            layout_word("and", 470, 162, 525, 200, size=38),
            layout_word("Public", 167, 203, 257, 241, size=38),
            layout_word("Health", 267, 203, 366, 241, size=38),
            layout_word("Relevance", 376, 203, 525, 241, size=38),
            layout_word("Bo", 443, 251, 459, 267, size=16),
            layout_word("Lönnerdal", 463, 251, 524, 267, size=16),
            layout_word("Abstract:", 71, 340, 120, 350),
            layout_word("Calcium", 124, 340, 170, 350),
            layout_word("may", 174, 340, 198, 350),
            layout_word("inhibit", 202, 340, 244, 350),
            layout_word("iron", 248, 340, 273, 350),
            layout_word("absorption.", 277, 340, 334, 350),
            layout_word("Introduction", 57, 600, 117, 611),
            layout_word("The", 57, 630, 77, 640),
            layout_word("adverse", 81, 630, 124, 640),
            layout_word("effects", 128, 630, 166, 640),
            layout_word("are", 170, 630, 190, 640),
            layout_word("well", 194, 630, 218, 640),
            layout_word("known.", 222, 630, 265, 640),
            layout_word("Vulnerable", 312, 630, 369, 640),
            layout_word("populations", 373, 630, 438, 640),
            layout_word("need", 442, 630, 470, 640),
            layout_word("support.", 474, 630, 522, 640),
            layout_word("Address", 0, 550, 10, 600, upright=False),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-016c81c9a3e29ebd",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Calcium and Iron\nAbsorption – Mechanisms and\nPublic Health Relevance",
        "Abstract: Calcium may inhibit iron absorption.",
        "Introduction\nThe adverse effects are well known.",
        "Vulnerable populations need support.",
    ]


def test_parse_zinc_iron_study_skips_author_footnotes_and_tables() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Supplemental", 34, 106, 129, 121, size=15),
            layout_word("Zinc", 133, 106, 163, 121, size=15),
            layout_word("Lowers", 168, 106, 219, 121, size=15),
            layout_word("Carmen", 70, 149, 112, 161, size=12),
            layout_word("Donangelo", 116, 149, 195, 161, size=12),
            layout_word("ABSTRACT", 34, 230, 90, 242, size=12),
            layout_word("Zinc", 94, 230, 120, 242, size=12),
            layout_word("and", 124, 230, 144, 242, size=12),
            layout_word("iron", 148, 230, 172, 242, size=12),
            layout_word("compete.", 176, 230, 224, 242, size=12),
            layout_word("Zinc", 34, 450, 58, 460, size=10),
            layout_word("and", 62, 450, 82, 460, size=10),
            layout_word("iron", 86, 450, 110, 460, size=10),
            layout_word("interact.", 114, 450, 168, 460, size=10),
            layout_word("SUBJECTS", 300, 570, 354, 580, size=10),
            layout_word("AND", 358, 570, 382, 580, size=10),
            layout_word("METHODS", 386, 570, 442, 580, size=10),
            layout_word("Subjects", 300, 595, 345, 605, size=10),
            layout_word("were", 349, 595, 376, 605, size=10),
            layout_word("enrolled.", 380, 595, 431, 605, size=10),
            layout_word("1", 33, 635, 38, 645, size=8),
            layout_word("Presented", 42, 635, 82, 645, size=8),
            layout_word("TABLE", 300, 640, 340, 650, size=10),
            layout_word("1", 344, 640, 349, 650, size=10),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-ce2c45272c5bd272",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "Supplemental Zinc Lowers",
        "ABSTRACT Zinc and iron compete.",
        "Zinc and iron interact.",
        "SUBJECTS AND METHODS\nSubjects were enrolled.",
    ]


def test_parse_vitamin_c_copper_study_keeps_verified_materials_and_cell_culture() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Biomolecules", 30, 56, 94, 65, size=9),
            layout_word("2.", 72, 448, 84, 460, size=11),
            layout_word("Materials", 88, 448, 138, 460, size=11),
            layout_word("and", 142, 448, 164, 460, size=11),
            layout_word("Methods", 168, 448, 220, 460, size=11),
            layout_word("2.1.", 72, 460, 92, 472, size=10),
            layout_word("Materials", 96, 460, 145, 472, size=10),
            layout_word("Copper(II)", 72, 476, 137, 488, size=10),
            layout_word("Sulfate", 141, 476, 186, 488, size=10),
            layout_word("was", 190, 476, 213, 488, size=10),
            layout_word("purchased.", 217, 476, 276, 488, size=10),
            layout_word("2.2.", 72, 600, 92, 612, size=10),
            layout_word("Cell", 96, 600, 120, 612, size=10),
            layout_word("Culture", 124, 600, 165, 612, size=10),
            layout_word("Rat", 72, 612, 89, 624, size=10),
            layout_word("cells", 93, 612, 120, 624, size=10),
            layout_word("were", 124, 612, 152, 624, size=10),
            layout_word("cultured.", 156, 612, 207, 624, size=10),
            layout_word("2", 77, 630, 83, 640, size=8),
            layout_word("of", 87, 630, 96, 640, size=8),
            layout_word("16", 100, 630, 111, 640, size=8),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-7cc01e25b07044ff",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "2. Materials and Methods\n2.1. Materials\nCopper(II) Sulfate was purchased.\n2.2. Cell Culture\nRat cells were cultured."
    ]


def test_parse_vitamin_c_copper_study_restores_spacing_and_formula_from_region_text() -> None:
    page = FakeCroppedPage(
        [],
        extracted_text=(
            "2. Materials and Methods\n"
            "2.1. Materials\n"
            "Copper(II) Sulfate (CuSO ; Cu2+) was purchased from FUJIFILM Wako Pure Chemical\n"
            "4\n"
            "Corporation (Osaka, Japan). Bovine serum albumin (BSA, Faction V) was obtained from\n"
            "Iwai Chemical Company (Tokyo, Japan).\n"
            "2.2. Cell Culture\n"
            "Rat renal tubular epithelial NRK-52E cells were purchased from the American Type\n"
            "Culture Collection (ATCC, Rockville, MD, USA). Cells were cultured in DMEM/F12 (Gibco-\n"
            "BRL, Gaithersburg, MD, USA) containing 5% FBS in 5% CO /95% air at 37 ◦C. For experiments, cells\n"
            "2\n"
            "were seeded into the culture plate."
        ),
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-7cc01e25b07044ff",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "2. Materials and Methods\n"
        "2.1. Materials\n"
        "Copper(II) Sulfate (CuSO4; Cu2+) was purchased from FUJIFILM Wako Pure Chemical "
        "Corporation (Osaka, Japan). Bovine serum albumin (BSA, Faction V) was obtained from "
        "Iwai Chemical Company (Tokyo, Japan).\n"
        "2.2. Cell Culture\n"
        "Rat renal tubular epithelial NRK-52E cells were purchased from the American Type Culture "
        "Collection (ATCC, Rockville, MD, USA). Cells were cultured in DMEM/F12 (Gibco-BRL, "
        "Gaithersburg, MD, USA) containing 5% FBS in 5% CO2/95% air at 37 ◦C. For experiments, "
        "cells were seeded into the culture plate."
    ]


def test_parse_vitamin_c_copper_study_separates_animal_experiments_from_cell_culture() -> None:
    page = FakeLayoutPage(
        [
            layout_word("2.2.", 72, 600, 92, 612, size=10),
            layout_word("Cell", 96, 600, 120, 612, size=10),
            layout_word("Culture", 124, 600, 165, 612, size=10),
            layout_word("Cells", 72, 616, 101, 628, size=10),
            layout_word("were", 105, 616, 133, 628, size=10),
            layout_word("cultured.", 137, 616, 188, 628, size=10),
            layout_word("2.3.", 72, 710, 92, 722, size=10),
            layout_word("Animal", 96, 710, 135, 722, size=10),
            layout_word("Experiments", 139, 710, 210, 722, size=10),
            layout_word("Mice", 72, 726, 96, 738, size=10),
            layout_word("were", 100, 726, 128, 738, size=10),
            layout_word("used.", 132, 726, 166, 738, size=10),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-7cc01e25b07044ff",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "2.2. Cell Culture\nCells were cultured.",
        "2.3. Animal Experiments\nMice were used.",
    ]


def test_parse_vitamin_c_iron_trial_excludes_flowchart_and_baseline_table_pages() -> None:
    page = FakeLayoutPage(
        [
            layout_word("Methods", 36, 108, 86, 120, size=12),
            layout_word("Study", 36, 128, 72, 140, size=11),
            layout_word("Design", 76, 128, 118, 140, size=11),
            layout_word("Participants", 36, 144, 106, 156, size=10),
            layout_word("were", 110, 144, 137, 156, size=10),
            layout_word("enrolled.", 141, 144, 192, 156, size=10),
            layout_word("Figure", 36, 480, 74, 492, size=10),
            layout_word("1.", 78, 480, 87, 492, size=10),
            layout_word("CONSORT", 91, 480, 144, 492, size=10),
            layout_word("530", 36, 500, 57, 512, size=10),
            layout_word("Patients", 61, 500, 108, 512, size=10),
            layout_word("assessed", 112, 500, 164, 512, size=10),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page,
        page_number=3,
        source_id="research_supplement_interactions",
        document_id="research_supplement_interactions-6152f916c012be79",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == ["Methods\nStudy Design\nParticipants were enrolled."]


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


def test_parse_levothyroxine_calcium_review_restores_columns_without_figure_or_footer() -> None:
    page_one = FakeLayoutPage(
        [
            layout_word("Journal", 60, 40, 100, 52),
            layout_word("Absorption", 105, 110, 170, 124),
            layout_word("of", 175, 110, 188, 124),
            layout_word("Levothyroxine", 193, 110, 275, 124),
            layout_word("Authors", 210, 175, 260, 187),
            layout_word("Background:", 60, 230, 125, 242),
            layout_word("Calcium", 130, 230, 180, 242),
            layout_word("Introduction", 60, 470, 125, 484),
            layout_word("Intro-left", 60, 500, 120, 512),
            layout_word("Intro-right", 315, 500, 380, 512),
            layout_word("Materials", 315, 565, 370, 577),
            layout_word("and", 375, 565, 395, 577),
            layout_word("Methods", 400, 565, 450, 577),
            layout_word("Subjects", 315, 580, 365, 592),
            layout_word("Subject-body", 315, 610, 390, 622),
            layout_word("Presented", 70, 720, 125, 732),
        ]
    )
    page_two = FakeLayoutPage(
        [
            layout_word("Subject-end", 65, 70, 130, 82),
            layout_word("Study", 65, 116, 100, 128),
            layout_word("design", 105, 116, 145, 128),
            layout_word("Design-body", 65, 145, 135, 157),
            layout_word("Assays", 65, 441, 105, 453),
            layout_word("Assay-body", 65, 470, 130, 482),
            layout_word("Statistics", 65, 591, 120, 603),
            layout_word("Statistics-body", 65, 620, 150, 632),
            layout_word("Results", 315, 60, 360, 72),
            layout_word("Result-body", 315, 90, 380, 102),
            layout_word("Discussion", 315, 450, 380, 462),
            layout_word("Discussion-body", 315, 480, 405, 492),
            layout_word("FIG.", 315, 670, 345, 682),
            layout_word("1.", 350, 670, 360, 682),
            layout_word("Figure-body", 315, 700, 385, 712),
        ]
    )

    parser = VerifiedKnowledgeLayoutParser()
    first = parser.parse(
        page=page_one,
        page_number=1,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-502801c809b5ec8d",
    )
    second = parser.parse(
        page=page_two,
        page_number=2,
        source_id="research_drug_nutrient_interactions",
        document_id="research_drug_nutrient_interactions-502801c809b5ec8d",
    )

    assert first is not None
    assert [block.content for block in first.blocks] == [
        "Absorption of Levothyroxine",
        "Background: Calcium",
        "Introduction\nIntro-left",
        "Intro-right",
        "Materials and Methods\nSubjects\nSubject-body",
    ]
    assert second is not None
    assert [block.content for block in second.blocks] == [
        "Subject-end",
        "Study design\nDesign-body",
        "Assays\nAssay-body",
        "Statistics\nStatistics-body",
        "Results\nResult-body",
        "Discussion\nDiscussion-body",
    ]


def test_clean_levothyroxine_calcium_review_restores_encoded_measurement_symbols() -> None:
    content = (
        "Synthroid (cid:2) was stored at (cid:2) 20 8 C. "
        "Samples at (cid:2) 15 minutes measured 6.49 (cid:3) 0.45 m g/dL. "
        "Lunch followed the þ 240 minute specimen. "
        "The result was ( F 1⁄4 5.37, p < 0.007)."
    )

    cleaned = LevothyroxineCalciumReviewLayoutParser._clean_content(content)

    assert cleaned == (
        "Synthroid was stored at −20°C. "
        "Samples at −15 minutes measured 6.49 ± 0.45 μg/dL. "
        "Lunch followed the +240 minute specimen. "
        "The result was (F = 5.37, p < 0.007)."
    )


def test_parse_primary_care_herb_drug_review_keeps_body_in_verified_column_order() -> None:
    page_one = FakeLayoutPage(
        [
            layout_word("TYPE", 50, 36, 75, 48),
            layout_word("Drug–herb", 222, 124, 290, 138),
            layout_word("interactions:", 295, 124, 365, 138),
            layout_word("a", 370, 124, 378, 138),
            layout_word("OPEN", 50, 160, 80, 172),
            layout_word("Primary", 222, 268, 270, 280),
            layout_word("healthcare", 275, 268, 335, 280),
            layout_word("body", 340, 268, 370, 280),
            layout_word("KEYWORDS", 222, 500, 275, 512),
            layout_word("drug–herb", 222, 512, 280, 524),
            layout_word("interactions", 285, 512, 345, 524),
            layout_word("Introduction", 222, 558, 300, 570),
            layout_word("intro-body", 222, 590, 285, 602),
            layout_word("Frontiers", 50, 800, 95, 812),
        ]
    )
    page_three = FakeLayoutPage(
        [
            layout_word("Disclosure-end", 64, 84, 145, 96),
            layout_word("Patient", 64, 248, 105, 260),
            layout_word("communication", 110, 248, 190, 260),
            layout_word("High-risk", 64, 404, 115, 416),
            layout_word("clinical", 120, 404, 160, 416),
            layout_word("High-risk-end", 310, 84, 390, 96),
            layout_word("Detection", 310, 224, 365, 236),
            layout_word("Operational", 310, 500, 375, 512),
            layout_word("Existing", 310, 728, 360, 740),
        ]
    )
    page_four = FakeLayoutPage(
        [
            layout_word("FIGURE", 64, 389, 105, 401),
            layout_word("Figure-body", 100, 410, 170, 422),
            layout_word("Existing-end", 64, 444, 140, 456),
            layout_word("Information", 64, 524, 125, 536),
            layout_word("Evidence", 64, 716, 115, 728),
            layout_word("Evidence-end", 310, 444, 385, 456),
            layout_word("Figure-sentence", 310, 504, 400, 516),
            layout_word("Recent", 310, 548, 350, 560),
        ]
    )

    parser = VerifiedKnowledgeLayoutParser()
    first = parser.parse(
        page=page_one,
        page_number=1,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-83a8fd3c37dd38e1",
    )
    third = parser.parse(
        page=page_three,
        page_number=3,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-83a8fd3c37dd38e1",
    )
    fourth = parser.parse(
        page=page_four,
        page_number=4,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-83a8fd3c37dd38e1",
    )

    assert first is not None
    assert [block.content for block in first.blocks] == [
        "Drug–herb interactions: a",
        "Primary healthcare body",
        "KEYWORDS\ndrug–herb interactions",
        "Introduction\nintro-body",
    ]
    assert third is not None
    assert [block.content for block in third.blocks] == [
        "Disclosure-end",
        "Patient communication",
        "High-risk clinical",
        "High-risk-end",
        "Detection",
        "Operational",
        "Existing",
    ]
    assert fourth is not None
    assert [block.content for block in fourth.blocks] == [
        "Existing-end",
        "Information",
        "Evidence",
        "Evidence-end",
        "Recent",
    ]


def test_parse_st_johns_wort_review_excludes_sidebar_footer_and_table() -> None:
    page_one = FakeLayoutPage(
        [
            layout_word("Interaction", 57, 183, 133, 198),
            layout_word("title", 137, 183, 170, 198),
            layout_word("Edward", 57, 225, 90, 237),
            layout_word("Mills", 94, 225, 120, 237),
            layout_word("Abstract", 57, 261, 97, 272),
            layout_word("Objective", 57, 278, 94, 287),
            layout_word("abstract-body", 98, 278, 170, 287),
            layout_word("Introduction", 57, 656, 118, 667),
            layout_word("intro-start", 57, 680, 115, 690),
            layout_word("systematic", 270, 261, 320, 270),
            layout_word("review-end", 325, 261, 380, 270),
            layout_word("Methods", 270, 317, 312, 328),
            layout_word("method-body", 270, 345, 335, 355),
            layout_word("Department", 483, 261, 535, 270),
            layout_word("millsej@mcmaster.ca", 483, 691, 543, 700),
            layout_word("flow-chart-note", 300, 746, 390, 754),
            layout_word("BMJ", 57, 785, 70, 792),
        ]
    )
    page_two = FakeLayoutPage(
        [
            layout_word("methods-end", 128, 80, 190, 90),
            layout_word("Results", 128, 196, 162, 207),
            layout_word("Search", 128, 213, 154, 221),
            layout_word("results-body", 158, 213, 225, 221),
            layout_word("Pharmacokinetic", 128, 328, 194, 336),
            layout_word("details", 198, 328, 230, 336),
            layout_word("pharmacokinetic-body", 128, 350, 240, 360),
            layout_word("Study", 341, 81, 364, 90),
            layout_word("design", 368, 81, 402, 90),
            layout_word("study-body", 341, 100, 400, 110),
            layout_word("Effects", 341, 192, 368, 201),
            layout_word("effect-body", 341, 210, 405, 220),
            layout_word("Discussion", 341, 332, 392, 342),
            layout_word("discussion-body", 341, 350, 430, 360),
            layout_word("Characteristics", 128, 520, 190, 528),
            layout_word("table-row", 128, 550, 180, 558),
            layout_word("BMJ", 300, 785, 315, 792),
        ]
    )

    parser = VerifiedKnowledgeLayoutParser()
    first = parser.parse(
        page=page_one,
        page_number=1,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-e5fcbe5d02f9650c",
    )
    second = parser.parse(
        page=page_two,
        page_number=2,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-e5fcbe5d02f9650c",
    )

    assert first is not None
    assert [block.content for block in first.blocks] == [
        "Interaction title",
        "Abstract\nObjective abstract-body",
        "Introduction\nintro-start",
        "systematic review-end",
        "Methods\nmethod-body",
    ]
    assert second is not None
    assert [block.content for block in second.blocks] == [
        "methods-end",
        "Results\nSearch results-body\nPharmacokinetic details\npharmacokinetic-body",
        "Study design\nstudy-body",
        "Effects\neffect-body",
        "Discussion\ndiscussion-body",
    ]


def test_parse_st_johns_wort_review_keeps_summary_box_after_discussion() -> None:
    page_three = FakeLayoutPage(
        [
            layout_word("discussion-left", 57, 81, 150, 90),
            layout_word("future", 57, 480, 95, 490),
            layout_word("recommendations.", 100, 480, 180, 490),
            layout_word("We", 270, 270, 282, 280),
            layout_word("used", 286, 270, 310, 280),
            layout_word("concomitant", 270, 450, 330, 460),
            layout_word("use.", 334, 450, 355, 460),
            layout_word("What", 286, 84, 308, 95),
            layout_word("is", 312, 84, 320, 95),
            layout_word("already", 324, 84, 360, 95),
            layout_word("known", 364, 84, 395, 95),
            layout_word("summary-body", 286, 105, 360, 115),
            layout_word("What", 286, 138, 308, 149),
            layout_word("this", 312, 138, 330, 149),
            layout_word("study", 334, 138, 360, 149),
            layout_word("adds", 364, 138, 390, 149),
            layout_word("adds-body", 286, 160, 340, 170),
            layout_word("Contributors:", 270, 475, 330, 483),
            layout_word("forest-plot", 57, 560, 120, 570),
            layout_word("Mean", 57, 716, 75, 724),
        ]
    )

    extraction = VerifiedKnowledgeLayoutParser().parse(
        page=page_three,
        page_number=3,
        source_id="research_herb_drug_interactions",
        document_id="research_herb_drug_interactions-e5fcbe5d02f9650c",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "discussion-left\nfuture recommendations.",
        "We used\nconcomitant use.",
        "What is already known\nsummary-body\nWhat this study adds\nadds-body",
    ]
