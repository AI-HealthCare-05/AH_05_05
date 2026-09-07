import json
from pathlib import Path

from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.schemas.knowledge_manifest import KnowledgeManualReviewStatus
from ai_worker.services.knowledge_blocked_document_recovery_service import (
    KnowledgeBlockedDocumentRecoveryService,
    KnowledgeBlockedDocumentRecoveryStatus,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityReasonCode,
    KnowledgeAutomaticQualityStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)


def build_blocked_report(
    *,
    document_id: str,
    source_id: str,
    source_document_path: str,
    document_type: KnowledgeDocumentType,
    reason_codes: list[KnowledgeAutomaticQualityReasonCode],
    layout_warning_pages: list[int] | None = None,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id=source_id,
        source_document_path=Path(source_document_path),
        document_type=document_type,
        selection_reason="전체 코퍼스 전처리",
        automatic_status=KnowledgeAutomaticQualityStatus.BLOCKED,
        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
        reason_codes=reason_codes,
        page_count=2,
        character_count=200,
        chunk_count=2,
        min_chunk_tokens=10,
        average_chunk_tokens=20,
        max_chunk_tokens=30,
        semantic_section_ratio=0,
        layout_warning_count=len(layout_warning_pages or []),
        layout_warning_pages=layout_warning_pages or [],
        review_sample_path=Path(f"review/{document_id}.md"),
    )


def test_recovery_service_automatically_excludes_garbled_supplement_source_text(
    tmp_path: Path,
) -> None:
    """Broken legacy supplement text must not become a human review task or Qdrant candidate."""
    document_id = "food-safety-p1"
    quarantine_text = tmp_path / "quarantine" / "text"
    quarantine_text.mkdir(parents=True)
    (quarantine_text / f"{document_id}.jsonl").write_text(
        json.dumps({"content": "ܐ FMTFNJOF ੿੄ ޛ ࠁ࠙ࢿ"}, ensure_ascii=False),
        encoding="utf-8",
    )
    review_sample = tmp_path / "review" / f"{document_id}.md"
    review_sample.parent.mkdir()
    review_sample.write_text("자동 제외 전 생성된 검수 파일", encoding="utf-8")
    result = KnowledgePilotPreprocessingResult(
        dataset_version="test-v1",
        processed_document_count=0,
        chunk_count=0,
        document_reports=[
            build_blocked_report(
                document_id=document_id,
                source_id="food_safety_korea_supplement_ingredients",
                source_document_path="data/knowledge/raw/public/p1-1.pdf",
                document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
                reason_codes=[
                    KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS,
                    KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
                ],
            )
        ],
    )

    recovery = KnowledgeBlockedDocumentRecoveryService().write(
        result=result,
        output_root=tmp_path,
    )

    assert recovery.automatically_excluded_count == 1
    assert recovery.manual_review_required_count == 0
    assert recovery.records[0].status == KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT
    assert not review_sample.exists()
    assert not (tmp_path / "review" / "REQUIRES_MANUAL_REVIEW.md").exists()


def test_recovery_service_writes_only_reading_order_unsafe_document_to_manual_review(
    tmp_path: Path,
) -> None:
    """A multi-column research article remains visible for human verification with its source pages."""
    report = build_blocked_report(
        document_id="research-calcium-iron",
        source_id="research_supplement_interactions",
        source_document_path="data/knowledge/raw/research/calcium-iron.pdf",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        reason_codes=[KnowledgeAutomaticQualityReasonCode.READING_ORDER_UNSAFE],
        layout_warning_pages=[2, 3],
    )
    result = KnowledgePilotPreprocessingResult(
        dataset_version="test-v1",
        processed_document_count=0,
        chunk_count=0,
        document_reports=[report],
    )

    recovery = KnowledgeBlockedDocumentRecoveryService().write(
        result=result,
        output_root=tmp_path,
    )

    manual_review = tmp_path / "review" / "REQUIRES_MANUAL_REVIEW.md"
    assert recovery.automatically_excluded_count == 0
    assert recovery.manual_review_required_count == 1
    assert recovery.records[0].status == KnowledgeBlockedDocumentRecoveryStatus.MANUAL_REVIEW_REQUIRED
    assert manual_review.is_file()
    content = manual_review.read_text(encoding="utf-8")
    assert "research-calcium-iron" in content
    assert "data/knowledge/raw/research/calcium-iron.pdf" in content
    assert "원본 p.2, p.3" in content


def test_recovery_service_excludes_latin_shifted_supplement_text_without_summary_fields(
    tmp_path: Path,
) -> None:
    """Encoding-shifted Latin fragments are not a recoverable consumer summary."""
    document_id = "food-safety-p1-latin-shift"
    quarantine_text = tmp_path / "quarantine" / "text"
    quarantine_text.mkdir(parents=True)
    (quarantine_text / f"{document_id}.jsonl").write_text(
        json.dumps({"content": "FMTFNJOF BMTBNJOF JHOPOJBTFNQFSWJSFOT"}),
        encoding="utf-8",
    )
    result = KnowledgePilotPreprocessingResult(
        dataset_version="test-v1",
        processed_document_count=0,
        chunk_count=0,
        document_reports=[
            build_blocked_report(
                document_id=document_id,
                source_id="food_safety_korea_supplement_ingredients",
                source_document_path="data/knowledge/raw/public/p1-1.pdf",
                document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
                reason_codes=[
                    KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS,
                    KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
                ],
            )
        ],
    )

    recovery = KnowledgeBlockedDocumentRecoveryService().write(
        result=result,
        output_root=tmp_path,
    )

    assert recovery.automatically_excluded_count == 1
    assert recovery.records[0].status == KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT


def test_recovery_service_includes_unreleased_quality_review_in_manual_queue(
    tmp_path: Path,
) -> None:
    """A non-blocked document with no approved chunks still needs a visible human decision."""
    report = build_blocked_report(
        document_id="vitamin-b12-review",
        source_id="research_supplement_interactions",
        source_document_path="data/knowledge/raw/research/vitamin-b12.pdf",
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        reason_codes=[KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS],
    ).model_copy(
        update={"automatic_status": KnowledgeAutomaticQualityStatus.REVIEW},
    )

    recovery = KnowledgeBlockedDocumentRecoveryService().write(
        result=KnowledgePilotPreprocessingResult(
            dataset_version="test-v1",
            processed_document_count=0,
            chunk_count=0,
            document_reports=[report],
        ),
        output_root=tmp_path,
    )

    assert recovery.manual_review_required_count == 1
    assert recovery.records[0].document_id == "vitamin-b12-review"
    assert recovery.records[0].status == KnowledgeBlockedDocumentRecoveryStatus.MANUAL_REVIEW_REQUIRED
