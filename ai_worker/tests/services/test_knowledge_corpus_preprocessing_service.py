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
    KnowledgeChunkReviewRecord,
    KnowledgeChunkReviewStatus,
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


def test_builder_includes_ocr_document_only_when_artifact_is_available(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    quality_path = tmp_path / "quality.json"
    artifact_root = tmp_path / "artifacts"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "ocr-source",
                "document_id": "ocr-document",
                "repo_path": "raw/ocr/document.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: ocr-source
    provider: OCR 출처
    access_scope: PUBLIC
    target: QDRANT
    document_type: ADVERSE_CASE_REPORT
    raw_path: raw/ocr
""".strip(),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps({"ready_for_bulk_source_ids": ["ocr-source"]}),
        encoding="utf-8",
    )
    artifact_root.mkdir()
    (artifact_root / "ocr-document.json").write_text("{}", encoding="utf-8")

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=quality_path,
        ocr_artifact_root=artifact_root,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["ocr-document"]
    assert manifest.pilots[0].processing_status.value == "TEXT_EXTRACTABLE"


def test_builder_unions_approved_sources_from_multiple_quality_reports(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    first_report_path = tmp_path / "first-quality.json"
    second_report_path = tmp_path / "second-quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "first-source",
                "document_id": "first-document",
                "repo_path": "raw/first/first.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "second-source",
                "document_id": "second-document",
                "repo_path": "raw/second/second.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: first-source
    provider: First
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/first
  - source_id: second-source
    provider: Second
    access_scope: PUBLIC
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw/second
""".strip(),
        encoding="utf-8",
    )
    first_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "first",
                "processed_document_count": 0,
                "chunk_count": 0,
                "ready_for_bulk_source_ids": ["first-source"],
            }
        ),
        encoding="utf-8",
    )
    second_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "second",
                "processed_document_count": 0,
                "chunk_count": 0,
                "ready_for_bulk_source_ids": ["second-source"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_paths=[first_report_path, second_report_path],
    )

    assert [entry.document_id for entry in manifest.pilots] == [
        "first-document",
        "second-document",
    ]


def test_builder_accepts_legacy_quality_report_without_new_document_fields(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "legacy-quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "legacy-source",
                "document_id": "legacy-document",
                "repo_path": "raw/legacy/legacy.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: legacy-source
    provider: Legacy
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/legacy
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "legacy-v2",
                "processed_document_count": 1,
                "chunk_count": 1,
                "document_reports": [
                    {
                        "document_id": "legacy-document",
                        "source_id": "legacy-source",
                    }
                ],
                "ready_for_bulk_source_ids": ["legacy-source"],
            },
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["legacy-document"]


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


def test_builder_preserves_reviewed_document_metadata(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "research",
                "document_id": "review-document",
                "repo_path": "raw/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
                "title": "Reviewed interaction article",
                "source_url": "https://doi.org/10.1234/review",
                "doi": "10.1234/review",
                "authors": ["Example Author"],
                "publication_year": 2024,
                "drug_names": ["warfarin"],
                "ingredient_names": ["vitamin K"],
                "evidence_level": "SYSTEMATIC_REVIEW",
                "study_population": "HUMAN",
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
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
                "ready_for_bulk_source_ids": ["research"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    entry = manifest.pilots[0]
    assert entry.title == "Reviewed interaction article"
    assert entry.source_url == "https://doi.org/10.1234/review"
    assert entry.doi == "10.1234/review"
    assert entry.authors == ["Example Author"]
    assert entry.publication_year == 2024
    assert entry.drug_names == ["warfarin"]
    assert entry.ingredient_names == ["vitamin K"]
    assert entry.evidence_level.value == "SYSTEMATIC_REVIEW"
    assert entry.study_population.value == "HUMAN"


def test_builder_inherits_verified_repairs_from_pilot_manifest(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    pilot_manifest_path = tmp_path / "pilot-manifest.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "research",
                "document_id": "review-document",
                "repo_path": "raw/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
                "title": "Reviewed interaction article",
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
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
                "ready_for_bulk_source_ids": ["research"],
            }
        ),
        encoding="utf-8",
    )
    pilot_manifest_path.write_text(
        json.dumps(
            {
                "policy": "대표 문서 검수",
                "pilots": [
                    {
                        "source_id": "research",
                        "document_id": "review-document",
                        "repo_path": "raw/review.pdf",
                        "processing_status": "TEXT_EXTRACTABLE",
                        "selection_reason": "대표 문서",
                        "manual_review_status": "APPROVED",
                        "verified_text_replacements": {
                            "intestinal wal": "intestinal wall",
                        },
                        "verified_section_headings": [
                            "Drug Interactions",
                        ],
                        "approved_review_reason_codes": [
                            "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW",
                        ],
                        "approved_chunk_content_hashes": ["b" * 64],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
        pilot_manifest_path=pilot_manifest_path,
    )

    entry = manifest.pilots[0]
    assert entry.selection_reason == "대표 문서"
    assert entry.verified_text_replacements == {
        "intestinal wal": "intestinal wall",
    }
    assert entry.verified_section_headings == ["Drug Interactions"]
    assert [code.value for code in entry.approved_review_reason_codes] == [
        "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW",
    ]
    assert entry.approved_chunk_content_hashes == ["b" * 64]


def build_report(
    document_id: str,
    status: KnowledgeAutomaticQualityStatus,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id="source",
        source_document_path=Path(f"raw/{document_id}.pdf"),
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


def test_finalize_release_keeps_approved_chunks_from_blocked_document(
    tmp_path: Path,
) -> None:
    chunks_dir = tmp_path / "chunks"
    release_chunks_dir = tmp_path / "release" / "chunks"
    chunks_dir.mkdir()
    release_chunks_dir.mkdir(parents=True)
    (chunks_dir / "partial-document.jsonl").write_text(
        "{}\n{}\n",
        encoding="utf-8",
    )
    (release_chunks_dir / "partial-document.jsonl").write_text(
        '{"chunk_id":"approved"}\n',
        encoding="utf-8",
    )
    report = build_report(
        "partial-document",
        KnowledgeAutomaticQualityStatus.BLOCKED,
    ).model_copy(
        update={
            "chunk_count": 2,
            "approved_chunk_count": 1,
            "repair_required_chunk_count": 1,
            "released_chunk_count": 1,
            "partial_release": True,
            "chunk_reviews": [
                KnowledgeChunkReviewRecord(
                    chunk_id="a" * 64,
                    chunk_index=0,
                    page_start=1,
                    page_end=1,
                    status=KnowledgeChunkReviewStatus.APPROVED,
                ),
                KnowledgeChunkReviewRecord(
                    chunk_id="b" * 64,
                    chunk_index=1,
                    page_start=1,
                    page_end=1,
                    status=KnowledgeChunkReviewStatus.REPAIR_REQUIRED,
                ),
            ],
        }
    )
    result = KnowledgePilotPreprocessingResult(
        dataset_version="knowledge-full-v1",
        processed_document_count=0,
        chunk_count=0,
        document_reports=[report],
        skipped_documents=[
            {
                "document_id": "partial-document",
                "reason": "AUTOMATIC_QUALITY_BLOCKED",
            }
        ],
    )

    release = KnowledgeCorpusPreprocessingService.finalize_release(
        result=result,
        output_root=tmp_path,
    )

    assert release.processed_document_count == 1
    assert release.chunk_count == 1
    assert release.skipped_documents == []
    released_report = release.document_reports[0]
    assert released_report.chunk_count == 1
    assert released_report.released_chunk_count == 1
    assert released_report.partial_release is True
    assert released_report.release_ready is True
    assert [review.status for review in released_report.chunk_reviews] == [KnowledgeChunkReviewStatus.APPROVED]
    assert (chunks_dir / "partial-document.jsonl").read_text() == ('{"chunk_id":"approved"}\n')
