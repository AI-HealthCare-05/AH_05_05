import json
from hashlib import sha256
from pathlib import Path

import pytest

from ai_worker.services.knowledge_recovery_manifest_service import (
    KnowledgeRecoveryManifestService,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _document_report(
    *,
    document_id: str,
    source_id: str,
    partial_release: bool,
    chunk_reviews: list[dict],
) -> dict:
    return {
        "document_id": document_id,
        "source_id": source_id,
        "partial_release": partial_release,
        "chunk_reviews": chunk_reviews,
    }


def _write_chunk(
    path: Path,
    *,
    document_id: str,
    chunk_id: str,
    content_hash: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "chunk_id": chunk_id,
                "content": "승인된 근거",
                "embedding_text": "승인된 근거",
                "token_count": 10,
                "metadata": {
                    "document_id": document_id,
                    "content_hash": content_hash,
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_builds_reproducible_partial_recovery_and_ocr_manifests(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    audit_path = tmp_path / "corpus-quality-audit.json"
    ocr_queue_path = tmp_path / "ocr-required.jsonl"
    release_chunks_dir = tmp_path / "release" / "chunks"
    release_chunks_dir.mkdir(parents=True)
    _write_jsonl(
        documents_path,
        [
            {
                "document_id": "partial-document",
                "source_id": "supplement-source",
                "repo_path": "raw/partial.pdf",
                "sha256": "a" * 64,
                "processing_status": "TEXT_EXTRACTABLE",
            },
            {
                "document_id": "ocr-document",
                "source_id": "ocr-source",
                "repo_path": "raw/ocr.pdf",
                "sha256": "b" * 64,
                "processing_status": "OCR_REQUIRED",
            },
        ],
    )
    audit_path.write_text(
        json.dumps(
            {
                "document_reports": [
                    _document_report(
                        document_id="partial-document",
                        source_id="supplement-source",
                        partial_release=True,
                        chunk_reviews=[
                            {
                                "chunk_id": "approved-chunk",
                                "page_start": 2,
                                "page_end": 2,
                                "status": "APPROVED",
                            },
                            {
                                "chunk_id": "pending-chunk",
                                "page_start": 3,
                                "page_end": 4,
                                "status": "PENDING",
                            },
                        ],
                    ),
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_chunk(
        release_chunks_dir / "partial-document.jsonl",
        document_id="partial-document",
        chunk_id="approved-chunk",
        content_hash="c" * 64,
    )
    _write_jsonl(
        ocr_queue_path,
        [
            {
                "document_id": "ocr-document",
                "source_id": "ocr-source",
                "repo_path": "raw/ocr.pdf",
                "sha256": "b" * 64,
                "ocr_reason": "CATALOG_OCR_REQUIRED",
            },
        ],
    )

    result = KnowledgeRecoveryManifestService().build(
        documents_path=documents_path,
        corpus_quality_audit_path=audit_path,
        release_chunks_dir=release_chunks_dir,
        ocr_queue_path=ocr_queue_path,
    )

    assert result.partial_document_count == 1
    assert result.pending_chunk_count == 1
    assert result.ocr_document_count == 1
    assert result.partial_entries[0].model_dump(mode="json") == {
        "document_id": "partial-document",
        "source_id": "supplement-source",
        "repo_path": "raw/partial.pdf",
        "source_sha256": "a" * 64,
        "approved_content_hashes": ["c" * 64],
        "pending_chunks": [
            {
                "chunk_id": "pending-chunk",
                "page_start": 3,
                "page_end": 4,
                "status": "PENDING",
            }
        ],
    }
    assert result.ocr_entries[0].model_dump(mode="json") == {
        "document_id": "ocr-document",
        "source_id": "ocr-source",
        "repo_path": "raw/ocr.pdf",
        "source_sha256": "b" * 64,
        "origin": "CATALOG",
        "access_scope": None,
    }


def test_rejects_ocr_manifest_when_source_hash_does_not_match_catalog(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    audit_path = tmp_path / "corpus-quality-audit.json"
    ocr_queue_path = tmp_path / "ocr-required.jsonl"
    _write_jsonl(
        documents_path,
        [
            {
                "document_id": "ocr-document",
                "source_id": "ocr-source",
                "repo_path": "raw/ocr.pdf",
                "sha256": "a" * 64,
                "processing_status": "OCR_REQUIRED",
            },
        ],
    )
    audit_path.write_text(json.dumps({"document_reports": []}), encoding="utf-8")
    _write_jsonl(
        ocr_queue_path,
        [
            {
                "document_id": "ocr-document",
                "source_id": "ocr-source",
                "repo_path": "raw/ocr.pdf",
                "sha256": "b" * 64,
                "ocr_reason": "CATALOG_OCR_REQUIRED",
            },
        ],
    )

    with pytest.raises(ValueError, match="SHA-256"):
        KnowledgeRecoveryManifestService().build(
            documents_path=documents_path,
            corpus_quality_audit_path=audit_path,
            release_chunks_dir=tmp_path / "release" / "chunks",
            ocr_queue_path=ocr_queue_path,
        )


def test_rejects_recovery_execution_when_raw_pdf_hash_changed(
    tmp_path: Path,
) -> None:
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    raw_path = raw_directory / "partial.pdf"
    raw_path.write_bytes(b"original PDF bytes")
    source_sha256 = sha256(raw_path.read_bytes()).hexdigest()
    documents_path = tmp_path / "documents.jsonl"
    audit_path = tmp_path / "corpus-quality-audit.json"
    ocr_queue_path = tmp_path / "ocr-required.jsonl"
    release_chunks_dir = tmp_path / "release" / "chunks"
    release_chunks_dir.mkdir(parents=True)
    _write_jsonl(
        documents_path,
        [
            {
                "document_id": "partial-document",
                "source_id": "supplement-source",
                "repo_path": "raw/partial.pdf",
                "sha256": source_sha256,
                "processing_status": "TEXT_EXTRACTABLE",
            }
        ],
    )
    audit_path.write_text(
        json.dumps(
            {
                "document_reports": [
                    _document_report(
                        document_id="partial-document",
                        source_id="supplement-source",
                        partial_release=True,
                        chunk_reviews=[
                            {
                                "chunk_id": "approved-chunk",
                                "page_start": 1,
                                "page_end": 1,
                                "status": "APPROVED",
                            },
                            {
                                "chunk_id": "pending-chunk",
                                "page_start": 2,
                                "page_end": 2,
                                "status": "PENDING",
                            },
                        ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_chunk(
        release_chunks_dir / "partial-document.jsonl",
        document_id="partial-document",
        chunk_id="approved-chunk",
        content_hash="c" * 64,
    )
    ocr_queue_path.write_text("", encoding="utf-8")
    service = KnowledgeRecoveryManifestService()
    result = service.build(
        documents_path=documents_path,
        corpus_quality_audit_path=audit_path,
        release_chunks_dir=release_chunks_dir,
        ocr_queue_path=ocr_queue_path,
    )
    raw_path.write_bytes(b"changed PDF bytes")

    with pytest.raises(ValueError, match="원본 SHA-256"):
        service.validate_source_files(result=result, repo_root=tmp_path)
