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
            " | ".join(
                f"{header}={cell}" for header, cell in zip(headers, row, strict=True)
            )
            for row in rows
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
    repaired_tables = [
        block for block in repaired.blocks if block.kind == KnowledgeContentKind.TABLE
    ]
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
    assert repaired_tables[1].rows[0].cells[0] == (
        "Clofibrate; Estrogen-containing oral contraceptives"
    )
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

    assert repaired_dosage.blocks[0].table_title == (
        "LEVO-T tablets are available as follows"
    )
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

    assert [row.cells for row in repaired.blocks[0].rows] == [
        ["Growth and puberty complete", "1.6 mcg/kg/day"]
    ]
    assert repaired.blocks[0].table_super_headers == [repaired_footnote]
    assert malformed_footnote not in repaired.blocks[0].content
