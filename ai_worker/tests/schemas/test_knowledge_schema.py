import pytest
from pydantic import ValidationError

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgePageBlock,
    KnowledgeSearchQuery,
    KnowledgeStudyPopulation,
    KnowledgeTableRow,
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


def test_page_accepts_ordered_text_and_table_blocks() -> None:
    page = KnowledgePage(
        content="제목\n\n성분=철분 | 결과=감소",
        metadata=build_metadata(),
        page_number=1,
        blocks=[
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TEXT,
                order=0,
                bbox=KnowledgeBoundingBox(
                    x0=0,
                    top=0,
                    x1=500,
                    bottom=40,
                ),
                content="제목",
            ),
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TABLE,
                order=1,
                bbox=KnowledgeBoundingBox(
                    x0=0,
                    top=50,
                    x1=500,
                    bottom=200,
                ),
                content="성분=철분 | 결과=감소",
                headers=["성분", "결과"],
                rows=[KnowledgeTableRow(cells=["철분", "감소"])],
                column_count=2,
                table_title="Table 1. Iron absorption",
                table_super_headers=["Human Studies"],
            ),
        ],
    )

    assert page.blocks[1].column_count == 2
    assert page.blocks[1].rows[0].cells == ["철분", "감소"]
    assert page.blocks[1].table_title == "Table 1. Iron absorption"
    assert page.blocks[1].table_super_headers == ["Human Studies"]


def test_legacy_page_without_blocks_remains_valid() -> None:
    page = KnowledgePage(
        content="기능성 내용",
        metadata=build_metadata(),
        page_number=1,
    )

    assert page.blocks == []


def test_bounding_box_rejects_reversed_coordinates() -> None:
    with pytest.raises(ValidationError, match="x1"):
        KnowledgeBoundingBox(
            x0=100,
            top=0,
            x1=10,
            bottom=20,
        )


def test_bounding_box_accepts_negative_pdf_crop_coordinates() -> None:
    bbox = KnowledgeBoundingBox(
        x0=-5,
        top=-30,
        x1=100,
        bottom=20,
    )

    assert bbox.top == -30


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


def test_pilot_manifest_rejects_blank_verified_text_replacement() -> None:
    with pytest.raises(ValidationError, match="텍스트 치환"):
        KnowledgePilotManifest.model_validate(
            {
                "policy": "test",
                "pilots": [
                    {
                        "source_id": "research_source",
                        "document_id": "research-document",
                        "repo_path": "raw/document.pdf",
                        "processing_status": "TEXT_EXTRACTABLE",
                        "selection_reason": "test",
                        "verified_text_replacements": {"mi-nor": ""},
                    }
                ],
            }
        )


def test_pilot_manifest_rejects_invalid_approved_chunk_content_hash() -> None:
    with pytest.raises(ValidationError, match="수동 승인 청크"):
        KnowledgePilotManifest.model_validate(
            {
                "policy": "test",
                "pilots": [
                    {
                        "source_id": "research_source",
                        "document_id": "research-document",
                        "repo_path": "raw/document.pdf",
                        "processing_status": "TEXT_EXTRACTABLE",
                        "selection_reason": "test",
                        "approved_chunk_content_hashes": ["chunk-7"],
                    }
                ],
            }
        )
