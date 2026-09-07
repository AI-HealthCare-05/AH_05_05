import json
from pathlib import Path

from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.schemas.knowledge_manifest import KnowledgeManualReviewStatus
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)
from ai_worker.services.knowledge_recovery_reporting_service import (
    KnowledgeRecoveryReportingService,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def _report(
    document_id: str,
    *,
    source_id: str,
    automatic_status: KnowledgeAutomaticQualityStatus,
    chunk_count: int,
    released_chunk_count: int,
    partial_release: bool,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id=source_id,
        source_document_path=Path(f"raw/{document_id}.pdf"),
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        selection_reason="전체 복원",
        automatic_status=automatic_status,
        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
        page_count=1,
        character_count=100,
        chunk_count=chunk_count,
        min_chunk_tokens=10,
        average_chunk_tokens=10,
        max_chunk_tokens=10,
        semantic_section_ratio=1,
        approved_chunk_count=released_chunk_count,
        released_chunk_count=released_chunk_count,
        partial_release=partial_release,
        release_ready=released_chunk_count > 0,
        review_sample_path=Path(f"review/{document_id}.md"),
    )


def test_write_creates_ocr_queue_and_recovery_summary(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    baseline_path = tmp_path / "baseline.json"
    output_root = tmp_path / "output"
    _write_jsonl(
        documents_path,
        [
            {
                "source_id": "adverse",
                "document_id": "ocr-document",
                "repo_path": "raw/ocr.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            },
            {
                "source_id": "research",
                "document_id": "partial-document",
                "repo_path": "raw/partial.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
            },
        ],
    )
    baseline_path.write_text(
        json.dumps(
            {
                "dataset_version": "baseline",
                "processed_document_count": 0,
                "chunk_count": 0,
                "skipped_documents": [
                    {
                        "document_id": "partial-document",
                        "reason": "AUTOMATIC_QUALITY_BLOCKED",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = KnowledgePilotPreprocessingResult(
        dataset_version="partial-dry-run",
        processed_document_count=1,
        chunk_count=2,
        skipped_documents=[
            {
                "document_id": "partial-document",
                "reason": "TEXT_QUALITY_OCR_REQUIRED",
            }
        ],
        document_reports=[
            _report(
                "partial-document",
                source_id="research",
                automatic_status=KnowledgeAutomaticQualityStatus.BLOCKED,
                chunk_count=2,
                released_chunk_count=2,
                partial_release=True,
            )
        ],
    )

    KnowledgeRecoveryReportingService().write(
        documents_path=documents_path,
        baseline_quality_report_path=baseline_path,
        result=result,
        output_root=output_root,
    )

    ocr_rows = [json.loads(line) for line in (output_root / "reports" / "ocr-required.jsonl").read_text().splitlines()]
    summary = json.loads(
        (output_root / "reports" / "recovery-summary.json").read_text(),
    )
    assert ocr_rows == [
        {
            "document_id": "ocr-document",
            "repo_path": "raw/ocr.pdf",
            "sha256": "a" * 64,
            "source_id": "adverse",
            "ocr_reason": "CATALOG_OCR_REQUIRED",
        },
        {
            "document_id": "partial-document",
            "repo_path": "raw/partial.pdf",
            "sha256": "b" * 64,
            "source_id": "research",
            "ocr_reason": "TEXT_QUALITY_OCR_REQUIRED",
        },
    ]
    assert summary["ocr_required_document_count"] == 2
    assert summary["catalog_ocr_required_document_count"] == 1
    assert summary["dynamic_ocr_required_document_count"] == 1
    assert summary["ocr_queue_document_count"] == 2
    assert summary["recovered_document_count"] == 1
    assert summary["partial_release_document_count"] == 1
    assert summary["released_chunk_count"] == 2
