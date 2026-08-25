from pathlib import Path

import pytest

from ai_worker.rag.loaders.knowledge_chunk_loader import (
    KnowledgeChunkLoader,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeDocumentType,
    KnowledgeSectionType,
)


def build_chunk(
    chunk_id: str,
    *,
    dataset_version: str = "knowledge-pilot-v1",
    index_eligible: bool = True,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        content=f"근거 원문 {chunk_id[0]}",
        embedding_text=f"[문서] 시험 문서\n[원문]\n근거 원문 {chunk_id[0]}",
        token_count=10,
        metadata=KnowledgeChunkMetadata(
            source_id="pilot-source",
            document_id=f"document-{chunk_id[0]}",
            title="시험 문서",
            provider="시험 제공자",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
            dataset_version=dataset_version,
            ingredient_names=["비타민 B6"],
            index_eligible=index_eligible,
            section_type=KnowledgeSectionType.CAUTION,
            section_title="섭취 시 주의사항",
            page_start=1,
            page_end=1,
            chunk_index=0,
            content_hash="c" * 64,
        ),
    )


def write_chunks(path: Path, chunks: list[KnowledgeChunk]) -> None:
    path.write_text(
        "\n".join(chunk.model_dump_json() for chunk in chunks) + "\n",
        encoding="utf-8",
    )


def test_load_reads_jsonl_files_in_stable_order(tmp_path: Path) -> None:
    write_chunks(tmp_path / "b.jsonl", [build_chunk("b" * 64)])
    write_chunks(tmp_path / "a.jsonl", [build_chunk("a" * 64)])

    chunks = KnowledgeChunkLoader().load(
        tmp_path,
        expected_dataset_version="knowledge-pilot-v1",
    )

    assert [chunk.chunk_id for chunk in chunks] == [
        "a" * 64,
        "b" * 64,
    ]


def test_load_rejects_empty_release_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="청크 JSONL"):
        KnowledgeChunkLoader().load(
            tmp_path,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_load_reports_file_and_line_for_invalid_json(tmp_path: Path) -> None:
    invalid_path = tmp_path / "broken.jsonl"
    invalid_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"broken\.jsonl:1",
    ):
        KnowledgeChunkLoader().load(
            tmp_path,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_load_rejects_duplicate_chunk_ids(tmp_path: Path) -> None:
    duplicate = build_chunk("a" * 64)
    write_chunks(tmp_path / "first.jsonl", [duplicate])
    write_chunks(tmp_path / "second.jsonl", [duplicate])

    with pytest.raises(ValueError, match="중복"):
        KnowledgeChunkLoader().load(
            tmp_path,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_load_rejects_mixed_dataset_versions(tmp_path: Path) -> None:
    write_chunks(
        tmp_path / "mixed.jsonl",
        [
            build_chunk("a" * 64),
            build_chunk(
                "b" * 64,
                dataset_version="knowledge-pilot-v2",
            ),
        ],
    )

    with pytest.raises(ValueError, match="dataset_version"):
        KnowledgeChunkLoader().load(
            tmp_path,
            expected_dataset_version="knowledge-pilot-v1",
        )


def test_load_rejects_index_ineligible_chunk(tmp_path: Path) -> None:
    write_chunks(
        tmp_path / "ineligible.jsonl",
        [build_chunk("a" * 64, index_eligible=False)],
    )

    with pytest.raises(ValueError, match="인덱싱 대상"):
        KnowledgeChunkLoader().load(
            tmp_path,
            expected_dataset_version="knowledge-pilot-v1",
        )
