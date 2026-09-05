from ai_worker.rag.normalizers.knowledge_normalizer import (
    KnowledgeNormalizer,
    TextQualityStatus,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


def build_pages(*contents: str) -> list[KnowledgePage]:
    metadata = KnowledgeMetadata(
        source_id="kpicia_adverse_case_report",
        document_id="case-1",
        title="독사조신 복용 후 어지러움",
        provider="약학정보원",
        access_scope=KnowledgeAccessScope.DEMO_RESTRICTED,
        document_type=KnowledgeDocumentType.ADVERSE_CASE_REPORT,
        dataset_version="pilot-v1",
    )
    return [
        KnowledgePage(
            content=content,
            metadata=metadata,
            page_number=index,
        )
        for index, content in enumerate(contents, start=1)
    ]


def build_regulatory_pages(*contents: str) -> list[KnowledgePage]:
    pages = build_pages(*contents)
    metadata = pages[0].metadata.model_copy(
        update={
            "source_id": "fda_regulatory_drug_labels",
            "document_type": KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        }
    )
    return [page.model_copy(update={"metadata": metadata}) for page in pages]


def build_research_pages(*contents: str) -> list[KnowledgePage]:
    pages = build_pages(*contents)
    metadata = pages[0].metadata.model_copy(
        update={
            "source_id": "research_drug_nutrient_interactions",
            "document_type": KnowledgeDocumentType.RESEARCH_ARTICLE,
            "title": (
                "Medications and Food Interfering with the Bioavailability of Levothyroxine: A Systematic Review"
            ),
        }
    )
    return [page.model_copy(update={"metadata": metadata}) for page in pages]


def test_normalize_pages_removes_repeated_header_and_page_numbers() -> None:
    pages = build_pages(
        "대한약사회 환자안전약물관리본부\n환자 정보: 72세 남성\n1/3",
        "대한약사회 환자안전약물관리본부\n이상사례: 어지러움\n2/3",
        "대한약사회 환자안전약물관리본부\n평가 의견: 상당히 확실함\n3/3",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "대한약사회 환자안전약물관리본부" not in normalized[0].content
    assert "1/3" not in normalized[0].content
    assert normalized[0].content == "환자 정보: 72세 남성"
    assert normalized[2].content == "평가 의견: 상당히 확실함"


def test_assess_quality_requires_ocr_for_long_unspaced_text() -> None:
    report = KnowledgeNormalizer().assess_quality("인삼과와파린을함께복용하면출혈위험이증가할수있습니다" * 10)

    assert report.status == TextQualityStatus.OCR_REQUIRED
    assert "LONG_UNSPACED_RUN" in report.reason_codes


def test_assess_quality_passes_normal_korean_text() -> None:
    report = KnowledgeNormalizer().assess_quality(
        "비타민 B6는 단백질과 아미노산 이용에 필요합니다. "
        "섭취 후 손발 저림이 발생하면 전문가와 상담하세요. "
        "이 문서는 기능성 내용과 섭취 시 주의사항을 제공합니다."
    )

    assert report.status == TextQualityStatus.PASS
    assert report.reason_codes == []


def test_assess_pages_quality_uses_total_document_length() -> None:
    pages = build_pages(
        "환자 정보와 복용 의약품을 확인한 정상적인 첫 번째 페이지입니다.",
        "이상사례와 평가 의견을 설명한 정상적인 두 번째 페이지입니다.",
    )

    report = KnowledgeNormalizer().assess_pages_quality(pages)

    assert report.status == TextQualityStatus.PASS
    assert report.character_count > 60


def test_normalize_pages_removes_pdf_download_audit_footer() -> None:
    pages = build_pages(
        "Calcium can affect short-term iron absorption.\n"
        "https://example.org/article.pdf - Saturday, August 22, 2026 "
        "5:00:06 AM - IP Address:203.0.113.10"
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("Calcium can affect short-term iron absorption.")


def test_normalize_pages_removes_document_production_footer_and_banner() -> None:
    pages = build_pages(
        "와파린과 비타민 K의 상호작용을 설명합니다.\n"
        "NATIONAL INSTITUTE OF FOOD AND DRUG SAFETY / www.nifds.go.kr\n"
        "약과음식안내서-최종.indd 10 2016-10-14 오후 12:45:15"
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("와파린과 비타민 K의 상호작용을 설명합니다.")


def test_normalize_pages_removes_variable_page_header() -> None:
    pages = build_pages(
        "Nutrients 2024, 16, 950 1 of 3\nAbstract\nCalcium and iron were evaluated.",
        "Nutrients 2024, 16, 950 2 of 3\nMethods\nParticipants received supplements.",
        "Nutrients 2024, 16, 950 3 of 3\nResults\nAbsorption was measured.",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert all("Nutrients 2024" not in page.content for page in normalized)
    assert normalized[0].content.startswith("Abstract")


def test_normalize_pages_repairs_soft_hyphen_and_wrapped_words() -> None:
    pages = build_pages(
        "A concomitant medicine was evaluated.\n"
        "The concomi-\n"
        "tant use changed absorption. A drug-\n"
        "nutrient interaction was reported. Co\u00adadministration was avoided."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "concomitant use" in normalized[0].content
    assert "drug-nutrient interaction" in normalized[0].content
    assert "Co\u00adadministration" not in normalized[0].content
    assert "Coadministration" in normalized[0].content


def test_normalize_pages_applies_manually_verified_text_replacements() -> None:
    page = build_pages("A mi-\nnor stroke was reported.")[0]
    page = page.model_copy(
        update={
            "blocks": [
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TEXT,
                    order=0,
                    bbox=KnowledgeBoundingBox(
                        x0=10,
                        top=10,
                        x1=500,
                        bottom=50,
                    ),
                    content="A mi-\nnor stroke was reported.",
                )
            ]
        }
    )

    normalized = KnowledgeNormalizer().normalize_pages(
        [page],
        verified_text_replacements={"mi-nor": "minor"},
    )

    assert normalized[0].content == "A minor stroke was reported."
    assert normalized[0].blocks[0].content == "A minor stroke was reported."


def test_normalize_pages_repairs_spaced_wrapped_latin_word() -> None:
    pages = build_pages(
        "Hydroxide is named elsewhere in this document.\nAluminum and magnesium hydro -\nxide may affect absorption."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "magnesium hydroxide" in normalized[0].content
    assert "hydro -\nxide" not in normalized[0].content


def test_normalize_pages_repairs_split_latin_word_only_when_verified() -> None:
    pages = build_pages(
        "Different outcomes and specific cases were reported.\n"
        "The effect was di fferent in tissue-speci fic interactions."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "effect was different" in normalized[0].content
    assert "tissue-specific interactions" in normalized[0].content


def test_normalize_pages_repairs_split_capitalized_word_only_when_verified() -> None:
    pages = build_pages("The document refers to Table 1 in the results.\nT able 1 Summary of interaction evidence")

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "Table 1 Summary" in normalized[0].content
    assert "T able" not in normalized[0].content


def test_normalize_pages_removes_fda_reference_footer() -> None:
    pages = build_pages("LEVO-T may interact with calcium carbonate.\nRevised: 12/2017\nReference ID: 4190666")

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("LEVO-T may interact with calcium carbonate.")


def test_normalize_pages_skips_fda_table_of_contents_page() -> None:
    pages = build_pages(
        "FULL PRESCRIBING INFORMATION: CONTENTS*\n1 INDICATIONS AND USAGE\n2 DOSAGE AND ADMINISTRATION",
        "FULL PRESCRIBING INFORMATION\n1 INDICATIONS AND USAGE\nLEVO-T is indicated as replacement therapy.",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert len(normalized) == 1
    assert normalized[0].page_number == 2
    assert "replacement therapy" in normalized[0].content


def test_normalize_pages_skips_fda_highlights_before_full_information() -> None:
    pages = build_regulatory_pages(
        "HIGHLIGHTS OF PRESCRIBING INFORMATION\nINDICATIONS AND USAGE\nSummary duplicated from the full label. (1)",
        "FULL PRESCRIBING INFORMATION: CONTENTS*\n1 INDICATIONS AND USAGE",
        "FULL PRESCRIBING INFORMATION\n1 INDICATIONS AND USAGE\nLEVO-T is indicated as replacement therapy.",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert [page.page_number for page in normalized] == [3]
    assert "Summary duplicated" not in normalized[0].content


def test_normalize_pages_removes_fda_cross_references_but_keeps_doses() -> None:
    pages = build_regulatory_pages(
        "7 DRUG INTERACTIONS\n"
        "Thyroid hormones do not readily cross the placental barrier "
        "[see Use in Specific Populations (8.1)].\n"
        "The response may change (see Tables 2-5 below).\n"
        "Administer 2 to 3 mcg/kg/day and monitor every 6 to 12 months."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "[see" not in normalized[0].content
    assert "(see Tables" not in normalized[0].content
    assert "(8.1)" not in normalized[0].content
    assert "2 to 3 mcg/kg/day" in normalized[0].content
    assert "6 to 12 months" in normalized[0].content


def test_normalize_pages_removes_known_academic_page_furniture() -> None:
    pages = build_pages(
        "Results\nCalcium absorption was measured.\nNutrients 2024, 16, 950. https://doi.org/10.3390/nu16070950",
        "Discussion\nThe clinical relevance remains uncertain.\nNutrients 2024, 16, x FOR PEER REVIEW 2 of 39",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert all("Nutrients 2024" not in page.content for page in normalized)
    assert "Calcium absorption" in normalized[0].content


def test_normalize_pages_removes_mdpi_footer_and_numeric_citations_only() -> None:
    pages = build_pages(
        "1. Introduction\n"
        "Drug-nutrient interactions are relevant [1-4] and clinically important [10, 22].\n"
        "The search used [micronutrient] as a placeholder.\n"
        "Nutrients 2024, 16, 950. https://doi.org/10.3390/nu16070950\n"
        "https://www.mdpi.com/journal/nutrients"
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == (
        "1. Introduction\n"
        "Drug-nutrient interactions are relevant and clinically important.\n"
        "The search used [micronutrient] as a placeholder."
    )


def test_normalize_pages_removes_figure_labels_but_preserves_claims_and_tables() -> None:
    pages = build_pages(
        "Results\n"
        "Figure 1. Proposed interaction mechanism.\n"
        "Calcium may affect iron absorption (Figure 1).\n"
        "The pathways are summarized in Figures 1 and 2.\n"
        "Table 1. Human interaction studies."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == (
        "Results\n"
        "Calcium may affect iron absorption.\n"
        "The pathways are summarized.\n"
        "Table 1. Human interaction studies."
    )


def test_normalize_pages_removes_figure_caption_without_punctuation() -> None:
    pages = build_pages(
        "Results\nSamples were collected from the supernatant after\nFigure 1 The flow chart of literature selection."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("Results\nSamples were collected from the supernatant after")


def test_normalize_pages_removes_figure_and_supplement_cross_reference() -> None:
    pages = build_research_pages(
        "Results\n"
        "The other studies met the exclusions (Figure 1 and Supplement 3).\n"
        "The clinical finding remains relevant."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == (
        "Results\nThe other studies met the exclusions.\nThe clinical finding remains relevant."
    )


def test_normalize_pages_removes_numeric_reference_column_from_table_content() -> None:
    page = build_pages("Nutriment=niacin | Result=INR increased | References=[271]")[0]
    page.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=100),
            content=("Nutriment=niacin | Result=INR increased | References=[271]"),
            headers=["Nutriment", "Result", "References"],
            rows=[KnowledgeTableRow(cells=["niacin", "INR increased", "[271]"])],
            column_count=3,
        )
    ]

    normalized = KnowledgeNormalizer().normalize_pages([page])

    assert normalized[0].blocks[0].content == ("Nutriment=niacin | Result=INR increased")
    assert normalized[0].blocks[0].rows[0].cells == [
        "niacin",
        "INR increased",
        "",
    ]


def test_normalize_pages_removes_attached_table_citations_but_keeps_counts_and_doses() -> None:
    page = build_research_pages(
        "Interfering Substances=Calcium carbonate; Calcium acetate; Calcium citrate "
        "| Class=Calcium supplement "
        "| Evidencesa=For interaction 1 randomized crossover study14 "
        "3 prospective studies15–17 4 retrospective studies3,18–20 "
        "| Recommendation=separate by 2–8h and use 1200 mg"
    )[0]
    page.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=100),
            content=page.content,
            headers=[
                "Interfering Substances",
                "Class",
                "Evidencesa",
                "Recommendation",
            ],
            rows=[
                KnowledgeTableRow(
                    cells=[
                        "Calcium carbonate; Calcium acetate; Calcium citrate",
                        "Calcium supplement",
                        (
                            "For interaction 1 randomized crossover study14 "
                            "3 prospective studies15–17 "
                            "4 retrospective studies3,18–20"
                        ),
                        "separate by 2–8h and use 1200 mg",
                    ]
                )
            ],
            column_count=4,
        )
    ]

    normalized = KnowledgeNormalizer().normalize_pages([page])
    table = normalized[0].blocks[0]

    assert table.headers[2] == "Evidences"
    assert table.rows[0].cells[2] == (
        "For interaction 1 randomized crossover study 3 prospective studies 4 retrospective studies"
    )
    assert table.rows[0].cells[3] == "separate by 2–8h and use 1200 mg"


def test_normalize_pages_promotes_repeated_table_header_and_drops_orphan_duplicate() -> None:
    page = build_research_pages(
        "열 1=Interfering Substances | 열 2=Class | 열 3=Evidencesa\n"
        "열 1=Sucralfate | 열 2=Gastric protectant | 열 3=1 randomized two-arm40 study\n"
        "열 1=Sucralfate"
    )[0]
    page.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=100),
            content=page.content,
            headers=["열 1", "열 2", "열 3"],
            rows=[
                KnowledgeTableRow(cells=["Interfering Substances", "Class", "Evidencesa"]),
                KnowledgeTableRow(
                    cells=[
                        "Sucralfate",
                        "Gastric protectant",
                        "1 randomized two-arm40 study",
                    ]
                ),
                KnowledgeTableRow(cells=["Sucralfate", "", ""]),
            ],
            column_count=3,
            validation_errors=["MULTI_ENTITY_ROW", "SOURCE_TOKEN_LOSS"],
        )
    ]
    page.extraction_warnings = [KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE]

    normalized = KnowledgeNormalizer().normalize_pages([page])
    table = normalized[0].blocks[0]

    assert table.headers == [
        "Interfering Substances",
        "Class",
        "Evidences",
    ]
    assert [row.cells for row in table.rows] == [["Sucralfate", "Gastric protectant", "1 randomized two-arm study"]]
    assert table.content == (
        "Interfering Substances=Sucralfate | Class=Gastric protectant | Evidences=1 randomized two-arm study"
    )
    assert table.validation_errors == []
    assert KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE not in normalized[0].extraction_warnings


def test_normalize_pages_moves_research_table_notes_out_of_body_text() -> None:
    page = build_research_pages(
        "Interfering Substances=Calcium carbonate | Class=Calcium supplement\n"
        "Notes: Some comparisons may show conflicting results."
    )[0]
    page.blocks = [
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TABLE,
            order=0,
            bbox=KnowledgeBoundingBox(x0=10, top=10, x1=500, bottom=100),
            content=("Interfering Substances=Calcium carbonate | Class=Calcium supplement"),
            headers=["Interfering Substances", "Class"],
            rows=[KnowledgeTableRow(cells=["Calcium carbonate", "Calcium supplement"])],
            column_count=2,
            table_title="Interaction summary",
        ),
        KnowledgePageBlock(
            kind=KnowledgeContentKind.TEXT,
            order=1,
            bbox=KnowledgeBoundingBox(x0=10, top=110, x1=500, bottom=140),
            content="Notes: Some comparisons may show conflicting results.",
        ),
    ]

    normalized = KnowledgeNormalizer().normalize_pages([page])

    assert [block.kind for block in normalized[0].blocks] == [KnowledgeContentKind.TABLE]
    assert normalized[0].blocks[0].table_super_headers == ["Notes: Some comparisons may show conflicting results."]


def test_normalize_pages_repairs_verified_word_across_page_boundary() -> None:
    pages = build_pages(
        "Other important nutrients include two macronu-",
        "trients, fatty acids and dietary amino acids.",
        "Macronutrients are described elsewhere in the document.",
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content.endswith("two macronutrients,")
    assert normalized[1].content.startswith("fatty acids")


def test_normalize_pages_removes_compact_academic_page_numbers() -> None:
    pages = build_pages(
        "Introduction\nDrug-nutrient interactions are clinically relevant.\n"
        "Nutrients2024,16,950.https://doi.org/10.3390/nu16070950\n"
        "2 of 39\n2of37"
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("Introduction\nDrug-nutrient interactions are clinically relevant.")


def test_normalize_pages_removes_inline_publisher_license_prefixes() -> None:
    pages = build_pages(
        "Copyright: © 2024 by the authors. Medication can affect nutrient uptake.\n"
        "Licensee MDPI, Basel, Switzerland. Transport pathways may be altered.\n"
        "Thisarticleisanopenaccessarticle Absorption was measured."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "Copyright" not in normalized[0].content
    assert "Licensee MDPI" not in normalized[0].content
    assert "openaccessarticle" not in normalized[0].content
    assert "Medication can affect nutrient uptake." in normalized[0].content
    assert "Transport pathways may be altered." in normalized[0].content
    assert "Absorption was measured." in normalized[0].content


def test_normalize_pages_removes_embedded_publisher_license_block() -> None:
    pages = build_pages(
        "The antiulcer agents were followed by\n"
        "© 2023 Liu et al. This work is published and licensed by Dove Medical Press Limited.\n"
        "The full terms of this license are available online.\n"
        "Received: 27 March 2023\nAccepted: 19 June 2023\nPublished: 23 June 2023\n"
        "iron and calcium supplements."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert "Dove Medical Press" not in normalized[0].content
    assert "Received:" not in normalized[0].content
    assert "iron and calcium supplements" in normalized[0].content


def test_normalize_pages_keeps_research_title_and_abstract_but_removes_authors() -> None:
    pages = build_research_pages(
        "Therapeutics and Clinical Risk Management\n"
        "open access to scientific and medical research\n"
        "Open Access Full Text Article\n"
        "R E V I E W\n"
        "Medications and Food Interfering with the\n"
        "Bioavailability of Levothyroxine: A Systematic Review\n"
        "Hanqing Liu, Man Lu, Jiawei Hu\n"
        "Department of Breast and Thyroid Surgery\n"
        "Correspondence: author@example.org\n"
        "Purpose: Levothyroxine bioavailability can be altered.\n"
        "Methods: Human studies were reviewed.\n"
        "Results: Calcium and iron interactions were reported.\n"
        "Conclusion: Clinicians should consider interactions.\n"
        "Keywords: L-T4, drug, interference\n"
        "Introduction\n"
        "Levothyroxine is widely prescribed.\n"
        "© 2023 Liu et al. This work is published and licensed by "
        "Dove Medical Pres Limited. License terms follow."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content.startswith(
        "Medications and Food Interfering with the Bioavailability "
        "of Levothyroxine: A Systematic Review\nAbstract\nPurpose:"
    )
    assert "Methods: Human studies were reviewed." in normalized[0].content
    assert "Keywords: L-T4, drug, interference" in normalized[0].content
    assert "Introduction\nLevothyroxine is widely prescribed." in normalized[0].content
    assert "Hanqing Liu" not in normalized[0].content
    assert "Department of" not in normalized[0].content
    assert "author@example.org" not in normalized[0].content
    assert "Dove Medical Pres" not in normalized[0].content


def test_normalize_pages_removes_research_running_headers_and_footers() -> None:
    pages = build_research_pages(
        "Liu et al\n"
        "hypoglycemics (17.4%), and iron supplements (16.1%).\n"
        "interactions with LT4.\n"
        "504 ht ps:/ doi.org/10.2147/TCRM.S414460\n"
        "Therapeutics andClinicalRiskManagement 2023:19\n"
        "Powerd byTCPDF (w .tcpdforg)"
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == ("hypoglycemics (17.4%), and iron supplements (16.1%).\ninteractions with LT4.")


def test_normalize_pages_removes_fragmented_vertical_research_footer() -> None:
    pages = build_research_pages(
        "The quality assessment was completed.\n"
        "Therapeutics\n"
        "andClinicalRiskManagement\n"
        "2023:19\n"
        "Liu\n"
        "et\n"
        "al\n"
        "htps:/doi.org/^10.^2147/TCRM.S414460\n"
        "Table 1 (Continued)."
    )

    normalized = KnowledgeNormalizer().normalize_pages(pages)

    assert normalized[0].content == "The quality assessment was completed."


def test_normalize_pages_applies_same_cleanup_to_structured_blocks() -> None:
    page = build_pages("Coadministration is described elsewhere.\nCo\u00adadministration affects absorption.")[0]
    page = page.model_copy(
        update={
            "blocks": [
                KnowledgePageBlock(
                    kind=KnowledgeContentKind.TEXT,
                    order=0,
                    bbox=KnowledgeBoundingBox(
                        x0=10,
                        top=10,
                        x1=500,
                        bottom=50,
                    ),
                    content=("Coadministration is described elsewhere.\nCo\u00adadministration affects absorption."),
                )
            ]
        }
    )

    normalized = KnowledgeNormalizer().normalize_pages([page])

    assert normalized[0].blocks[0].content == (
        "Coadministration is described elsewhere.\nCoadministration affects absorption."
    )
