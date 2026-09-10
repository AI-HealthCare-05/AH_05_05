import json
from pathlib import Path

import yaml

from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.schemas.knowledge_manifest import (
    KnowledgeManualReviewStatus,
    KnowledgeOcrDocumentSelectionDecision,
    KnowledgeOcrDocumentSelectionManifest,
    KnowledgePilotManifest,
)
from ai_worker.services.knowledge_corpus_preprocessing_service import (
    KnowledgeCorpusManifestBuilder,
    KnowledgeCorpusPreprocessingService,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityReasonCode,
    KnowledgeAutomaticQualityStatus,
    KnowledgeChunkReviewRecord,
    KnowledgeChunkReviewStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )


def write_ocr_artifact(
    path: Path,
    *,
    document_id: str,
    source_sha256: str,
    text: str,
    confidence: float,
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-ocr-artifact-v1",
                "document_id": document_id,
                "source_sha256": source_sha256,
                "renderer": {"name": "test", "version": "v1", "dpi": 300},
                "ocr_engine": {"name": "tesseract", "version": "v1"},
                "pages": [
                    {
                        "page_number": 1,
                        "image_sha256": "b" * 64,
                        "width": 600,
                        "height": 800,
                        "rotation_degrees": 0,
                        "blocks": [
                            {
                                "block_id": "line-1",
                                "text": text,
                                "confidence": confidence,
                                "bbox": {"x0": 1, "top": 1, "x1": 200, "bottom": 20},
                                "line_break": True,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_ocr_selection_manifest_classifies_every_ocr_required_document() -> None:
    repo_root = Path(__file__).parents[3]
    document_records = [
        json.loads(line)
        for line in (repo_root / "data/knowledge/manifests/documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = KnowledgeOcrDocumentSelectionManifest.model_validate(
        yaml.safe_load(
            (repo_root / "data/knowledge/manifests/ocr_document_selection.yaml").read_text(
                encoding="utf-8",
            ),
        ),
    )

    ocr_required_ids = {
        record["document_id"] for record in document_records if record["processing_status"] == "OCR_REQUIRED"
    }
    selected_ids = {
        selection.document_id
        for selection in manifest.selections
        if selection.decision == KnowledgeOcrDocumentSelectionDecision.INCLUDE
    }

    assert {selection.document_id for selection in manifest.selections} == ocr_required_ids
    assert selected_ids == {"kpicia_adverse_case_report-408e6bddec7da059"}


def test_official_omega3_code_has_searchable_supplement_aliases() -> None:
    """공식 EPA·DHA 공전은 일반 사용자의 오메가3 표현으로 검색돼야 한다."""
    repo_root = Path(__file__).parents[3]
    records = [
        json.loads(line)
        for line in (repo_root / "data/knowledge/manifests/documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    omega3 = next(record for record in records if record["document_id"] == "mfds_supplement_code-40a0dea0c535ba59")

    assert omega3["ingredient_names"] == ["오메가3", "EPA", "DHA"]
    assert omega3["entity_catalog_entries"] == [
        {
            "canonical_name": "오메가3",
            "aliases": ["EPA", "DHA", "EPA 및 DHA 함유 유지"],
            "entity_type": "INGREDIENT_NAME",
            "kind": "SUPPLEMENT",
        }
    ]


def test_restricted_micronutrient_reviews_are_registered_with_safe_metadata() -> None:
    repo_root = Path(__file__).parents[3]
    sources = yaml.safe_load(
        (repo_root / "data/knowledge/manifests/sources.yaml").read_text(encoding="utf-8"),
    )["sources"]
    source = next(item for item in sources if item["source_id"] == "research_micronutrient_interactions")
    records = [
        json.loads(line)
        for line in (repo_root / "data/knowledge/manifests/documents.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    interaction_review = next(
        record for record in records if record["document_id"] == "research_micronutrient_interactions-e3b164ce9cc98cc6"
    )
    pilot_manifest = KnowledgePilotManifest.model_validate_json(
        (repo_root / "data/knowledge/manifests/additional_micronutrient_interactions_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    sandstrom_pilot = next(
        pilot
        for pilot in pilot_manifest.pilots
        if pilot.document_id == "research_micronutrient_interactions-e3b164ce9cc98cc6"
    )
    bond_pilot = next(
        pilot
        for pilot in pilot_manifest.pilots
        if pilot.document_id == "research_micronutrient_interactions-bc3fd489c828415e"
    )

    assert source["access_scope"] == "DEMO_RESTRICTED"
    assert source["target"] == "QDRANT"
    assert interaction_review["ingredient_names"] == ["철분", "아연", "구리", "칼슘", "비타민 C"]
    assert interaction_review["evidence_level"] == "REVIEW_ARTICLE"
    assert interaction_review["source_id"] == source["source_id"]
    assert interaction_review["access_scope"] == source["access_scope"]
    assert interaction_review["repo_path"].startswith(
        "data/knowledge/raw/demo_restricted/research/micronutrient_interactions/"
    )
    assert interaction_review["sha256"] == "e3b164ce9cc98cc68afe8194fa30e1f757d26aa40b0a8fad97ee387d5d8b9580"
    assert sandstrom_pilot.manual_review_status == KnowledgeManualReviewStatus.APPROVED
    assert bond_pilot.manual_review_status == KnowledgeManualReviewStatus.PENDING


def test_builder_selects_approved_qdrant_text_documents(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "public-code",
                "document_id": "magnesium-document",
                "repo_path": "raw/public/1-16 마그네슘.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "restricted-review",
                "document_id": "review-document",
                "repo_path": "raw/restricted/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
            },
            {
                "source_id": "public-code",
                "document_id": "ocr-document",
                "repo_path": "raw/public/ocr.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "c" * 64,
            },
            {
                "source_id": "disabled-source",
                "document_id": "disabled-document",
                "repo_path": "raw/disabled/source.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "d" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: public-code
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/public
  - source_id: restricted-review
    provider: 약학정보원
    access_scope: DEMO_RESTRICTED
    target: QDRANT
    document_type: PHARM_REVIEW
    raw_path: raw/restricted
  - source_id: disabled-source
    provider: 출처 확인 필요
    access_scope: DEMO_RESTRICTED
    target: QDRANT_DISABLED_UNTIL_VERIFIED
    document_type: RESEARCH_ARTICLE
    raw_path: raw/disabled
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 2,
                "chunk_count": 2,
                "ready_for_bulk_source_ids": [
                    "public-code",
                    "restricted-review",
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == [
        "magnesium-document",
        "review-document",
    ]
    assert all(entry.manual_review_status.value == "APPROVED" for entry in manifest.pilots)


def test_builder_excludes_document_marked_not_index_eligible(tmp_path: Path) -> None:
    """A known fragment must remain in raw storage without entering a release."""
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    quality_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "supplement-source",
                "document_id": "usable-document",
                "repo_path": "raw/supplements/usable.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "supplement-source",
                "document_id": "corrupted-fragment",
                "repo_path": "raw/supplements/p2-01.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
                "index_eligible": False,
                "index_exclusion_reason": "단독 문맥이 없는 깨진 페이지 조각",
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: supplement-source
    provider: 식품안전나라
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/supplements
""".strip(),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps({"ready_for_bulk_source_ids": ["supplement-source"]}),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=quality_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["usable-document"]


def test_builder_includes_ocr_document_only_when_artifact_is_available(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    quality_path = tmp_path / "quality.json"
    selection_path = tmp_path / "ocr-selection.yaml"
    artifact_root = tmp_path / "artifacts"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "ocr-source",
                "document_id": "ocr-document",
                "repo_path": "raw/ocr/document.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: ocr-source
    provider: OCR 출처
    access_scope: PUBLIC
    target: QDRANT
    document_type: ADVERSE_CASE_REPORT
    raw_path: raw/ocr
""".strip(),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps({"ready_for_bulk_source_ids": ["ocr-source"]}),
        encoding="utf-8",
    )
    selection_path.write_text(
        """
schema_version: knowledge-ocr-selection-v1
policy: 검증된 OCR 문서만 챗봇 근거로 사용한다.
selections:
  - document_id: ocr-document
    decision: INCLUDE
    reason: 테스트용 중요 OCR 문서다.
""".strip(),
        encoding="utf-8",
    )
    artifact_root.mkdir()
    write_ocr_artifact(
        artifact_root / "ocr-document.json",
        document_id="ocr-document",
        source_sha256="a" * 64,
        text="읽기 쉬운 정상 OCR 문장입니다.",
        confidence=0.98,
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=quality_path,
        ocr_artifact_root=artifact_root,
        ocr_document_selection_path=selection_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["ocr-document"]
    assert manifest.pilots[0].processing_status.value == "TEXT_EXTRACTABLE"


def test_builder_uses_ocr_selection_allowlist_for_bulk_chunking(
    tmp_path: Path,
) -> None:
    """Only OCR documents explicitly selected for chatbot evidence may enter a release."""
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    quality_path = tmp_path / "quality.json"
    selection_path = tmp_path / "ocr-selection.yaml"
    artifact_root = tmp_path / "artifacts"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "ocr-source",
                "document_id": "important-interaction",
                "repo_path": "raw/ocr/important.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            },
            {
                "source_id": "ocr-source",
                "document_id": "non-core-case-report",
                "repo_path": "raw/ocr/non-core.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "b" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: ocr-source
    provider: OCR 출처
    access_scope: PUBLIC
    target: QDRANT
    document_type: ADVERSE_CASE_REPORT
    raw_path: raw/ocr
""".strip(),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps({"ready_for_bulk_source_ids": ["ocr-source"]}),
        encoding="utf-8",
    )
    selection_path.write_text(
        """
schema_version: knowledge-ocr-selection-v1
policy: 챗봇의 약물·영양제 상호작용 근거로 필요한 OCR 문서만 허용한다.
selections:
  - document_id: important-interaction
    decision: INCLUDE
    reason: 약물 상호작용 질문과 직접 관련된 사례다.
  - document_id: non-core-case-report
    decision: EXCLUDE
    reason: 개별 이상사례로 일반 안내 근거에 사용하지 않는다.
""".strip(),
        encoding="utf-8",
    )
    artifact_root.mkdir()
    write_ocr_artifact(
        artifact_root / "important-interaction.json",
        document_id="important-interaction",
        source_sha256="a" * 64,
        text="읽기 쉬운 정상 OCR 문장입니다.",
        confidence=0.98,
    )
    write_ocr_artifact(
        artifact_root / "non-core-case-report.json",
        document_id="non-core-case-report",
        source_sha256="b" * 64,
        text="읽기 쉬운 정상 OCR 문장입니다.",
        confidence=0.98,
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=quality_path,
        ocr_artifact_root=artifact_root,
        ocr_document_selection_path=selection_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == [
        "important-interaction",
    ]


def test_builder_excludes_low_quality_ocr_artifact_from_bulk_chunking(
    tmp_path: Path,
) -> None:
    """An artifact with fragmented Hangul must stay out of the bulk release."""
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    quality_path = tmp_path / "quality.json"
    artifact_root = tmp_path / "artifacts"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "ocr-source",
                "document_id": "fragmented-ocr-document",
                "repo_path": "raw/ocr/document.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: ocr-source
    provider: OCR 출처
    access_scope: PUBLIC
    target: QDRANT
    document_type: ADVERSE_CASE_REPORT
    raw_path: raw/ocr
""".strip(),
        encoding="utf-8",
    )
    quality_path.write_text(
        json.dumps({"ready_for_bulk_source_ids": ["ocr-source"]}),
        encoding="utf-8",
    )
    artifact_root.mkdir()
    write_ocr_artifact(
        artifact_root / "fragmented-ocr-document.json",
        document_id="fragmented-ocr-document",
        source_sha256="a" * 64,
        text="건 강 기 능 식 품 원 료 심 사 보 고 서",
        confidence=0.98,
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=quality_path,
        ocr_artifact_root=artifact_root,
    )

    assert manifest.pilots == []


def test_builder_uses_manually_approved_representative_for_ocr_source_approval(
    tmp_path: Path,
) -> None:
    """A reviewed representative must allow a quality-passing OCR sibling to chunk."""
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_manifest_path = tmp_path / "pilot-manifest.json"
    selection_path = tmp_path / "ocr-selection.yaml"
    artifact_root = tmp_path / "artifacts"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "ocr-source",
                "document_id": "ocr-document",
                "repo_path": "raw/ocr/document.pdf",
                "processing_status": "OCR_REQUIRED",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: ocr-source
    provider: OCR 출처
    access_scope: PUBLIC
    target: QDRANT
    document_type: ADVERSE_CASE_REPORT
    raw_path: raw/ocr
""".strip(),
        encoding="utf-8",
    )
    pilot_manifest_path.write_text(
        json.dumps(
            {
                "policy": "대표 문서 검수",
                "pilots": [
                    {
                        "source_id": "ocr-source",
                        "document_id": "reviewed-representative",
                        "repo_path": "raw/ocr/representative.pdf",
                        "processing_status": "TEXT_EXTRACTABLE",
                        "selection_reason": "대표 검수",
                        "manual_review_status": "APPROVED",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    selection_path.write_text(
        """
schema_version: knowledge-ocr-selection-v1
policy: 검증된 OCR 문서만 챗봇 근거로 사용한다.
selections:
  - document_id: ocr-document
    decision: INCLUDE
    reason: 테스트용 중요 OCR 문서다.
""".strip(),
        encoding="utf-8",
    )
    artifact_root.mkdir()
    write_ocr_artifact(
        artifact_root / "ocr-document.json",
        document_id="ocr-document",
        source_sha256="a" * 64,
        text="읽기 쉬운 정상 OCR 문장입니다.",
        confidence=0.98,
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_manifest_path=pilot_manifest_path,
        ocr_artifact_root=artifact_root,
        ocr_document_selection_path=selection_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["ocr-document"]


def test_builder_unions_approved_sources_from_multiple_quality_reports(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    first_report_path = tmp_path / "first-quality.json"
    second_report_path = tmp_path / "second-quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "first-source",
                "document_id": "first-document",
                "repo_path": "raw/first/first.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "second-source",
                "document_id": "second-document",
                "repo_path": "raw/second/second.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "b" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: first-source
    provider: First
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/first
  - source_id: second-source
    provider: Second
    access_scope: PUBLIC
    target: QDRANT
    document_type: RESEARCH_ARTICLE
    raw_path: raw/second
""".strip(),
        encoding="utf-8",
    )
    first_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "first",
                "processed_document_count": 0,
                "chunk_count": 0,
                "ready_for_bulk_source_ids": ["first-source"],
            }
        ),
        encoding="utf-8",
    )
    second_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "second",
                "processed_document_count": 0,
                "chunk_count": 0,
                "ready_for_bulk_source_ids": ["second-source"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_paths=[first_report_path, second_report_path],
    )

    assert [entry.document_id for entry in manifest.pilots] == [
        "first-document",
        "second-document",
    ]


def test_builder_accepts_legacy_quality_report_without_new_document_fields(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "legacy-quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "legacy-source",
                "document_id": "legacy-document",
                "repo_path": "raw/legacy/legacy.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            }
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: legacy-source
    provider: Legacy
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw/legacy
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "legacy-v2",
                "processed_document_count": 1,
                "chunk_count": 1,
                "document_reports": [
                    {
                        "document_id": "legacy-document",
                        "source_id": "legacy-source",
                    }
                ],
                "ready_for_bulk_source_ids": ["legacy-source"],
            },
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["legacy-document"]


def test_builder_deduplicates_identical_file_hashes(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "source",
                "document_id": "first-document",
                "repo_path": "raw/first.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
            {
                "source_id": "source",
                "document_id": "duplicate-document",
                "repo_path": "raw/second.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
            },
        ],
    )
    sources_path.write_text(
        """
schema_version: knowledge-sources-v1
sources:
  - source_id: source
    provider: 식품의약품안전처
    access_scope: PUBLIC
    target: QDRANT
    document_type: SUPPLEMENT_CODE
    raw_path: raw
""".strip(),
        encoding="utf-8",
    )
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": ["source"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    assert [entry.document_id for entry in manifest.pilots] == ["first-document"]


def test_builder_preserves_reviewed_document_metadata(tmp_path: Path) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "research",
                "document_id": "review-document",
                "repo_path": "raw/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
                "title": "Reviewed interaction article",
                "source_url": "https://doi.org/10.1234/review",
                "doi": "10.1234/review",
                "authors": ["Example Author"],
                "publication_year": 2024,
                "drug_names": ["warfarin"],
                "ingredient_names": ["vitamin K"],
                "entity_catalog_entries": [
                    {
                        "canonical_name": "vitamin K",
                        "aliases": ["비타민 K", "비타민케이"],
                        "entity_type": "INGREDIENT_NAME",
                        "kind": "SUPPLEMENT",
                    }
                ],
                "evidence_level": "SYSTEMATIC_REVIEW",
                "study_population": "HUMAN",
            }
        ],
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
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": ["research"],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
    )

    entry = manifest.pilots[0]
    assert entry.title == "Reviewed interaction article"
    assert entry.source_url == "https://doi.org/10.1234/review"
    assert entry.doi == "10.1234/review"
    assert entry.authors == ["Example Author"]
    assert entry.publication_year == 2024
    assert entry.drug_names == ["warfarin"]
    assert entry.ingredient_names == ["vitamin K"]
    assert entry.entity_catalog_entries[0].canonical_name == "vitamin K"
    assert entry.entity_catalog_entries[0].aliases == ["비타민 K", "비타민케이"]
    assert entry.evidence_level.value == "SYSTEMATIC_REVIEW"
    assert entry.study_population.value == "HUMAN"


def test_builder_inherits_verified_repairs_from_pilot_manifest(
    tmp_path: Path,
) -> None:
    documents_path = tmp_path / "documents.jsonl"
    sources_path = tmp_path / "sources.yaml"
    pilot_report_path = tmp_path / "quality.json"
    pilot_manifest_path = tmp_path / "pilot-manifest.json"
    write_jsonl(
        documents_path,
        [
            {
                "source_id": "research",
                "document_id": "review-document",
                "repo_path": "raw/review.pdf",
                "processing_status": "TEXT_EXTRACTABLE",
                "sha256": "a" * 64,
                "title": "Reviewed interaction article",
            }
        ],
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
    pilot_report_path.write_text(
        json.dumps(
            {
                "dataset_version": "pilot-v1",
                "processed_document_count": 1,
                "chunk_count": 1,
                "ready_for_bulk_source_ids": ["research"],
            }
        ),
        encoding="utf-8",
    )
    pilot_manifest_path.write_text(
        json.dumps(
            {
                "policy": "대표 문서 검수",
                "pilots": [
                    {
                        "source_id": "research",
                        "document_id": "review-document",
                        "repo_path": "raw/review.pdf",
                        "processing_status": "TEXT_EXTRACTABLE",
                        "selection_reason": "대표 문서",
                        "manual_review_status": "APPROVED",
                        "verified_text_replacements": {
                            "intestinal wal": "intestinal wall",
                        },
                        "verified_section_headings": [
                            "Drug Interactions",
                        ],
                        "approved_review_reason_codes": [
                            "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW",
                        ],
                        "approved_chunk_content_hashes": ["b" * 64],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = KnowledgeCorpusManifestBuilder().build(
        documents_path=documents_path,
        sources_path=sources_path,
        pilot_quality_report_path=pilot_report_path,
        pilot_manifest_path=pilot_manifest_path,
    )

    entry = manifest.pilots[0]
    assert entry.selection_reason == "대표 문서"
    assert entry.verified_text_replacements == {
        "intestinal wal": "intestinal wall",
    }
    assert entry.verified_section_headings == ["Drug Interactions"]
    assert [code.value for code in entry.approved_review_reason_codes] == [
        "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW",
    ]
    assert entry.approved_chunk_content_hashes == ["b" * 64]


def build_report(
    document_id: str,
    status: KnowledgeAutomaticQualityStatus,
) -> KnowledgeDocumentPreprocessingReport:
    return KnowledgeDocumentPreprocessingReport(
        document_id=document_id,
        source_id="source",
        source_document_path=Path(f"raw/{document_id}.pdf"),
        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
        selection_reason="전체 전처리",
        automatic_status=status,
        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
        page_count=1,
        character_count=100,
        chunk_count=2 if status == KnowledgeAutomaticQualityStatus.PASS else 1,
        min_chunk_tokens=10,
        average_chunk_tokens=10,
        max_chunk_tokens=10,
        semantic_section_ratio=1,
        review_sample_path=Path(f"review/{document_id}.md"),
    )


def test_finalize_release_keeps_only_automatic_pass_documents(
    tmp_path: Path,
) -> None:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    (chunks_dir / "pass-document.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (chunks_dir / "review-document.jsonl").write_text("{}\n", encoding="utf-8")
    result = KnowledgePilotPreprocessingResult(
        dataset_version="knowledge-full-v1",
        processed_document_count=2,
        chunk_count=3,
        document_reports=[
            build_report(
                "pass-document",
                KnowledgeAutomaticQualityStatus.PASS,
            ),
            build_report(
                "review-document",
                KnowledgeAutomaticQualityStatus.REVIEW,
            ),
        ],
    )

    release = KnowledgeCorpusPreprocessingService.finalize_release(
        result=result,
        output_root=tmp_path,
    )

    assert release.processed_document_count == 1
    assert release.chunk_count == 2
    assert release.ready_for_bulk_source_ids == ["source"]
    assert (chunks_dir / "pass-document.jsonl").is_file()
    assert not (chunks_dir / "review-document.jsonl").exists()
    assert (tmp_path / "reports" / "corpus-quality-audit.json").is_file()


def test_finalize_release_keeps_approved_chunks_from_blocked_document(
    tmp_path: Path,
) -> None:
    chunks_dir = tmp_path / "chunks"
    release_chunks_dir = tmp_path / "release" / "chunks"
    chunks_dir.mkdir()
    release_chunks_dir.mkdir(parents=True)
    (chunks_dir / "partial-document.jsonl").write_text(
        "{}\n{}\n",
        encoding="utf-8",
    )
    (release_chunks_dir / "partial-document.jsonl").write_text(
        '{"chunk_id":"approved"}\n',
        encoding="utf-8",
    )
    report = build_report(
        "partial-document",
        KnowledgeAutomaticQualityStatus.BLOCKED,
    ).model_copy(
        update={
            "chunk_count": 2,
            "approved_chunk_count": 1,
            "repair_required_chunk_count": 1,
            "released_chunk_count": 1,
            "partial_release": True,
            "chunk_reviews": [
                KnowledgeChunkReviewRecord(
                    chunk_id="a" * 64,
                    chunk_index=0,
                    page_start=1,
                    page_end=1,
                    status=KnowledgeChunkReviewStatus.APPROVED,
                ),
                KnowledgeChunkReviewRecord(
                    chunk_id="b" * 64,
                    chunk_index=1,
                    page_start=1,
                    page_end=1,
                    status=KnowledgeChunkReviewStatus.REPAIR_REQUIRED,
                ),
            ],
        }
    )
    result = KnowledgePilotPreprocessingResult(
        dataset_version="knowledge-full-v1",
        processed_document_count=0,
        chunk_count=0,
        document_reports=[report],
        skipped_documents=[
            {
                "document_id": "partial-document",
                "reason": "AUTOMATIC_QUALITY_BLOCKED",
            }
        ],
    )

    release = KnowledgeCorpusPreprocessingService.finalize_release(
        result=result,
        output_root=tmp_path,
    )

    assert release.processed_document_count == 1
    assert release.chunk_count == 1
    assert release.skipped_documents == []
    released_report = release.document_reports[0]
    assert released_report.chunk_count == 1
    assert released_report.released_chunk_count == 1
    assert released_report.partial_release is True
    assert released_report.release_ready is True
    assert [review.status for review in released_report.chunk_reviews] == [KnowledgeChunkReviewStatus.APPROVED]
    assert (chunks_dir / "partial-document.jsonl").read_text() == ('{"chunk_id":"approved"}\n')


def test_preprocess_replaces_garbled_supplement_skip_with_automatic_exclusion(
    tmp_path: Path,
) -> None:
    """An unrecoverable source must remain visible as an exclusion, not an open manual-review task."""

    class StubManifestBuilder:
        def build(self, **_kwargs) -> KnowledgePilotManifest:
            return KnowledgePilotManifest(policy="test", pilots=[])

    class StubPilotService:
        def preprocess(self, **kwargs) -> KnowledgePilotPreprocessingResult:
            quarantine_text = kwargs["output_root"] / "quarantine" / "text"
            quarantine_text.mkdir(parents=True)
            (quarantine_text / "garbled-document.jsonl").write_text(
                json.dumps({"content": "ܐ FMTFNJOF ੿੄ ޛ ࠁ࠙ࢿ"}, ensure_ascii=False),
                encoding="utf-8",
            )
            review_path = kwargs["output_root"] / "review" / "garbled-document.md"
            review_path.parent.mkdir()
            review_path.write_text("자동 제외 전 검수 파일", encoding="utf-8")
            return KnowledgePilotPreprocessingResult(
                dataset_version="test-v1",
                processed_document_count=0,
                chunk_count=0,
                skipped_documents=[
                    {
                        "document_id": "garbled-document",
                        "reason": "AUTOMATIC_QUALITY_BLOCKED",
                    }
                ],
                document_reports=[
                    KnowledgeDocumentPreprocessingReport(
                        document_id="garbled-document",
                        source_id="food_safety_korea_supplement_ingredients",
                        source_document_path=Path("data/knowledge/raw/public/p1-1.pdf"),
                        document_type=KnowledgeDocumentType.SUPPLEMENT_CODE,
                        selection_reason="전체 코퍼스 전처리",
                        automatic_status=KnowledgeAutomaticQualityStatus.BLOCKED,
                        manual_review_status=KnowledgeManualReviewStatus.APPROVED,
                        reason_codes=[
                            KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS,
                            KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
                        ],
                        page_count=1,
                        character_count=100,
                        chunk_count=1,
                        min_chunk_tokens=10,
                        average_chunk_tokens=10,
                        max_chunk_tokens=10,
                        semantic_section_ratio=0,
                        review_sample_path=Path("review/garbled-document.md"),
                    )
                ],
            )

    release = KnowledgeCorpusPreprocessingService(
        pilot_service=StubPilotService(),
        manifest_builder=StubManifestBuilder(),
    ).preprocess(
        documents_path=tmp_path / "documents.jsonl",
        sources_path=tmp_path / "sources.yaml",
        output_root=tmp_path,
        dataset_version="test-v1",
    )

    assert release.skipped_documents[0].reason == "AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT"
    assert (tmp_path / "reports" / "blocked-document-recovery.json").is_file()
    assert not (tmp_path / "review" / "garbled-document.md").exists()
