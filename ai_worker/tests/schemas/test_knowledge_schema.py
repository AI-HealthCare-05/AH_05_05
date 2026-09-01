import pytest
from pydantic import ValidationError

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgeSearchQuery,
    KnowledgeStudyPopulation,
)
from ai_worker.schemas.knowledge_manifest import (
    KnowledgePilotManifest,
    KnowledgeSourcesManifest,
)


def build_metadata() -> KnowledgeMetadata:
    return KnowledgeMetadata(
        source_id="mfds_supplement_code",
        document_id="vitamin-a",
        title="비타민 A",
        provider="식품의약품안전처",
        access_scope=KnowledgeAccessScope.PUBLIC,
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        dataset_version="pilot-v1",
        ingredient_names=["비타민 A"],
    )


def test_metadata_normalizes_duplicate_entity_names() -> None:
    metadata = build_metadata().model_copy(
        update={
            "ingredient_names": [
                " 비타민 A ",
                "비타민 A",
                "레티닐 팔미트산염",
            ]
        }
    )

    normalized = KnowledgeMetadata.model_validate(metadata.model_dump())

    assert normalized.ingredient_names == [
        "비타민 A",
        "레티닐 팔미트산염",
    ]


def test_metadata_defaults_to_unknown_evidence_contract() -> None:
    metadata = build_metadata()

    assert metadata.evidence_level == KnowledgeEvidenceLevel.UNKNOWN
    assert metadata.study_population == KnowledgeStudyPopulation.UNKNOWN


def test_page_requires_positive_page_number() -> None:
    with pytest.raises(ValidationError):
        KnowledgePage(
            content="기능성 내용",
            metadata=build_metadata(),
            page_number=0,
        )


def test_metadata_normalizes_interaction_pair_keys() -> None:
    metadata = build_metadata().model_copy(
        update={
            "interaction_pair_keys": [
                "a" * 64,
                "a" * 64,
                "b" * 64,
            ]
        }
    )

    normalized = KnowledgeMetadata.model_validate(metadata.model_dump())

    assert normalized.interaction_pair_keys == [
        "a" * 64,
        "b" * 64,
    ]


def test_search_query_rejects_invalid_interaction_pair_key() -> None:
    with pytest.raises(ValidationError, match="pair key"):
        KnowledgeSearchQuery(
            query="파록세틴과 셀레길린 상호작용",
            dataset_version="interaction-pilot-v1",
            interaction_pair_keys=["not-a-sha256"],
        )


def test_source_manifest_rejects_duplicate_source_ids() -> None:
    source = {
        "source_id": "duplicate_source",
        "provider": "식품의약품안전처",
        "access_scope": "PUBLIC",
        "target": "MYSQL",
        "raw_path": "raw/source",
    }

    with pytest.raises(ValidationError, match="source_id"):
        KnowledgeSourcesManifest.model_validate(
            {
                "schema_version": "knowledge-sources-v1",
                "sources": [source, source],
            }
        )


def test_pilot_manifest_rejects_duplicate_document_ids() -> None:
    pilot = {
        "source_id": "supplement_code",
        "document_id": "duplicate-document",
        "repo_path": "raw/document.pdf",
        "processing_status": "TEXT_EXTRACTABLE",
        "selection_reason": "test",
    }

    with pytest.raises(ValidationError, match="document_id"):
        KnowledgePilotManifest.model_validate(
            {
                "policy": "test",
                "pilots": [pilot, pilot],
            }
        )
