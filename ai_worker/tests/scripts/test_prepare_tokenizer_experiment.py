import json
from pathlib import Path

import pytest

from ai_worker.schemas.knowledge import KnowledgeChunk
from scripts import prepare_tokenizer_experiment as module

DATASET_VERSION = "knowledge-full-v17-function-ingredients"


def _chunk(document_id: str, content: str, *, chunk_id: str = "a" * 64) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "embedding_text": f"[원문]\\n{content}",
        "token_count": 1,
        "metadata": {
            "source_id": "source",
            "document_id": document_id,
            "title": document_id,
            "provider": "test",
            "access_scope": "PUBLIC",
            "document_type": "REGULATORY_DRUG_LABEL",
            "dataset_version": DATASET_VERSION,
            "section_type": "FUNCTION",
            "section_title": "Approved section",
            "page_start": 1,
            "page_end": 1,
            "chunk_index": 0,
            "content_hash": "b" * 64,
        },
    }


def _page(document_id: str, content: str) -> dict:
    return {
        "content": content,
        "metadata": {
            "source_id": "source",
            "document_id": document_id,
            "title": document_id,
            "provider": "test",
            "access_scope": "PUBLIC",
            "document_type": "REGULATORY_DRUG_LABEL",
            "dataset_version": DATASET_VERSION,
        },
        "page_number": 1,
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _source_root(tmp_path: Path, *, approved_hashes: list[str] | None = None) -> Path:
    root = tmp_path / "v17"
    _write_jsonl(root / "release/chunks/doc.jsonl", [_chunk("doc", "approved baseline")])
    _write_jsonl(root / "quarantine/text/doc.jsonl", [_page("doc", "normalized approved baseline")])
    _write_jsonl(root / "quarantine/text/extra.jsonl", [_page("extra", "must stay quarantined")])
    (root / "reports").mkdir(parents=True)
    (root / "reports/corpus-manifest.json").write_text(
        json.dumps(
            {
                "pilots": [
                    {
                        "document_id": "doc",
                        "verified_section_headings": ["Approved section"],
                        "approved_chunk_content_hashes": approved_hashes or [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "annotations.yaml").write_text(
        "schema_version: knowledge-interaction-annotations-v1\ndocuments: []\n",
        encoding="utf-8",
    )
    return root


class _FakeSplitter:
    def __init__(self, encoding: str, candidates: dict[tuple[str, str], list[dict]]) -> None:
        self.encoding = encoding
        self._candidates = candidates

    def split(self, pages, *, verified_section_headings=None):
        document_id = pages[0].metadata.document_id
        return [KnowledgeChunk.model_validate(item) for item in self._candidates[(self.encoding, document_id)]]


def _patch_splitters(monkeypatch, candidates: dict[tuple[str, str], list[dict]]) -> None:
    monkeypatch.setattr(
        module,
        "build_splitter",
        lambda *, tokenizer_encoding, interaction_annotations: _FakeSplitter(tokenizer_encoding, candidates),
    )


def _output_chunks(output: Path, arm: str) -> list[dict]:
    return [
        json.loads(line)
        for path in (output / arm / "chunks").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_excludes_quarantine_only_documents_from_both_arms(tmp_path: Path, monkeypatch) -> None:
    """Would fail if the allowlist is derived from normalized files instead of release chunks."""
    source_root = _source_root(tmp_path)
    candidates = {
        (encoding, "doc"): [_chunk("doc", "approved baseline", chunk_id="c" * 64)]
        for encoding in ("cl100k_base", "o200k_base")
    }
    _patch_splitters(monkeypatch, candidates)

    module.run_experiment(
        source_root=source_root, annotations_path=tmp_path / "annotations.yaml", output_root=tmp_path / "out"
    )

    for arm in ("cl100k_base", "o200k_base"):
        assert [chunk["metadata"]["document_id"] for chunk in _output_chunks(tmp_path / "out", arm)] == ["doc"]


def test_changed_cl100k_baseline_freezes_both_arms_to_baseline_chunks(tmp_path: Path, monkeypatch) -> None:
    """Would fail if a cl100k mismatch still lets either tokenizer publish fresh segmentation."""
    source_root = _source_root(tmp_path)
    candidates = {
        ("cl100k_base", "doc"): [_chunk("doc", "changed regenerated content", chunk_id="c" * 64)],
        ("o200k_base", "doc"): [_chunk("doc", "approved baseline", chunk_id="d" * 64)],
    }
    _patch_splitters(monkeypatch, candidates)

    result = module.run_experiment(
        source_root=source_root, annotations_path=tmp_path / "annotations.yaml", output_root=tmp_path / "out"
    )

    assert [chunk["content"] for chunk in _output_chunks(tmp_path / "out", "cl100k_base")] == ["approved baseline"]
    assert [chunk["content"] for chunk in _output_chunks(tmp_path / "out", "o200k_base")] == ["approved baseline"]
    assert result["documents"]["doc"]["freeze_reasons"] == ["cl100k_content_mismatch"]
    assert result["counts"]["regenerated_changed_documents"] == {"cl100k": 1, "o200k": 0}
    assert result["counts"]["selected_changed_document_count"] == 0


def test_approved_hashes_freeze_without_transferring_approval_to_new_manifest(tmp_path: Path, monkeypatch) -> None:
    """Would fail if an approved content hash permits rechunking or is copied as a new approval."""
    source_root = _source_root(tmp_path, approved_hashes=["b" * 64])
    candidates = {
        (encoding, "doc"): [_chunk("doc", "approved baseline", chunk_id="c" * 64)]
        for encoding in ("cl100k_base", "o200k_base")
    }
    _patch_splitters(monkeypatch, candidates)

    module.run_experiment(
        source_root=source_root, annotations_path=tmp_path / "annotations.yaml", output_root=tmp_path / "out"
    )

    manifest = json.loads((tmp_path / "out/experiment-manifest.json").read_text(encoding="utf-8"))
    assert [chunk["chunk_id"] for chunk in _output_chunks(tmp_path / "out", "o200k_base")] == ["a" * 64]
    assert manifest["documents"]["doc"]["freeze_reasons"] == ["pilot_approved_chunk_content_hashes"]
    assert "approved_chunk_content_hashes" not in manifest
    assert manifest["annotations_checksum"]["path"].endswith("annotations.yaml")
    assert "quarantine/text/doc.jsonl" in manifest["source_checksums"]


def test_refuses_to_overwrite_an_existing_output_directory(tmp_path: Path) -> None:
    """Would fail if a later experiment could replace an already reviewable artifact."""
    source_root = _source_root(tmp_path)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        module.run_experiment(
            source_root=source_root, annotations_path=tmp_path / "annotations.yaml", output_root=output
        )
