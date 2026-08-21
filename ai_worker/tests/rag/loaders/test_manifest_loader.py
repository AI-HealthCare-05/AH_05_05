import json
from pathlib import Path

import pytest

from ai_worker.rag.loaders.manifest_loader import (
    GuidelineManifestLoader,
)


def write_manifest(
    manifest_path: Path,
    documents: list[dict[str, object]],
) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "documents": documents,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_load_reads_single_document_and_resolves_relative_pdf_path(
    tmp_path: Path,
) -> None:
    pdf_directory = tmp_path / "pdfs"
    pdf_directory.mkdir()

    pdf_path = pdf_directory / "stroke-guideline.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path=manifest_path,
        documents=[
            {
                "file_path": ("pdfs/stroke-guideline.pdf"),
                "document_id": "stroke-2020",
                "title": "Stroke Guideline",
                "organization": "Test Organization",
                "dataset_version": "2020",
                "publication_year": 2020,
                "language": "en",
                "condition": "STROKE",
                "care_phase": "POST_DISCHARGE",
                "topic": "LIFESTYLE",
                "source_url": ("https://example.org/stroke-guideline"),
                "license": "TEST_LICENSE",
            }
        ],
    )

    loader = GuidelineManifestLoader()

    manifest = loader.load(manifest_path)

    assert len(manifest.documents) == 1

    document = manifest.documents[0]

    assert document.file_path == pdf_path.resolve()
    assert document.document_id == "stroke-2020"
    assert document.condition == "STROKE"
    assert document.care_phase == "POST_DISCHARGE"
    assert document.topic == "LIFESTYLE"


def test_load_rejects_duplicate_document_ids(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path=manifest_path,
        documents=[
            {
                "file_path": "pdfs/stroke-v1.pdf",
                "document_id": "stroke-2020",
                "title": "Stroke Guideline V1",
                "condition": "STROKE",
            },
            {
                "file_path": "pdfs/stroke-v2.pdf",
                "document_id": "stroke-2020",
                "title": "Stroke Guideline V2",
                "condition": "STROKE",
            },
        ],
    )

    loader = GuidelineManifestLoader()

    with pytest.raises(
        ValueError,
        match="중복된 document_id",
    ):
        loader.load(manifest_path)


def test_load_rejects_missing_pdf_file(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path=manifest_path,
        documents=[
            {
                "file_path": "pdfs/missing.pdf",
                "document_id": "missing-pdf",
                "title": "Missing PDF Guideline",
                "condition": "STROKE",
            }
        ],
    )

    loader = GuidelineManifestLoader()

    with pytest.raises(
        FileNotFoundError,
        match="PDF 파일을 찾을 수 없습니다",
    ):
        loader.load(manifest_path)


def test_load_rejects_non_pdf_file(
    tmp_path: Path,
) -> None:
    document_directory = tmp_path / "documents"
    document_directory.mkdir()

    text_path = document_directory / "guideline.txt"
    text_path.write_text(
        "PDF가 아닌 테스트 문서",
        encoding="utf-8",
    )

    manifest_path = tmp_path / "manifest.json"
    write_manifest(
        manifest_path=manifest_path,
        documents=[
            {
                "file_path": ("documents/guideline.txt"),
                "document_id": "text-guideline",
                "title": "Text Guideline",
                "condition": "STROKE",
            }
        ],
    )

    loader = GuidelineManifestLoader()

    with pytest.raises(
        ValueError,
        match="PDF 파일만",
    ):
        loader.load(manifest_path)
