from ai_worker.rag.loaders.herb_drug_review_layout_parser import (
    HerbDrugReviewLayoutParser,
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
):
    return {
        "text": text,
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": bottom,
        "upright": upright,
    }


def rotated_word_with_gaps(text: str, *, x0: float, x1: float, top: float):
    cursor = top
    chars = []
    for character in reversed(text):
        if character == " ":
            cursor += 2.5
            continue
        chars.append(
            {
                "text": character,
                "top": cursor,
                "bottom": cursor + 3.0,
            }
        )
        cursor += 3.0
    return {
        "text": text.replace(" ", "")[::-1],
        "x0": x0,
        "top": top,
        "x1": x1,
        "bottom": cursor,
        "upright": False,
        "chars": chars,
    }


def test_parse_two_column_body_in_reading_order_and_drops_page_edges() -> None:
    page = FakeLayoutPage(
        [
            word("Evidence", 280, 27, 320, 35),
            word("1057", 545, 27, 562, 35),
            word("left", 123, 80, 145, 91),
            word("first", 149, 80, 175, 91),
            word("right", 374, 80, 402, 91),
            word("second", 406, 80, 445, 91),
            word("downloaded", 585, 100, 593, 145, upright=False),
            word("footer", 74, 760, 110, 770),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=2,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    assert [block.content for block in extraction.blocks] == [
        "left first",
        "right second",
    ]


def test_parse_first_page_omits_author_line_from_search_content() -> None:
    page = FakeLayoutPage(
        [
            word("Study title", 123, 50, 200, 60),
            word(
                "H.-H. Tsai,1,2 H.-W. Lin,1,2,3 A. Simon Pickard,3,4,5 H.-Y. Tsai,1,2 G. B. Mahady5",
                123,
                70,
                540,
                80,
            ),
            word("SUMMARY", 123, 95, 180, 105),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=1,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    content = "\n".join(block.content for block in extraction.blocks)
    assert "Study title" in content
    assert "SUMMARY" in content
    assert "H.-H. Tsai" not in content


def test_parse_major_interaction_table_into_three_columns() -> None:
    page = FakeLayoutPage(
        [
            word("HDS", 60, 85, 74, 93),
            word("Drugs", 134, 85, 153, 93),
            word("Potential consequences/reactions", 430, 85, 545, 93),
            word("Alfalfa", 60, 127, 80, 135),
            word("Warfarin", 134, 127, 180, 135),
            word("(21,33)", 181, 127, 215, 135),
            word("Decreased effect of warfarin", 430, 127, 545, 135),
            word("Arginine", 60, 160, 85, 168),
            word("Enalapril", 134, 160, 180, 168),
            word("Hypotensive effects", 430, 160, 520, 168),
            word("Spironolactone", 134, 171, 192, 179),
            word("Risk of hyperkalemia", 430, 171, 520, 179),
            word("Ginkgo", 60, 190, 95, 198),
            word("Aspirin, clopidogrel", 134, 190, 230, 198),
            word("Risk of bleeding", 430, 190, 510, 198),
            word("ticlopidine, warfarin", 134, 201, 240, 209),
            word("Risperidone", 134, 212, 200, 220),
            word("Risperidone adverse effects", 430, 212, 550, 220),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=10,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.headers == [
        "Herb or dietary supplement",
        "Drug",
        "Potential consequence or reaction",
    ]
    assert table.rows[0].cells == [
        "Alfalfa",
        "Warfarin",
        "Decreased effect of warfarin",
    ]
    assert table.rows[1].cells == [
        "Arginine",
        "Enalapril",
        "Hypotensive effects",
    ]
    assert table.rows[2].cells == [
        "Arginine",
        "Spironolactone",
        "Risk of hyperkalemia",
    ]
    assert table.rows[3].cells == [
        "Ginkgo",
        "Aspirin, clopidogrel ticlopidine, warfarin",
        "Risk of bleeding",
    ]
    assert table.rows[4].cells == [
        "Ginkgo",
        "Risperidone",
        "Risperidone adverse effects",
    ]


def test_parse_continued_major_table_preserves_left_edge_hds() -> None:
    page = FakeLayoutPage(
        [
            word("Vitamin", 39, 110, 64, 118),
            word("E", 65, 110, 70, 118),
            word("Aspirin", 140, 110, 180, 118),
            word("Increased risk of bleeding", 430, 110, 550, 118),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=11,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.rows[0].cells == [
        "Vitamin E",
        "Aspirin",
        "Increased risk of bleeding",
    ]


def test_parse_st_johns_wort_continuation_page_inherits_hds() -> None:
    page = FakeLayoutPage(
        [
            word("Warfarin", 140, 110, 180, 118),
            word("Decreased anticoagulant effect", 430, 110, 560, 118),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=13,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.rows[0].cells == [
        "St John’s wort",
        "Warfarin",
        "Decreased anticoagulant effect",
    ]


def test_parse_major_table_appends_effect_only_continuation() -> None:
    page = FakeLayoutPage(
        [
            word("Temsirolimus", 140, 110, 190, 118),
            word("Effect of sirolimus, the", 430, 110, 550, 118),
            word("active metabolite of temsirolimus", 430, 121, 560, 129),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=13,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.rows[0].cells == [
        "St John’s wort",
        "Temsirolimus",
        "Effect of sirolimus, the active metabolite of temsirolimus",
    ]


def test_parse_rotated_evidence_table_restores_logical_cells() -> None:
    page = FakeLayoutPage(
        [
            word("ecnerefeR", 127, 671, 135, 704, upright=False),
            word("SDH", 127, 619, 135, 633, upright=False),
            word("noitacideM", 127, 492, 135, 529, upright=False),
            word(")rebmun(ledomlaminA", 127, 359, 135, 436, upright=False),
            word("ngisedydutS", 127, 301, 135, 343, upright=False),
            word("serusaememoctuO", 127, 220, 135, 268, upright=False),
            word("tnednepedesoD", 127, 165, 135, 201, upright=False),
            word("sgnidnfirojaM", 127, 102, 135, 150, upright=False),
            word(")16(.lategnaihC", 147, 651, 155, 704, upright=False),
            word(")laro(atabolairareuP", 147, 566, 155, 633, upright=False),
            word(")suonevartni(etaxertohteM", 147, 460, 155, 529, upright=False),
            word(")puorghcaeni7(staR", 147, 369, 155, 436, upright=False),
            word("ngisedlellaraP", 147, 300, 155, 343, upright=False),
            word("citenikocamrahP", 147, 220, 155, 268, upright=False),
            word("seY", 147, 190, 155, 201, upright=False),
            word("yltnacfiingisatabolairareuP", 147, 68, 155, 150, upright=False),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=4,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = extraction.blocks[0]
    assert table.kind == KnowledgeContentKind.TABLE
    assert table.rows[0].cells == [
        "Chiang et al.",
        "Pueraria lobata (oral)",
        "Methotrexate (intravenous)",
        "Rats (7 in each group)",
        "Parallel design",
        "Pharmacokinetic",
        "Yes",
        "Pueraria lobata significantly",
    ]


def test_parse_rotated_evidence_table_restores_spaces_from_character_gaps() -> None:
    page = FakeLayoutPage(
        [
            word(")16(.lategnaihC", 147, 651, 155, 704, upright=False),
            rotated_word_with_gaps(
                "Water extract of crude",
                x0=147,
                x1=155,
                top=566,
            ),
            rotated_word_with_gaps(
                "Methotrexate oral",
                x0=147,
                x1=155,
                top=460,
            ),
            rotated_word_with_gaps(
                "decreased the elimination of methotrexate",
                x0=147,
                x1=155,
                top=68,
            ),
            word("eoD", 158, 680, 166, 704, upright=False),
            rotated_word_with_gaps(
                "Pueraria lobatasigniﬁcantly",
                x0=158,
                x1=166,
                top=68,
            ),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=4,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    row = extraction.blocks[0].rows[0]
    assert row.cells[1] == "Water extract of crude"
    assert row.cells[2] == "Methotrexate oral"
    assert row.cells[7] == "decreased the elimination of methotrexate"
    assert extraction.blocks[0].rows[1].cells[7] == ("Pueraria lobata significantly")


def test_parse_rotated_evidence_table_repairs_verified_scientific_name_boundaries() -> None:
    page = FakeLayoutPage(
        [
            word(")16(.lategnaihC", 147, 651, 155, 704, upright=False),
            word(")laro(abolibogkniG", 147, 566, 155, 633, upright=False),
            word(
                "Andrographispaniculataand"[::-1],
                147,
                68,
                155,
                150,
                upright=False,
            ),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=4,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    row = extraction.blocks[0].rows[0]
    assert row.cells[1] == "Ginkgo biloba (oral)"
    assert row.cells[7] == "Andrographis paniculata and"


def test_parse_rotated_table_continuation_uses_table_three_and_skips_heading() -> None:
    page = FakeLayoutPage(
        [
            word("deunitnoC3elbaT", 215, 650, 223, 704, upright=False),
            word(")88(.lateeoD", 235, 660, 243, 704, upright=False),
            word("troWsnhoJtS", 235, 585, 243, 633, upright=False),
            word("nirafraW", 235, 490, 243, 529, upright=False),
            word("laicifeneb", 235, 90, 243, 150, upright=False),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=7,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = extraction.blocks[0]
    assert table.table_title == "HDS-drug interaction evidence studies (Table 3)"
    assert all("Table3Continued" not in cell for row in table.rows for cell in row.cells)
    assert table.rows[0].cells[0] == "Doe et al."


def test_parse_rotated_table_merges_split_author_and_citation_lines() -> None:
    page = FakeLayoutPage(
        [
            word("demmahoM", 348, 660, 356, 704, upright=False),
            word("stcudorplaicremmoC", 348, 565, 356, 633, upright=False),
            word("nirafraW", 348, 490, 356, 529, upright=False),
            word("laicifeneb", 348, 90, 356, 150, upright=False),
            word(".late ludbA", 359, 650, 367, 704, upright=False),
            word("laro", 359, 565, 367, 633, upright=False),
            word(")19(", 370, 671, 378, 704, upright=False),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=7,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = extraction.blocks[0]
    assert len(table.rows) == 1
    assert table.rows[0].cells[0] == "Mohammed Abdul et al."


def test_parse_contraindication_table_uses_verified_column_boundaries() -> None:
    page = FakeLayoutPage(
        [
            word("Acid", 214, 100, 235, 108),
            word("peptic", 238, 100, 270, 108),
            word("disease", 273, 100, 315, 108),
            word("Betaine", 331, 100, 370, 108),
            word("hydrochloride", 373, 100, 443, 108),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=14,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.table_title == ("Contraindication relationships for herbs and dietary supplements")
    assert table.headers == [
        "Class of contraindications",
        "Contraindications",
        "HDS which should be avoided and/or not recommended",
    ]
    assert table.rows[0].cells == [
        "Gastrointestinal Diseases (n = 25, 16.4%)",
        "Acid peptic disease",
        "Betaine hydrochloride",
    ]


def test_parse_contraindication_table_keeps_condition_on_offset_line() -> None:
    page = FakeLayoutPage(
        [
            word("Aloe vera", 331, 403.3, 390, 411),
            word("disease", 253, 406.1, 300, 414),
            word("Cardiac", 229, 406.4, 251, 414),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=14,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert table.rows[0].cells == [
        "Cardiovascular Disease (n = 14, 9.2%)",
        "Cardiac disease",
        "Aloe vera",
    ]


def test_parse_contraindication_table_disambiguates_others_by_parent_class() -> None:
    page = FakeLayoutPage(
        [
            word("Others", 250, 131, 279, 138),
            word("Aloe vera", 331, 131, 390, 138),
            word("Others", 244, 195, 286, 203),
            word("Echinacea", 331, 195, 380, 203),
        ]
    )

    extraction = HerbDrugReviewLayoutParser().parse(
        page=page,
        page_number=14,
        source_id="research_herb_drug_interactions",
    )

    assert extraction is not None
    table = next(block for block in extraction.blocks if block.kind == KnowledgeContentKind.TABLE)
    assert [row.cells for row in table.rows] == [
        [
            "Gastrointestinal Diseases (n = 25, 16.4%)",
            "Others",
            "Aloe vera",
        ],
        [
            "Neurologic Disorders (n = 22, 14.5%)",
            "Others",
            "Echinacea",
        ],
    ]


def test_parse_excludes_references_and_appendices() -> None:
    parser = HerbDrugReviewLayoutParser()

    for page_number in range(16, 24):
        extraction = parser.parse(
            page=FakeLayoutPage([word("irrelevant", 50, 100, 100, 110)]),
            page_number=page_number,
            source_id="research_herb_drug_interactions",
        )
        assert extraction is not None
        assert extraction.blocks == []


def test_parse_ignores_other_sources() -> None:
    extraction = HerbDrugReviewLayoutParser().parse(
        page=FakeLayoutPage([]),
        page_number=2,
        source_id="another_source",
    )

    assert extraction is None
