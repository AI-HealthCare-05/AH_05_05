import json
from pathlib import Path

import pytest

from ai_worker.rag.normalizers.knowledge_normalizer import KnowledgeNormalizer
from ai_worker.rag.splitters.knowledge_splitter import (
    KnowledgeSplitter,
    WordTokenCounter,
)
from ai_worker.schemas.knowledge import KnowledgePage
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingService,
)


class FakeKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 B6\n"
                    "기능성 내용 단백질 및 아미노산 이용에 필요\n"
                    "일일섭취량 0.45~67 mg\n"
                    "섭취 시 주의사항 손발 저림이 생기면 전문가와 상담할 것"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def test_preprocess_writes_only_index_eligible_text_pilots(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    output_root = tmp_path / "processed"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "vitamin-b6",
                    "repo_path": "raw/1-10_비타민_B6.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                },
                {
                    "source_id": "supplement_code",
                    "document_id": "ocr-document",
                    "repo_path": "raw/ocr.pdf",
                    "processing_status": "OCR_REQUIRED",
                    "selection_reason": "test",
                },
                {
                    "source_id": "disabled_source",
                    "document_id": "disabled-document",
                    "repo_path": "raw/disabled.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                },
                {
                    "source_id": "mysql_source",
                    "document_id": "records",
                    "repo_path": "raw/records.csv",
                    "processing_status": "STRUCTURED_SOURCE",
                    "selection_reason": "test",
                },
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement_code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw
  - source_id: disabled_source
    provider: 출처 확인 필요
    access_scope: DEMO_RESTRICTED
    target: QDRANT_DISABLED_UNTIL_VERIFIED
    document_type: SUPPLEMENT_INTERACTION_MONOGRAPH
    raw_path: raw
  - source_id: mysql_source
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: MYSQL
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )

    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )
    stale_chunk = output_root / "chunks" / "disabled-document.jsonl"
    stale_chunk.parent.mkdir(parents=True)
    stale_chunk.write_text('{"stale": true}\n', encoding="utf-8")

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    assert result.processed_document_count == 1
    assert result.chunk_count == 3
    assert {item.reason for item in result.skipped_documents} == {
        "OCR_REQUIRED",
        "SOURCE_NOT_INDEX_ELIGIBLE",
        "STRUCTURED_SOURCE",
    }

    text_path = output_root / "text" / "vitamin-b6.jsonl"
    chunk_path = output_root / "chunks" / "vitamin-b6.jsonl"
    assert text_path.exists()
    assert chunk_path.exists()

    chunks = [json.loads(line) for line in chunk_path.read_text(encoding="utf-8").splitlines()]
    assert all(chunk["metadata"]["index_eligible"] for chunk in chunks)
    assert all(chunk["metadata"]["dataset_version"] == "pilot-v1" for chunk in chunks)
    assert "[성분] 비타민 B6" in chunks[0]["embedding_text"]
    assert not stale_chunk.exists()


def test_preprocess_is_deterministic(tmp_path: Path) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    output_root = tmp_path / "processed"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "vitamin-b6",
                    "repo_path": "raw/1-10_비타민_B6.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement_code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )
    first = (output_root / "chunks" / "vitamin-b6.jsonl").read_text(encoding="utf-8")
    service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )
    second = (output_root / "chunks" / "vitamin-b6.jsonl").read_text(encoding="utf-8")

    assert first == second


def test_preprocess_rejects_pilot_path_outside_source_root(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "wrong-source-document",
                    "repo_path": "raw/other_source/document.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement_code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/supplement_code
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    with pytest.raises(ValueError, match="출처 경로"):
        service.preprocess(
            manifest_path=manifest_path,
            sources_path=sources_path,
            output_root=tmp_path / "processed",
            dataset_version="pilot-v1",
        )


def test_preprocess_rejects_document_id_with_path_separator(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "../outside",
                    "repo_path": "raw/document.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement_code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    with pytest.raises(ValueError, match="document_id"):
        service.preprocess(
            manifest_path=manifest_path,
            sources_path=sources_path,
            output_root=tmp_path / "processed",
            dataset_version="pilot-v1",
        )


def test_preprocess_rejects_source_path_outside_repository(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    outside_root = tmp_path.parent / "outside-knowledge"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "outside-document",
                    "repo_path": str(outside_root / "document.pdf"),
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "test",
                }
            ],
        },
    )
    sources_path.write_text(
        f"""
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement_code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: {outside_root}
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    with pytest.raises(ValueError, match="저장소 경로"):
        service.preprocess(
            manifest_path=manifest_path,
            sources_path=sources_path,
            output_root=tmp_path / "processed",
            dataset_version="pilot-v1",
        )


def test_preprocess_removes_output_for_document_removed_from_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    output_root = tmp_path / "processed"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources: []
""".strip(),
        encoding="utf-8",
    )
    stale_text = output_root / "text" / "removed-document.jsonl"
    stale_chunk = output_root / "chunks" / "removed-document.jsonl"
    stale_text.parent.mkdir(parents=True)
    stale_chunk.parent.mkdir(parents=True)
    stale_text.write_text('{"stale": true}\n', encoding="utf-8")
    stale_chunk.write_text('{"stale": true}\n', encoding="utf-8")
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    assert result.processed_document_count == 0
    assert not stale_text.exists()
    assert not stale_chunk.exists()
