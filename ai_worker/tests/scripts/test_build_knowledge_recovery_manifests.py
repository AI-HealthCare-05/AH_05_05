import json
import sys
from pathlib import Path

from scripts import build_knowledge_recovery_manifests


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_main_writes_partial_and_ocr_manifest_files(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    audit_path = tmp_path / "audit.json"
    ocr_queue_path = tmp_path / "ocr.jsonl"
    release_chunks_dir = tmp_path / "release" / "chunks"
    partial_output_path = tmp_path / "partial.jsonl"
    ocr_output_path = tmp_path / "ocr-output.jsonl"
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
                    {
                        "document_id": "partial-document",
                        "source_id": "supplement-source",
                        "partial_release": True,
                        "pending_chunk_count": 1,
                        "chunk_reviews": [
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
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (release_chunks_dir / "partial-document.jsonl").write_text(
        json.dumps(
            {
                "chunk_id": "approved-chunk",
                "metadata": {"content_hash": "c" * 64},
            }
        )
        + "\n",
        encoding="utf-8",
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
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_knowledge_recovery_manifests.py",
            "--documents",
            str(documents_path),
            "--corpus-quality-audit",
            str(audit_path),
            "--release-chunks-dir",
            str(release_chunks_dir),
            "--ocr-queue",
            str(ocr_queue_path),
            "--partial-output",
            str(partial_output_path),
            "--ocr-output",
            str(ocr_output_path),
            "--skip-source-hash-validation",
        ],
    )

    build_knowledge_recovery_manifests.main()

    assert json.loads(partial_output_path.read_text().strip())["document_id"] == "partial-document"
    assert json.loads(ocr_output_path.read_text().strip())["origin"] == "CATALOG"
    assert json.loads(capsys.readouterr().out) == {
        "partial_document_count": 1,
        "pending_chunk_count": 1,
        "ocr_document_count": 1,
    }
