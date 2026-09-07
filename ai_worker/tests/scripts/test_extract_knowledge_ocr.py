import json
import sys
from pathlib import Path

import pytest

from scripts import extract_knowledge_ocr


def test_main_dry_run_lists_ocr_targets_without_provider_call(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    manifest_path = tmp_path / "ocr-manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "public-document",
                "source_id": "source",
                "repo_path": "raw/public.pdf",
                "source_sha256": "a" * 64,
                "origin": "CATALOG",
                "access_scope": "PUBLIC",
            }
        )
        + "\n"
        + json.dumps(
            {
                "document_id": "restricted-document",
                "source_id": "source",
                "repo_path": "raw/restricted.pdf",
                "source_sha256": "b" * 64,
                "origin": "DYNAMIC",
                "access_scope": "DEMO_RESTRICTED",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract_knowledge_ocr.py",
            "--repo-root",
            str(tmp_path),
            "--ocr-manifest",
            str(manifest_path),
        ],
    )

    extract_knowledge_ocr.main()

    assert json.loads(capsys.readouterr().out) == {
        "mode": "DRY_RUN",
        "ocr_engine": "tesseract",
        "external_ocr_mode": "NONE",
        "ocr_document_count": 2,
        "demo_restricted_document_count": 1,
        "artifact_root": str(tmp_path / "data/knowledge/processed/ocr-artifacts"),
    }


def test_main_rejects_external_fallback_without_an_explicit_opt_in(
    monkeypatch,
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "ocr-manifest.jsonl"
    manifest_path.write_text(
        json.dumps(
            {
                "document_id": "public-document",
                "source_id": "source",
                "repo_path": "raw/public.pdf",
                "source_sha256": "a" * 64,
                "origin": "CATALOG",
                "access_scope": "PUBLIC",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "extract_knowledge_ocr.py",
            "--repo-root",
            str(tmp_path),
            "--ocr-manifest",
            str(manifest_path),
            "--execute",
            "--engine",
            "tesseract-with-clova-fallback",
        ],
    )

    with pytest.raises(ValueError, match="--allow-clova-fallback"):
        extract_knowledge_ocr.main()
