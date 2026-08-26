from ai_worker.rag.metadata.knowledge_entity_extractor import (
    KnowledgeEntityExtractor,
)
from ai_worker.schemas.knowledge import KnowledgeDocumentType


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
