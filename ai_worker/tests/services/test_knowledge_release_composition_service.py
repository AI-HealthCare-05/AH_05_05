import json
from pathlib import Path

import pytest

from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
)
from ai_worker.schemas.knowledge_manifest import KnowledgeManualReviewStatus
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)
from ai_worker.services.knowledge_release_composition_service import (
    KnowledgeReleaseCompositionInput,
    KnowledgeReleaseCompositionService,
)


def build_chunk(
    marker: str,
    *,
    document_id: str,
    dataset_version: str,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=marker * 64,
        content=f"{marker} 근거",
        embedding_text=f"[문서] {document_id}\n[원문]\n{marker} 근거",
        token_count=10,
        metadata=KnowledgeChunkMetadata(
            source_id=f"source-{marker}",
            document_id=document_id,
            title=f"{document_id} 제목",
            provider="시험 제공자",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            dataset_version=dataset_version,
            ingredient_names=["시험 성분"],
            section_type=KnowledgeSectionType.INTERACTION,
            section_title="상호작용",
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash=marker * 64,
        ),
    )


def build_report(
    *,
    document_id: str,
    source_id: str,
    chunk_id: str,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id=source_id,
        source_document_path=Path(f"raw/{document_id}.pdf"),
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        selection_reason="시험",
        automatic_status=KnowledgeAutomaticQualityStatus.PASS,
        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
        page_count=1,
        character_count=10,
        chunk_count=1,
        min_chunk_tokens=10,
        average_chunk_tokens=10,
        max_chunk_tokens=10,
        semantic_section_ratio=1,
        search_entity_coverage=1,
        known_evidence_ratio=1,
        source_metadata_complete=True,
        approved_chunk_count=1,
        release_ready=True,
        review_sample_path=Path(f"review/{document_id}.md"),
        chunk_reviews=[
            {
                "chunk_index": 0,
                "page_start": 1,
                "page_end": 1,
                "chunk_id": chunk_id,
                "status": "APPROVED",
                "reason_codes": [],
            }
        ],
    )


def write_release(
    root: Path,
    *,
    marker: str,
    document_id: str,
    dataset_version: str,
) -> KnowledgeReleaseCompositionInput:
    chunks_dir = root / "chunks"
    reports_dir = root / "reports"
    chunks_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    chunk = build_chunk(
        marker,
        document_id=document_id,
        dataset_version=dataset_version,
    )
    (chunks_dir / f"{document_id}.jsonl").write_text(
        chunk.model_dump_json() + "\n",
        encoding="utf-8",
    )
    report = KnowledgePilotPreprocessingResult(
        dataset_version=dataset_version,
        processed_document_count=1,
        chunk_count=1,
        document_reports=[
            build_report(
                document_id=document_id,
                source_id=chunk.metadata.source_id,
                chunk_id=chunk.chunk_id,
            )
        ],
        ready_for_bulk_source_ids=[chunk.metadata.source_id],
    )
    quality_report_path = reports_dir / "preprocessing-quality.json"
    quality_report_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return KnowledgeReleaseCompositionInput(
        chunks_dir=chunks_dir,
        quality_report_path=quality_report_path,
    )


def test_compose_rewrites_dataset_version_and_merges_quality_contract(
    tmp_path: Path,
) -> None:
    first = write_release(
        tmp_path / "first",
        marker="a",
        document_id="document-a",
        dataset_version="release-a",
    )
    second = write_release(
        tmp_path / "second",
        marker="b",
        document_id="document-b",
        dataset_version="release-b",
    )
    output_root = tmp_path / "combined"

    result = KnowledgeReleaseCompositionService().compose(
        inputs=[first, second],
        output_root=output_root,
        dataset_version="release-combined",
    )

    assert result.processed_document_count == 2
    assert result.chunk_count == 2
    assert result.ready_for_bulk_source_ids == ["source-a", "source-b"]
    output_chunks = [
        json.loads(line)
        for path in sorted((output_root / "chunks").glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert {row["metadata"]["dataset_version"] for row in output_chunks} == {"release-combined"}
    persisted = KnowledgePilotPreprocessingResult.model_validate_json(
        (output_root / "reports" / "preprocessing-quality.json").read_text(
            encoding="utf-8",
        )
    )
    assert persisted == result


def test_compose_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    first = write_release(
        tmp_path / "first",
        marker="a",
        document_id="same-document",
        dataset_version="release-a",
    )
    second = write_release(
        tmp_path / "second",
        marker="b",
        document_id="same-document",
        dataset_version="release-b",
    )

    with pytest.raises(ValueError, match="중복 document_id"):
        KnowledgeReleaseCompositionService().compose(
            inputs=[first, second],
            output_root=tmp_path / "combined",
            dataset_version="release-combined",
        )


def test_compose_accepts_partial_release_with_only_approved_chunks(
    tmp_path: Path,
) -> None:
    release = write_release(
        tmp_path / "partial",
        marker="p",
        document_id="partial-document",
        dataset_version="release-partial",
    )
    raw_report = json.loads(release.quality_report_path.read_text(encoding="utf-8"))
    document_report = raw_report["document_reports"][0]
    document_report["automatic_status"] = "BLOCKED"
    document_report["partial_release"] = True
    document_report["released_chunk_count"] = 1
    document_report["release_ready"] = True
    release.quality_report_path.write_text(
        json.dumps(raw_report, ensure_ascii=False),
        encoding="utf-8",
    )

    result = KnowledgeReleaseCompositionService().compose(
        inputs=[release],
        output_root=tmp_path / "combined",
        dataset_version="release-combined",
    )

    assert result.processed_document_count == 1
    assert result.document_reports[0].partial_release is True


def test_compose_accepts_manually_approved_blocked_document_when_all_released_chunks_are_approved(
    tmp_path: Path,
) -> None:
    release = write_release(
        tmp_path / "manual-override",
        marker="m",
        document_id="manually-approved-document",
        dataset_version="release-manual-override",
    )
    raw_report = json.loads(release.quality_report_path.read_text(encoding="utf-8"))
    document_report = raw_report["document_reports"][0]
    document_report["automatic_status"] = "BLOCKED"
    document_report["partial_release"] = False
    document_report["released_chunk_count"] = 1
    document_report["release_ready"] = True
    release.quality_report_path.write_text(
        json.dumps(raw_report, ensure_ascii=False),
        encoding="utf-8",
    )

    result = KnowledgeReleaseCompositionService().compose(
        inputs=[release],
        output_root=tmp_path / "combined",
        dataset_version="release-combined",
    )

    assert result.processed_document_count == 1
    assert result.document_reports[0].release_ready is True


def test_compose_rejects_existing_output_directory(tmp_path: Path) -> None:
    release = write_release(
        tmp_path / "first",
        marker="a",
        document_id="document-a",
        dataset_version="release-a",
    )
    output_root = tmp_path / "combined"
    output_root.mkdir()

    with pytest.raises(ValueError, match="이미 존재"):
        KnowledgeReleaseCompositionService().compose(
            inputs=[release],
            output_root=output_root,
            dataset_version="release-combined",
        )


def test_compose_migrates_legacy_report_without_source_document_path(
    tmp_path: Path,
) -> None:
    release = write_release(
        tmp_path / "legacy",
        marker="a",
        document_id="legacy-document",
        dataset_version="legacy-release",
    )
    raw_report = json.loads(release.quality_report_path.read_text(encoding="utf-8"))
    del raw_report["document_reports"][0]["source_document_path"]
    del raw_report["document_reports"][0]["release_ready"]
    release.quality_report_path.write_text(
        json.dumps(raw_report, ensure_ascii=False),
        encoding="utf-8",
    )

    result = KnowledgeReleaseCompositionService().compose(
        inputs=[release],
        output_root=tmp_path / "combined",
        dataset_version="release-combined",
    )

    assert result.document_reports[0].source_document_path == Path("legacy-document.pdf")
    assert result.document_reports[0].release_ready is True
