import json
from pathlib import Path

import pytest

from ai_worker.rag.normalizers.knowledge_normalizer import KnowledgeNormalizer
from ai_worker.rag.splitters.knowledge_splitter import (
    ChunkingPolicy,
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
                    "제조기준1)\n"
                    "원료(1)\n"
                    "가 피리독신염산염 (Pyridoxine Hydrochloride)\n"
                    "규격2)\n"
                    "성상 고유의 색택과 향미를 가짐(1) :\n"
                    "비타민 B6 표시량의 80~150%(2) :\n"
                    "대장균군 음성(3) :\n"
                    "제품의 요건3)\n"
                    "기능성 내용 단백질 및 아미노산 이용에 필요\n"
                    "일일섭취량 0.45~67 mg\n"
                    "섭취 시 주의사항 손발 저림이 생기면 전문가와 상담할 것\n"
                    "시험법4)\n"
                    "성상 제4 시험법"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeUnstructuredKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "이 문서는 제목 경계 없이 이어지는 충분히 긴 설명입니다. "
                    "약명과 성분, 주의사항이 한 문단에 섞여 있어 사람이 원본과 "
                    "대조하여 청킹 규칙을 추가해야 하는 대표 문서입니다."
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeBlockedKnowledgeSplitter(KnowledgeSplitter):
    @staticmethod
    def policy_for(document_type) -> ChunkingPolicy:
        return ChunkingPolicy(
            target_min_tokens=1,
            hard_max_tokens=1,
            overlap_tokens=0,
        )


class FakeMixedQualityKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        if file_path.name == "too-short.pdf":
            return [
                KnowledgePage(
                    content="짧은 문서",
                    metadata=metadata,
                    page_number=1,
                )
            ]
        return FakeKnowledgePdfLoader().load(file_path, metadata)


class FakeLongReviewKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        body = " ".join(f"검수단어{index:03d}" for index in range(250))
        return [
            KnowledgePage(
                content=f"기능성 내용 {body} 최종검수표식",
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeFailingKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        raise RuntimeError("PDF 추출 실패")


class FakeSuspiciousSupplementUnitLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 A\n"
                    "제품의 요건3)\n"
                    "기능성 내용(1)\n"
                    "가 어두운 곳에서 시각 적응을 위해 필요( )\n"
                    "일일섭취량 (2) : 210 ~ 1,000 g RAE\n"
                    "시험법4)\n"
                    "성상 제 성상시험법(1) : 4. 2-7"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeUnresolvedSupplementReferenceLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 A\n"
                    "1) 제조기준\n"
                    "(1) 원료\n"
                    "(가) 레티닐 팔미트산염 (Retinyl Palmitate)\n"
                    "3) 제품의 요건\n"
                    "(2) 일일섭취량\n"
                    "(가) 9). (9). (가)의 경우: 0.42~7 mg\n"
                    "4) 시험법\n"
                    "(1) 성상시험법"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeContaminatedSupplementSectionLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 B6\n"
                    "제품의 요건3)\n"
                    "기능성 내용(1)\n"
                    "가 단백질 및 아미노산 이용에 필요( )\n"
                    "섭취 시 주의사항 (3)\n"
                    "이상사례 발생 시 전문가와 상담할 것\n"
                    "시험 법\n"
                    "성상 제 성상시험법(1) : 4. 2-7"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeMalformedSupplementTextLoader:
    def __init__(self, malformed_text: str) -> None:
        self._malformed_text = malformed_text

    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 A\n"
                    "제조기준1)\n"
                    "원료(1)\n"
                    "가 레티닐 팔미트산염 (Retinyl Palmitate)\n"
                    "규격2)\n"
                    "성상 고유의 색택과 향미를 가짐(1) :\n"
                    "비타민 A 표시량의 80~150%(2) :\n"
                    "대장균군 음성(3) :\n"
                    "제품의 요건3)\n"
                    "기능성 내용(1)\n"
                    "가 어두운 곳에서 시각 적응을 위해 필요\n"
                    f"{self._malformed_text}\n"
                    "일일섭취량 (2) : 210 ~ 1,000 μg RAE\n"
                    "시험법4)\n"
                    "성상 제4 시험법"
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeMissingRequiredSupplementSectionLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "비타민 B6\n"
                    "제조기준1)\n"
                    "원료(1)\n"
                    "가 피리독신염산염 (Pyridoxine Hydrochloride)\n"
                    "규격2)\n"
                    "성상 고유의 색택과 향미를 가짐(1) :\n"
                    "비타민 B6 표시량의 80~150%(2) :\n"
                    "대장균군 음성(3) :\n"
                    "제품의 요건3)\n"
                    "일일섭취량 (2) : 0.45 ~ 67 mg\n"
                    "시험법4)\n"
                    "성상 제4 시험법"
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
    assert result.chunk_count == 4
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
    stale_review = output_root / "review" / "removed-document.md"
    stale_text.parent.mkdir(parents=True)
    stale_chunk.parent.mkdir(parents=True)
    stale_review.parent.mkdir(parents=True)
    stale_text.write_text('{"stale": true}\n', encoding="utf-8")
    stale_chunk.write_text('{"stale": true}\n', encoding="utf-8")
    stale_review.write_text("stale\n", encoding="utf-8")
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
    assert not stale_review.exists()


def test_preprocess_writes_quality_report_and_review_sample(
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
                    "selection_reason": "유형별 대표 문서",
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

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    assert result.ready_for_bulk_source_ids == []
    assert len(result.document_reports) == 1
    report = result.document_reports[0]
    assert report.automatic_status.value == "PASS"
    assert report.manual_review_status.value == "PENDING"
    assert report.page_count == 1
    assert report.chunk_count == 4
    assert report.semantic_section_ratio == 1.0

    quality_report = output_root / result.quality_report_path
    review_sample = output_root / report.review_sample_path
    assert quality_report.exists()
    assert review_sample.exists()
    review_content = review_sample.read_text(encoding="utf-8")
    assert "유형별 대표 문서" in review_content
    assert "원본 읽기 순서" in review_content
    for section_type in (
        "INGREDIENT",
        "FUNCTION",
        "DAILY_INTAKE",
        "CAUTION",
    ):
        assert f"· {section_type} ·" in review_content


def test_preprocess_marks_approved_quality_pilot_ready_for_bulk(
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
                    "document_id": "vitamin-b6",
                    "repo_path": "raw/1-10_비타민_B6.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "유형별 대표 문서",
                    "manual_review_status": "APPROVED",
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

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    assert result.ready_for_bulk_source_ids == ["supplement_code"]


def test_preprocess_blocks_supplement_code_without_semantic_sections(
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
                    "document_id": "unstructured-document",
                    "repo_path": "raw/unstructured.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "제목 경계 검증",
                    "manual_review_status": "APPROVED",
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
        loader=FakeUnstructuredKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    assert result.ready_for_bulk_source_ids == []
    report = result.document_reports[0]
    assert report.automatic_status.value == "BLOCKED"
    assert [reason.value for reason in report.reason_codes] == [
        "NO_SEMANTIC_SECTIONS",
        "MISSING_SUPPLEMENT_CONTEXT",
    ]


def test_preprocess_does_not_publish_automatically_blocked_chunks(
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
                    "document_id": "oversized-document",
                    "repo_path": "raw/oversized.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "최대 토큰 차단 검증",
                    "manual_review_status": "APPROVED",
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
        splitter=FakeBlockedKnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    assert result.processed_document_count == 0
    assert result.document_reports[0].automatic_status.value == "BLOCKED"
    assert result.skipped_documents[0].reason == "AUTOMATIC_QUALITY_BLOCKED"
    assert not (output_root / "chunks" / "oversized-document.jsonl").exists()


def test_preprocess_does_not_ready_source_with_failed_representative(
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
                    "document_id": "passing-document",
                    "repo_path": "raw/passing.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "정상 대표 문서",
                    "manual_review_status": "APPROVED",
                },
                {
                    "source_id": "supplement_code",
                    "document_id": "failed-document",
                    "repo_path": "raw/too-short.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "추출 실패 대표 문서",
                    "manual_review_status": "APPROVED",
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
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeMixedQualityKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    assert result.processed_document_count == 1
    assert result.ready_for_bulk_source_ids == []
    assert result.skipped_documents[-1].reason == "TEXT_QUALITY_REVIEW"


def test_preprocess_review_sample_keeps_full_selected_chunk(
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
                    "document_id": "long-review-document",
                    "repo_path": "raw/long-review.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "긴 청크 표본 검증",
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
        loader=FakeLongReviewKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    review_path = output_root / result.document_reports[0].review_sample_path
    assert "최종검수표식" in review_path.read_text(encoding="utf-8")


def test_preprocess_invalidates_previous_report_before_processing(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    output_root = tmp_path / "processed"
    report_path = output_root / "reports" / "preprocessing-quality.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text('{"stale": true}', encoding="utf-8")
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "supplement_code",
                    "document_id": "failing-document",
                    "repo_path": "raw/failing.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "실패 시 보고서 무효화 검증",
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
        loader=FakeFailingKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    with pytest.raises(RuntimeError, match="PDF 추출 실패"):
        service.preprocess(
            manifest_path=manifest_path,
            sources_path=sources_path,
            output_root=output_root,
            dataset_version="pilot-v1",
        )

    assert not report_path.exists()


@pytest.mark.parametrize(
    ("loader", "expected_reason"),
    [
        (
            FakeSuspiciousSupplementUnitLoader(),
            "SUSPICIOUS_SUPPLEMENT_UNIT",
        ),
        (
            FakeUnresolvedSupplementReferenceLoader(),
            "UNRESOLVED_HIERARCHY_REFERENCE",
        ),
        (
            FakeContaminatedSupplementSectionLoader(),
            "SUPPLEMENT_SECTION_CONTAMINATION",
        ),
        (
            FakeMalformedSupplementTextLoader("비타민 보충 목적으로 비타민 원료를 A A"),
            "MALFORMED_SUPPLEMENT_TEXT",
        ),
        (
            FakeMalformedSupplementTextLoader("최소함량기준은 비타민 와 베타카로틴의 합으로 적용"),
            "MALFORMED_SUPPLEMENT_TEXT",
        ),
        (
            FakeMalformedSupplementTextLoader("베타카로틴의 비타민 전환계수는 을 적용함 다만A 1/2"),
            "MALFORMED_SUPPLEMENT_TEXT",
        ),
        (
            FakeMalformedSupplementTextLoader("유성비타민 지방산 에스테르(Dry Formed Vitamin A) A\n의 형태로 사용"),
            "MALFORMED_SUPPLEMENT_TEXT",
        ),
        (
            FakeMissingRequiredSupplementSectionLoader(),
            "MISSING_REQUIRED_SUPPLEMENT_SECTION",
        ),
    ],
)
def test_preprocess_blocks_unsafe_supplement_code_chunks(
    tmp_path: Path,
    loader,
    expected_reason: str,
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
                    "document_id": "unsafe-supplement-code",
                    "repo_path": "raw/unsafe.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "건강기능식품공전 안전 검사",
                    "manual_review_status": "APPROVED",
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
        loader=loader,
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "BLOCKED"
    assert expected_reason in [reason.value for reason in report.reason_codes]
    assert result.ready_for_bulk_source_ids == []
    assert not (output_root / "chunks" / "unsafe-supplement-code.jsonl").exists()
