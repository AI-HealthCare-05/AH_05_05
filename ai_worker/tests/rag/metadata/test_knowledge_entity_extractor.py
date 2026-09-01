from ai_worker.rag.metadata.knowledge_entity_extractor import (
    KnowledgeEntityExtractor,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)


def test_extracts_normalized_supplement_name_from_code_title() -> None:
    entities = KnowledgeEntityExtractor().extract_from_title(
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        title="1-16 마그네슘 _20260616 (2페이지)",
    )

    assert entities.ingredient_names == ["마그네슘"]
    assert entities.drug_names == []


def test_extracts_drug_name_from_adverse_case_title() -> None:
    entities = KnowledgeEntityExtractor().extract_from_title(
        document_type=KnowledgeDocumentType.ADVERSE_CASE_REPORT,
        title="01 독사조신 심한어지러움",
    )

    assert entities.drug_names == ["독사조신"]


def test_extracts_verified_bilingual_drug_name_aliases() -> None:
    entities = KnowledgeEntityExtractor().extract_from_title(
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="로사르탄(losartan)",
    )

    assert entities.drug_names == [
        "로사르탄(losartan)",
        "로사르탄",
        "losartan",
    ]


def test_does_not_assign_all_document_words_as_supplement_names() -> None:
    entities = KnowledgeEntityExtractor().extract_from_title(
        document_type=KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
        title="건강기능식품 기능별 정보집",
    )

    assert entities.ingredient_names == []


def test_extracts_supplement_interaction_pair_from_research_title() -> None:
    entities = KnowledgeEntityExtractor().extract_from_title(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title=("Supplemental Zinc Lowers Measures of Iron Status in Young Women with Low Iron Reserves"),
    )

    assert entities.ingredient_names == ["아연", "철분"]
    assert entities.interaction_type == "SUPPLEMENT_SUPPLEMENT"
    assert len(entities.interaction_pair_keys) == 1


def test_enriches_research_chunk_with_pair_and_human_clinical_evidence() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Calcium and iron absorption--mechanisms and public health relevance",
        content=("A crossover single-meal study measured calcium and iron absorption in postmenopausal women."),
    )

    assert entities.ingredient_names == ["칼슘", "철분"]
    assert entities.interaction_type == "SUPPLEMENT_SUPPLEMENT"
    assert len(entities.interaction_pair_keys) == 1
    assert entities.evidence_level == KnowledgeEvidenceLevel.CLINICAL_STUDY
    assert entities.study_population == KnowledgeStudyPopulation.HUMAN


def test_enriches_animal_research_without_claiming_human_evidence() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Magnesium and zinc interaction",
        content="The intervention was evaluated in rats and mice.",
    )

    assert entities.evidence_level == KnowledgeEvidenceLevel.PRECLINICAL
    assert entities.study_population == KnowledgeStudyPopulation.ANIMAL


def test_does_not_infer_review_level_from_abstract_content() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Calcium and iron absorption",
        content=("Studies on human subjects and Caco-2 cells reported mixed findings without naming a study design."),
    )

    assert entities.evidence_level == KnowledgeEvidenceLevel.UNKNOWN
    assert entities.study_population == KnowledgeStudyPopulation.MIXED


def test_does_not_infer_supplement_interaction_from_drug_encyclopedia_mentions() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.DRUG_ENCYCLOPEDIA,
        title="테트라사이클린",
        content="칼슘, 마그네슘, 철분 또는 아연과 함께 복용하면 흡수가 달라질 수 있습니다.",
        section_type=KnowledgeSectionType.INTERACTION,
    )

    assert entities.interaction_type is None
    assert entities.interaction_pair_keys == []


def test_classifies_randomized_animal_study_as_preclinical() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Randomized calcium and iron absorption experiment",
        content="A randomized crossover experiment was performed in rats.",
        section_type=KnowledgeSectionType.METHODS,
    )

    assert entities.evidence_level == KnowledgeEvidenceLevel.PRECLINICAL
    assert entities.study_population == KnowledgeStudyPopulation.ANIMAL


def test_does_not_treat_human_red_blood_cells_as_cell_study() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Iron status in women",
        content="Red blood cells were measured in postmenopausal women.",
        section_type=KnowledgeSectionType.RESULTS,
    )

    assert entities.study_population == KnowledgeStudyPopulation.HUMAN


def test_does_not_classify_reference_section_as_evidence() -> None:
    entities = KnowledgeEntityExtractor().extract_from_chunk(
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        title="Calcium and iron absorption",
        content="Randomized clinical trial in women, Journal of Nutrition.",
        section_type=KnowledgeSectionType.REFERENCES,
    )

    assert entities.evidence_level == KnowledgeEvidenceLevel.UNKNOWN
    assert entities.study_population == KnowledgeStudyPopulation.UNKNOWN
