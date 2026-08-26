import json
from pathlib import Path

from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.schemas.knowledge_manifest import KnowledgeManualReviewStatus
from ai_worker.services.knowledge_corpus_preprocessing_service import (
    KnowledgeCorpusManifestBuilder,
    KnowledgeCorpusPreprocessingService,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def test_builder_selects_approved_qdrant_text_documents(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "public-code",
                "document_id": "magnesium-document",
                "repo_path": "raw/public/1-16 마그네슘.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "restricted-review",
                "document_id": "review-document",
                "repo_path": "raw/restricted/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
            },
            {
                "source_id": "public-code",
                "document_id": "ocr-document",
                "repo_path": "raw/public/ocr.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "c" * 64,
            },
            {
                "source_id": "disabled-source",
                "document_id": "disabled-document",
                "repo_path": "raw/disabled/source.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "d" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: public-code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/public
  - source_id: restricted-review
    provider: 약학정보원
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: PHARM_REVIEW
    raw_path: raw/restricted
  - source_id: disabled-source
    provider: 출처 확인 필요
    access_scope: DEMO_RESTRICTED
    target: QDRANT_DISABLED_UNTIL_VERIFIED
    document_type: RESEARCH_ARTICLE
    raw_path: raw/disabled
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 2,
                "chunk_count": 2,
                "ready_for_bulk_source_ids": [
                    "public-code",
                    "restricted-review",
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == [
        "magnesium-document",
        "review-document",
    ]
    assert all(entry.manual_review_status.value == "APPROVED" for entry in manifest.pilots)


def test_builder_deduplicates_identical_file_hashes(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "source",
                "document_id": "first-document",
                "repo_path": "raw/first.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "source",
                "document_id": "duplicate-document",
                "repo_path": "raw/second.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: source
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": ["source"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["first-document"]


def build_report(
    document_id: str,
    status: KnowledgeAutomaticQualityStatus,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id="source",
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        selection_reason="전체 전처리",
        automatic_status=status,
        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
        page_count=1,
        character_count=100,
        chunk_count=2 if status == KnowledgeAutomaticQualityStatus.PASS else 1,
        min_chunk_tokens=10,
        average_chunk_tokens=10,
        max_chunk_tokens=10,
        semantic_section_ratio=1,
        review_sample_path=Path(f"review/{document_id}.md"),
    )


def test_finalize_release_keeps_only_automatic_pass_documents(
    tmp_path: Path,
) -> None:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "pass-document.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (chunks_dir / "review-document.jsonl").write_text("{}\n", encoding="utf-8")
    result = KnowledgePilotPreprocessingResult(
        dataset_version="knowledge-full-v1",
        processed_document_count=2,
        chunk_count=3,
        document_reports=[
            build_report(
                "pass-document",
                KnowledgeAutomaticQualityStatus.PASS,
            ),
            build_report(
                "review-document",
                KnowledgeAutomaticQualityStatus.REVIEW,
            ),
        ],
    )

    release = KnowledgeCorpusPreprocessingService.finalize_release(
        result=result,
        output_root=tmp_path,
    )

    assert release.processed_document_count == 1
    assert release.chunk_count == 2
    assert release.ready_for_bulk_source_ids == ["source"]
    assert (chunks_dir / "pass-document.jsonl").is_file()
    assert not (chunks_dir / "review-document.jsonl").exists()
    assert (tmp_path / "reports" / "corpus-quality-audit.json").is_file()
