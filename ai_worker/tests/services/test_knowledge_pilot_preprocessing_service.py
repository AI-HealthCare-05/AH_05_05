import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_worker.rag.normalizers.knowledge_normalizer import KnowledgeNormalizer
from ai_worker.rag.splitters.knowledge_splitter import (
    ChunkingPolicy,
    KnowledgeSplitter,
    WordTokenCounter,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)
from ai_worker.schemas.knowledge_manifest import KnowledgePilotEntry
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    _COMPLEX_TABLE_PATTERN,
    KnowledgeAutomaticQualityStatus,
    KnowledgeChunkReviewStatus,
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


class FakeResearchTableKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "Abstract\nThis review describes medication and nutrient evidence.\n"
                    "Results\nTable 1. Nutrient Dose Population Outcome\n"
                    "Group A 10 mg adults lower absorption\n"
                    "Group B 20 mg adults unchanged absorption.\n"
                    "A short concluding sentence is provided for readers."
                ),
                metadata=metadata,
                page_number=1,
            )
        ]


class FakeLayoutRiskKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "Abstract\nThis review explains an interaction.\n"
                    "Results\nThe observed result requires manual review."
                ),
                metadata=metadata,
                page_number=1,
                extraction_warnings=[
                    KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT,
                ],
            )
        ]


class FakeRotatedTextRiskKnowledgePdfLoader:
    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        return [
            KnowledgePage(
                content=(
                    "Abstract\nThis review explains an interaction.\n"
                    "Results\nA rotated table heading requires manual review."
                ),
                metadata=metadata,
                page_number=1,
                extraction_warnings=[
                    KnowledgeExtractionWarning.ROTATED_TEXT,
                ],
            )
        ]


class FakeUnsafeLayoutKnowledgePdfLoader:
    def __init__(self, warning: KnowledgeExtractionWarning) -> None:
        self._warning = warning

    def load(self, file_path: Path, metadata) -> list[KnowledgePage]:
        content = "Abstract\nThis review explains an interaction.\nResults\nThe extracted layout is not safe to index."
        if self._warning == KnowledgeExtractionWarning.READING_ORDER_UNSAFE:
            content += "\n" + ("MergedTableHeading" * 10)
        return [
            KnowledgePage(
                content=content,
                metadata=metadata,
                page_number=1,
                extraction_warnings=[self._warning],
            )
        ]


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


@pytest.mark.parametrize(
    "heading",
    [
        "Table 1. Interaction evidence",
        "Table I Summary of mechanisms",
    ],
)
def test_complex_table_pattern_accepts_numeric_and_roman_labels(
    heading: str,
) -> None:
    assert _COMPLEX_TABLE_PATTERN.search(heading)


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


def test_preprocess_marks_complex_table_and_missing_metadata_for_review(
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
                    "source_id": "research",
                    "document_id": "research-table",
                    "repo_path": "raw/research_table.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "표와 검색 메타데이터 검증",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: 연구논문
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeResearchTableKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "REVIEW"
    assert {reason.value for reason in report.reason_codes} >= {
        "COMPLEX_TABLE_REQUIRES_REVIEW",
        "MISSING_SEARCH_ENTITIES",
        "UNKNOWN_EVIDENCE_LEVEL",
    }


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


def test_review_sample_indices_include_every_complex_table_chunk() -> None:
    chunks = [
        SimpleNamespace(
            content=f"일반 설명 {index}",
            token_count=100 + index,
            metadata=SimpleNamespace(
                section_type=KnowledgeSectionType.RESULTS,
            ),
        )
        for index in range(7)
    ]
    chunks[1].content = "Table 1. First interaction table"
    chunks[5].content = "Table 2. Second interaction table"

    sample_indices = KnowledgePilotPreprocessingService._sample_indices(
        chunks,
        document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
    )

    assert 1 in sample_indices
    assert 5 in sample_indices


def test_review_document_includes_only_chunks_that_need_review() -> None:
    reviews = [
        SimpleNamespace(
            chunk_index=0,
            status=KnowledgeChunkReviewStatus.APPROVED,
        ),
        SimpleNamespace(
            chunk_index=1,
            status=KnowledgeChunkReviewStatus.PENDING,
        ),
        SimpleNamespace(
            chunk_index=2,
            status=KnowledgeChunkReviewStatus.REPAIR_REQUIRED,
        ),
        SimpleNamespace(
            chunk_index=3,
            status=KnowledgeChunkReviewStatus.EXCLUDED_NON_CONTENT,
        ),
    ]

    indices = KnowledgePilotPreprocessingService._review_required_indices(
        reviews,
    )

    assert indices == [1, 2]


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


def test_preprocess_propagates_reviewed_document_metadata_to_every_chunk(
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
                    "source_id": "research",
                    "document_id": "reviewed-research",
                    "repo_path": "raw/review.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "검수 메타데이터 상속 검증",
                    "title": "Levothyroxine interaction systematic review",
                    "source_url": "https://doi.org/10.1234/example",
                    "doi": "10.1234/example",
                    "authors": ["Example Author"],
                    "publication_year": 2023,
                    "drug_names": ["levothyroxine"],
                    "evidence_level": "SYSTEMATIC_REVIEW",
                    "study_population": "HUMAN",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeResearchTableKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=output_root,
        dataset_version="pilot-v1",
    )

    chunk_rows = [
        json.loads(line)
        for line in (output_root / "chunks" / "reviewed-research.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert chunk_rows
    for row in chunk_rows:
        metadata = row["metadata"]
        assert metadata["title"] == ("Levothyroxine interaction systematic review")
        assert metadata["source_url"] == "https://doi.org/10.1234/example"
        assert metadata["doi"] == "10.1234/example"
        assert metadata["authors"] == ["Example Author"]
        assert metadata["publication_year"] == 2023
        assert metadata["drug_names"] == ["levothyroxine"]
        assert metadata["evidence_level"] == (KnowledgeEvidenceLevel.SYSTEMATIC_REVIEW.value)
        assert metadata["study_population"] == (KnowledgeStudyPopulation.HUMAN.value)


def test_preprocess_marks_multi_column_extraction_for_review(
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
                    "source_id": "research",
                    "document_id": "layout-risk",
                    "repo_path": "raw/layout.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "다단 읽기 순서 검증",
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/layout",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeLayoutRiskKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "REVIEW"
    assert report.source_document_path == Path("raw/layout.pdf")
    assert report.layout_warning_pages == [1]
    assert "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW" in [reason.value for reason in report.reason_codes]
    review = (tmp_path / "processed" / report.review_sample_path).read_text(
        encoding="utf-8",
    )
    assert "- 원본 PDF: `raw/layout.pdf`" in review
    assert "- 다단 레이아웃: 원본 p.1" in review
    assert "- [ ] `APPROVED`" in review
    assert "- [ ] `KEEP_PENDING`" in review
    assert "- [ ] `REPROCESS_REQUIRED`" in review


def test_preprocess_releases_manually_verified_multi_column_layout(
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
                    "source_id": "research",
                    "document_id": "verified-layout",
                    "repo_path": "raw/layout.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "검수된 다단 읽기 순서",
                    "manual_review_status": "APPROVED",
                    "approved_review_reason_codes": ["MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW"],
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/layout",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeLayoutRiskKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status == KnowledgeAutomaticQualityStatus.PASS
    assert report.reason_codes == []
    assert report.pending_chunk_count == 0
    assert report.release_ready is True
    assert result.ready_for_bulk_source_ids == ["research"]


def test_preprocess_marks_rotated_text_extraction_for_review(
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
                    "source_id": "research",
                    "document_id": "rotated-text-risk",
                    "repo_path": "raw/rotated.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "회전 표제 읽기 순서 검증",
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/rotated",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeRotatedTextRiskKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "REVIEW"
    assert report.rotated_text_warning_count == 1
    assert report.rotated_text_warning_pages == [1]
    assert "ROTATED_TEXT_REQUIRES_REVIEW" in [reason.value for reason in report.reason_codes]


def test_preprocess_releases_manually_verified_rotated_text(
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
                    "source_id": "research",
                    "document_id": "verified-rotated-text",
                    "repo_path": "raw/rotated.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "사람이 원문과 대조한 회전 텍스트",
                    "manual_review_status": "APPROVED",
                    "approved_review_reason_codes": [
                        "ROTATED_TEXT_REQUIRES_REVIEW"
                    ],
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/rotated",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeRotatedTextRiskKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status == KnowledgeAutomaticQualityStatus.PASS
    assert report.reason_codes == []
    assert report.pending_chunk_count == 0
    assert report.release_ready is True
    review = (tmp_path / "processed" / report.review_sample_path).read_text(
        encoding="utf-8",
    )
    assert "- 회전 텍스트: 원본 p.1" in review


@pytest.mark.parametrize(
    ("warning", "expected_reason"),
    [
        (
            KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE,
            "TABLE_STRUCTURE_UNSAFE",
        ),
        (
            KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
            "READING_ORDER_UNSAFE",
        ),
    ],
)
def test_preprocess_blocks_unsafe_coordinate_extraction(
    tmp_path: Path,
    warning: KnowledgeExtractionWarning,
    expected_reason: str,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "research",
                    "document_id": "unsafe-layout",
                    "repo_path": "raw/unsafe.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "좌표 추출 안전성 검증",
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/unsafe",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeUnsafeLayoutKnowledgePdfLoader(warning),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "BLOCKED"
    assert expected_reason in [reason.value for reason in report.reason_codes]


@pytest.mark.parametrize(
    "warning",
    [
        KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE,
        KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
    ],
)
def test_preprocess_accepts_manually_verified_unsafe_layout_reason(
    tmp_path: Path,
    warning: KnowledgeExtractionWarning,
) -> None:
    manifest_path = tmp_path / "pilot_manifest.json"
    sources_path = tmp_path / "sources.yaml"
    write_json(
        manifest_path,
        {
            "policy": "test",
            "pilots": [
                {
                    "source_id": "research",
                    "document_id": "verified-unsafe-layout",
                    "repo_path": "raw/unsafe.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "사람이 원문과 대조한 좌표 추출",
                    "manual_review_status": "APPROVED",
                    "approved_review_reason_codes": [warning.value],
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/unsafe",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeUnsafeLayoutKnowledgePdfLoader(warning),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status == KnowledgeAutomaticQualityStatus.PASS
    assert report.reason_codes == []


def test_preprocess_quarantines_unsafe_chunks_and_blocks_release(
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
                    "source_id": "research",
                    "document_id": "unsafe-layout",
                    "repo_path": "raw/unsafe.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "청크 단위 격리 검증",
                    "title": "Interaction review",
                    "source_url": "https://doi.org/10.1234/unsafe",
                    "drug_names": ["example drug"],
                    "evidence_level": "REVIEW_ARTICLE",
                    "manual_review_status": "APPROVED",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: research
    provider: Journal
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeUnsafeLayoutKnowledgePdfLoader(
            KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
        ),
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
    assert report.release_ready is False
    assert report.repair_required_chunk_count > 0
    assert {review.status.value for review in report.chunk_reviews} == {
        "REPAIR_REQUIRED",
    }
    assert (output_root / "quarantine" / "text" / "unsafe-layout.jsonl").exists()
    assert (output_root / "quarantine" / "chunks" / "unsafe-layout.jsonl").exists()
    assert not (output_root / "release" / "chunks" / "unsafe-layout.jsonl").exists()


def test_chunk_manual_approval_is_scoped_to_matching_content_hash() -> None:
    approved_hash = "a" * 64
    pending_hash = "b" * 64
    shared_metadata = {
        "source_id": "research",
        "document_id": "unsafe-layout",
        "title": "Interaction review",
        "provider": "Journal",
        "access_scope": KnowledgeAccessScope.DEMO_RESTRICTED,
        "document_type": KnowledgeDocumentType.RESEARCH_ARTICLE,
        "dataset_version": "pilot-v1",
        "section_type": KnowledgeSectionType.RESULTS,
        "page_start": 1,
        "page_end": 1,
    }
    chunks = [
        KnowledgeChunk(
            chunk_id="1" * 64,
            content="First manually reviewed chunk.",
            embedding_text="First manually reviewed chunk.",
            token_count=4,
            metadata=KnowledgeChunkMetadata(
                **shared_metadata,
                chunk_index=0,
                content_hash=approved_hash,
            ),
        ),
        KnowledgeChunk(
            chunk_id="2" * 64,
            content="Second unreviewed chunk.",
            embedding_text="Second unreviewed chunk.",
            token_count=3,
            metadata=KnowledgeChunkMetadata(
                **shared_metadata,
                chunk_index=1,
                content_hash=pending_hash,
            ),
        ),
    ]
    pages = [
        KnowledgePage(
            content="Unsafe page extraction.",
            metadata=chunks[0].metadata,
            page_number=1,
            extraction_warnings=[
                KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
            ],
        )
    ]
    pilot = KnowledgePilotEntry.model_validate(
        {
            "source_id": "research",
            "document_id": "unsafe-layout",
            "repo_path": "raw/unsafe.pdf",
            "processing_status": "TEXT_EXTRACTABLE",
            "selection_reason": "청크 단위 승인 검증",
            "approved_chunk_content_hashes": [approved_hash],
        }
    )

    reviews = KnowledgePilotPreprocessingService._build_chunk_reviews(
        pilot=pilot,
        pages=pages,
        chunks=chunks,
        automatic_status=KnowledgeAutomaticQualityStatus.BLOCKED,
    )

    assert [review.status for review in reviews] == [
        KnowledgeChunkReviewStatus.APPROVED,
        KnowledgeChunkReviewStatus.REPAIR_REQUIRED,
    ]
    assert reviews[0].reason_codes == ["READING_ORDER_UNSAFE"]


def test_table_warning_does_not_quarantine_text_on_the_same_page() -> None:
    metadata = KnowledgeChunkMetadata(
        source_id="regulatory",
        document_id="label",
        title="LEVO-T prescribing information",
        provider="FDA",
        access_scope=KnowledgeAccessScope.PUBLIC,
        document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        dataset_version="pilot-v1",
        section_type=KnowledgeSectionType.OVERVIEW,
        content_kind=KnowledgeContentKind.TEXT,
        page_start=16,
        page_end=17,
        chunk_index=0,
        content_hash="a" * 64,
    )
    chunk = KnowledgeChunk(
        chunk_id="1" * 64,
        content="LEVO-T tablets are supplied as follows.",
        embedding_text="LEVO-T tablets are supplied as follows.",
        token_count=7,
        metadata=metadata,
    )
    page = KnowledgePage(
        content=chunk.content,
        metadata=KnowledgeMetadata(
            source_id="regulatory",
            document_id="label",
            title="LEVO-T prescribing information",
            provider="FDA",
            access_scope=KnowledgeAccessScope.PUBLIC,
            document_type=KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
            dataset_version="pilot-v1",
        ),
        page_number=17,
        extraction_warnings=[KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE],
    )
    pilot = KnowledgePilotEntry.model_validate(
        {
            "source_id": "regulatory",
            "document_id": "label",
            "repo_path": "raw/label.pdf",
            "processing_status": "TEXT_EXTRACTABLE",
            "selection_reason": "표 설명 본문 격리 오탐 방지",
        }
    )

    reviews = KnowledgePilotPreprocessingService._build_chunk_reviews(
        pilot=pilot,
        pages=[page],
        chunks=[chunk],
        automatic_status=KnowledgeAutomaticQualityStatus.BLOCKED,
    )

    assert reviews[0].status == KnowledgeChunkReviewStatus.PENDING
    assert reviews[0].reason_codes == []


def test_preprocess_marks_regulatory_table_for_review(
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
                    "source_id": "regulatory",
                    "document_id": "regulatory-table",
                    "repo_path": "raw/label.pdf",
                    "processing_status": "TEXT_EXTRACTABLE",
                    "selection_reason": "허가문서 표 구조 검증",
                    "title": "LEVO-T prescribing information",
                    "source_url": "https://example.test/label",
                    "drug_names": ["LEVO-T", "levothyroxine sodium"],
                    "evidence_level": "REGULATORY",
                    "study_population": "NOT_APPLICABLE",
                }
            ],
        },
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: regulatory
    provider: FDA
    access_scope: PUBLIC
    target: QDRANT
    document_type: REGULATORY_DRUG_LABEL
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    service = KnowledgePilotPreprocessingService(
        repo_root=tmp_path,
        loader=FakeResearchTableKnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(token_counter=WordTokenCounter()),
    )

    result = service.preprocess(
        manifest_path=manifest_path,
        sources_path=sources_path,
        output_root=tmp_path / "processed",
        dataset_version="pilot-v1",
    )

    report = result.document_reports[0]
    assert report.automatic_status.value == "REVIEW"
    assert report.complex_table_chunk_count == 1
    assert [location.model_dump() for location in report.complex_table_locations] == [
        {
            "chunk_index": 0,
            "page_start": 1,
            "page_end": 1,
        }
    ]
    assert "COMPLEX_TABLE_REQUIRES_REVIEW" in [reason.value for reason in report.reason_codes]
    review = (tmp_path / "processed" / report.review_sample_path).read_text(
        encoding="utf-8",
    )
    assert "Table 1. Nutrient Dose Population Outcome" in review
    assert "- 복잡한 표: 청크 0, 원본 p.1" in review
