import json
from hashlib import sha256
from pathlib import Path

import pytest

from ai_worker.rag.loaders.knowledge_ocr_artifact_loader import (
    KnowledgeOcrArtifactLoader,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
)


def _metadata() -> KnowledgeMetadata:
    return KnowledgeMetadata(
        source_id="ocr-source",
        document_id="ocr-document",
        title="OCR 문서",
        provider="OCR 제공자",
        access_scope=KnowledgeAccessScope.PUBLIC,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
        dataset_version="ocr-test-v1",
    )


def _artifact(*, source_sha256: str) -> dict:
    return {
        "schema_version": "knowledge-ocr-artifact-v1",
        "document_id": "ocr-document",
        "source_sha256": source_sha256,
        "renderer": {"name": "pdf-rasterizer", "version": "v1", "dpi": 300},
        "ocr_engine": {"name": "fake-ocr", "version": "v1"},
        "pages": [
            {
                "page_number": 1,
                "image_sha256": "b" * 64,
                "width": 600,
                "height": 800,
                "rotation_degrees": 0,
                "blocks": [
                    {
                        "block_id": "right-1",
                        "text": "오른쪽 첫 문장",
                        "confidence": 0.99,
                        "bbox": {"x0": 350, "top": 50, "x1": 500, "bottom": 80},
                        "line_break": True,
                    },
                    {
                        "block_id": "left-2",
                        "text": "왼쪽 두 번째 문장",
                        "confidence": 0.99,
                        "bbox": {"x0": 20, "top": 100, "x1": 180, "bottom": 130},
                        "line_break": True,
                    },
                    {
                        "block_id": "left-1",
                        "text": "왼쪽 첫 문장",
                        "confidence": 0.99,
                        "bbox": {"x0": 20, "top": 50, "x1": 180, "bottom": 80},
                        "line_break": True,
                    },
                    {
                        "block_id": "right-2",
                        "text": "오른쪽 두 번째 문장",
                        "confidence": 0.99,
                        "bbox": {"x0": 350, "top": 100, "x1": 500, "bottom": 130},
                        "line_break": True,
                    },
                ],
            }
        ],
    }


def test_load_restores_left_to_right_column_order_from_ocr_blocks(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"OCR source")
    source_sha256 = sha256(source_path.read_bytes()).hexdigest()
    (artifact_root / "ocr-document.json").write_text(
        json.dumps(_artifact(source_sha256=source_sha256), ensure_ascii=False),
        encoding="utf-8",
    )

    pages = KnowledgeOcrArtifactLoader(
        artifact_root=artifact_root,
    ).load(source_path, _metadata())

    assert pages[0].content == (
        "왼쪽 첫 문장\n왼쪽 두 번째 문장\n\n오른쪽 첫 문장\n오른쪽 두 번째 문장"
    )
    assert [block.content for block in pages[0].blocks] == [
        "왼쪽 첫 문장\n왼쪽 두 번째 문장",
        "오른쪽 첫 문장\n오른쪽 두 번째 문장",
    ]
    assert pages[0].extraction_warnings == [KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT]


def test_rejects_artifact_when_source_hash_does_not_match_manifest(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    source_path = tmp_path / "source.pdf"
    source_path.write_bytes(b"actual source")
    (artifact_root / "ocr-document.json").write_text(
        json.dumps(_artifact(source_sha256="a" * 64)),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="원본 SHA-256"):
        KnowledgeOcrArtifactLoader(
            artifact_root=artifact_root,
        ).load(source_path, _metadata())
