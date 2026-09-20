"""Create a conservative, offline tokenizer rechunking experiment from v17 artifacts."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import tiktoken

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.splitters.knowledge_splitter import KnowledgeSplitter
from ai_worker.schemas.knowledge import KnowledgeChunk, KnowledgePage

TOKENIZER_ENCODINGS = ("cl100k_base", "o200k_base")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an offline, review-preserving cl100k/o200k rechunking experiment.",
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def build_splitter(
    *,
    tokenizer_encoding: str,
    interaction_annotations: KnowledgeInteractionAnnotationRegistry,
) -> KnowledgeSplitter:
    return KnowledgeSplitter(
        tokenizer_encoding=tokenizer_encoding,
        interaction_annotations=interaction_annotations,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _chunk_metadata(chunk: KnowledgeChunk) -> dict[str, Any]:
    return chunk.metadata.model_dump(mode="json")


def _same_content_and_metadata(left: list[KnowledgeChunk], right: list[KnowledgeChunk]) -> tuple[bool, str | None]:
    if [chunk.content for chunk in left] != [chunk.content for chunk in right]:
        return False, "cl100k_content_mismatch"
    if [_chunk_metadata(chunk) for chunk in left] != [_chunk_metadata(chunk) for chunk in right]:
        return False, "cl100k_metadata_mismatch"
    return True, None


def _section_content(chunks: list[KnowledgeChunk]) -> dict[tuple[str, str], str]:
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for chunk in chunks:
        grouped[(str(chunk.metadata.section_type), chunk.metadata.section_title or "")].append(chunk.content)
    return {section: _normalize_text(" ".join(contents)) for section, contents in grouped.items()}


def _o200k_is_contained(candidate: list[KnowledgeChunk], baseline: list[KnowledgeChunk]) -> bool:
    candidate_sections = _section_content(candidate)
    baseline_sections = _section_content(baseline)
    if candidate_sections.keys() != baseline_sections.keys():
        return False
    return all(candidate_sections[section] == baseline_sections[section] for section in baseline_sections)


def _with_token_count(chunk: KnowledgeChunk, encoding_name: str) -> KnowledgeChunk:
    token_count = len(tiktoken.get_encoding(encoding_name).encode(chunk.content))
    return chunk.model_copy(update={"token_count": token_count})


def _pilot_details(corpus_manifest: dict[str, Any], document_id: str) -> dict[str, Any]:
    for pilot in corpus_manifest.get("pilots", []):
        if pilot.get("document_id") == document_id:
            return pilot
    return {}


def run_experiment(  # noqa: C901
    *,
    source_root: Path,
    annotations_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"output directory already exists: {output_root}")

    baseline_paths = sorted((source_root / "release/chunks").glob("*.jsonl"))
    if not baseline_paths:
        raise ValueError("source-root must contain release/chunks/*.jsonl")
    corpus_manifest_path = source_root / "reports/corpus-manifest.json"
    corpus_manifest = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
    annotations = KnowledgeInteractionAnnotationRegistry.from_yaml(annotations_path)
    splitters = {
        encoding: build_splitter(tokenizer_encoding=encoding, interaction_annotations=annotations)
        for encoding in TOKENIZER_ENCODINGS
    }

    documents: dict[str, dict[str, Any]] = {}
    arm_rows: dict[str, dict[str, list[dict[str, Any]]]] = {encoding: {} for encoding in TOKENIZER_ENCODINGS}
    dataset_versions: set[str] = set()
    checksum_paths = [*baseline_paths, corpus_manifest_path]

    for baseline_path in baseline_paths:
        baseline = [KnowledgeChunk.model_validate(row) for row in _read_jsonl(baseline_path)]
        if not baseline:
            continue
        document_id = baseline[0].metadata.document_id
        if any(chunk.metadata.document_id != document_id for chunk in baseline):
            raise ValueError(f"baseline chunk file mixes document ids: {baseline_path}")
        dataset_versions.update(chunk.metadata.dataset_version for chunk in baseline)
        text_path = source_root / "quarantine/text" / f"{document_id}.jsonl"
        if not text_path.exists():
            raise ValueError(f"missing normalized quarantine text for allowlisted document: {document_id}")
        pages = [KnowledgePage.model_validate(row) for row in _read_jsonl(text_path)]
        if not pages:
            raise ValueError(f"normalized quarantine text is empty: {document_id}")
        checksum_paths.append(text_path)

        pilot = _pilot_details(corpus_manifest, document_id)
        headings = list(pilot.get("verified_section_headings") or [])
        approved_hashes = list(pilot.get("approved_chunk_content_hashes") or [])
        regenerated = {
            encoding: splitters[encoding].split(pages, verified_section_headings=headings)
            for encoding in TOKENIZER_ENCODINGS
        }
        same_cl100k, cl100k_reason = _same_content_and_metadata(regenerated["cl100k_base"], baseline)
        same_o200k, _ = _same_content_and_metadata(regenerated["o200k_base"], baseline)
        freeze_reasons: list[str] = []
        if not same_cl100k and cl100k_reason is not None:
            freeze_reasons.append(cl100k_reason)
        if approved_hashes:
            freeze_reasons.append("pilot_approved_chunk_content_hashes")
        if not _o200k_is_contained(regenerated["o200k_base"], baseline):
            freeze_reasons.append("o200k_content_not_contained")

        frozen = bool(freeze_reasons)
        selected_matches: dict[str, bool] = {}
        for encoding in TOKENIZER_ENCODINGS:
            if frozen:
                selected = baseline
                if encoding == "o200k_base":
                    selected = [_with_token_count(chunk, encoding) for chunk in selected]
            elif encoding == "cl100k_base" and same_cl100k:
                selected = baseline
            elif encoding == "o200k_base" and same_o200k:
                selected = [_with_token_count(chunk, encoding) for chunk in baseline]
            else:
                selected = regenerated[encoding]
            selected_matches[encoding], _ = _same_content_and_metadata(selected, baseline)
            arm_rows[encoding][baseline_path.name] = [chunk.model_dump(mode="json") for chunk in selected]

        documents[document_id] = {
            "baseline_chunk_path": str(baseline_path.relative_to(source_root)),
            "normalized_text_path": str(text_path.relative_to(source_root)),
            "baseline_chunk_count": len(baseline),
            "regenerated_chunk_counts": {encoding: len(regenerated[encoding]) for encoding in TOKENIZER_ENCODINGS},
            "cl100k_content_and_metadata_match": same_cl100k,
            "o200k_content_and_metadata_match": same_o200k,
            "selected_content_and_metadata_matches": selected_matches,
            "freeze_reasons": freeze_reasons,
            "frozen": frozen,
        }

    if len(dataset_versions) != 1:
        raise ValueError("baseline allowlist must use exactly one dataset_version")
    dataset_version = dataset_versions.pop()

    output_root.mkdir(parents=True)
    for encoding, files in arm_rows.items():
        for filename, rows in files.items():
            _write_jsonl(output_root / encoding / "chunks" / filename, rows)
    result = {
        "offline": True,
        "source_root": str(source_root),
        "dataset_version": dataset_version,
        "tokenizers": list(TOKENIZER_ENCODINGS),
        "arms": {
            "cl100k_base": {"collection_name": f"{dataset_version}-cl100k-experimental"},
            "o200k_base": {"collection_name": f"{dataset_version}-o200k-experimental"},
        },
        "source_checksums": {
            (str(path.relative_to(source_root)) if path.is_relative_to(source_root) else str(path)): _sha256(path)
            for path in checksum_paths
        },
        "annotations_checksum": {
            "path": str(annotations_path.resolve()),
            "sha256": _sha256(annotations_path),
        },
        "provenance": {
            "baseline_allowlist": "release/chunks/*.jsonl",
            "normalized_pages": "quarantine/text/<document_id>.jsonl",
            "no_ocr_or_normalization": True,
            "new_chunks_are_segmentation_only": True,
            "approval_hashes_not_transferred": True,
        },
        "counts": {
            "document_count": len(documents),
            "frozen_document_count": sum(item["frozen"] for item in documents.values()),
            "regenerated_changed_documents": {
                "cl100k": sum(not item["cl100k_content_and_metadata_match"] for item in documents.values()),
                "o200k": sum(not item["o200k_content_and_metadata_match"] for item in documents.values()),
            },
            "selected_changed_document_count": sum(
                not all(item["selected_content_and_metadata_matches"].values()) for item in documents.values()
            ),
            "chunks": {encoding: sum(len(rows) for rows in files.values()) for encoding, files in arm_rows.items()},
        },
        "documents": documents,
    }
    (output_root / "experiment-manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    args = parse_args()
    result = run_experiment(
        source_root=args.source_root,
        annotations_path=args.annotations,
        output_root=args.output,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
