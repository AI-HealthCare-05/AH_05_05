import json
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_worker.schemas.knowledge import (
    KnowledgeEvidenceLevel,
    KnowledgeStudyPopulation,
)
from ai_worker.schemas.knowledge_manifest import (
    KnowledgeManualReviewStatus,
    KnowledgeOcrDocumentSelectionDecision,
    KnowledgeOcrDocumentSelectionManifest,
    KnowledgePilotEntry,
    KnowledgePilotManifest,
    KnowledgeProcessingStatus,
    KnowledgeSourcesManifest,
)
from ai_worker.services.knowledge_blocked_document_recovery_service import (
    KnowledgeBlockedDocumentRecoveryResult,
    KnowledgeBlockedDocumentRecoveryService,
)
from ai_worker.services.knowledge_ocr_artifact_quality_service import (
    KnowledgeOcrArtifactQualityService,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgeChunkReviewStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
    KnowledgePilotPreprocessingService,
    SkippedKnowledgeDocument,
)
from ai_worker.services.knowledge_recovery_reporting_service import (
    KnowledgeRecoveryReportingService,
)


class KnowledgeCorpusDocument(BaseModel):
    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    repo_path: Path
    processing_status: KnowledgeProcessingStatus
    sha256: str = Field(min_length=64, max_length=64)
    title: str | None = None
    source_url: str | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1900, le=2100)
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    evidence_level: KnowledgeEvidenceLevel = KnowledgeEvidenceLevel.UNKNOWN
    study_population: KnowledgeStudyPopulation = KnowledgeStudyPopulation.UNKNOWN
    index_eligible: bool = True
    index_exclusion_reason: str | None = None


class KnowledgeCorpusManifestBuilder:
    def __init__(
        self,
        *,
        ocr_artifact_quality_service: KnowledgeOcrArtifactQualityService | None = None,
    ) -> None:
        self._ocr_artifact_quality_service = ocr_artifact_quality_service or KnowledgeOcrArtifactQualityService()

    def build(
        self,
        *,
        documents_path: Path,
        sources_path: Path,
        pilot_quality_report_path: Path | None = None,
        pilot_quality_report_paths: list[Path] | None = None,
        pilot_manifest_path: Path | None = None,
        pilot_manifest_paths: list[Path] | None = None,
        ocr_artifact_root: Path | None = None,
        ocr_document_selection_path: Path | None = None,
    ) -> KnowledgePilotManifest:
        sources = KnowledgeSourcesManifest.model_validate(
            yaml.safe_load(Path(sources_path).read_text(encoding="utf-8"))
        )
        source_by_id = {source.source_id: source for source in sources.sources}
        quality_report_paths = self._normalized_paths(
            singular=pilot_quality_report_path,
            plural=pilot_quality_report_paths,
            label="대표 품질 보고서",
            required=False,
        )
        reviewed_by_document_id = self._load_reviewed_entries(
            pilot_manifest_path=pilot_manifest_path,
            pilot_manifest_paths=pilot_manifest_paths,
        )
        selected_ocr_document_ids = self._load_selected_ocr_document_ids(
            ocr_document_selection_path=ocr_document_selection_path,
        )
        approved_sources: set[str] = set()
        for quality_report_path in quality_report_paths:
            approved_sources.update(
                self._load_approved_source_ids(quality_report_path),
            )
        approved_sources.update(
            entry.source_id
            for entry in reviewed_by_document_id.values()
            if entry.manual_review_status == KnowledgeManualReviewStatus.APPROVED
        )
        selected: list[KnowledgePilotEntry] = []
        seen_hashes: set[str] = set()

        for document in self._load_documents(documents_path):
            if not document.index_eligible:
                continue
            source = source_by_id.get(document.source_id)
            if source is None or not source.index_eligible:
                continue
            if document.source_id not in approved_sources:
                continue
            is_artifact_backed_ocr = (
                document.processing_status == KnowledgeProcessingStatus.OCR_REQUIRED
                and document.document_id in selected_ocr_document_ids
                and self._has_eligible_ocr_artifact(
                    artifact_root=ocr_artifact_root,
                    document_id=document.document_id,
                )
            )
            if document.processing_status != KnowledgeProcessingStatus.TEXT_EXTRACTABLE and not is_artifact_backed_ocr:
                continue
            if document.repo_path.suffix.casefold() != ".pdf":
                continue
            if not document.repo_path.is_relative_to(source.raw_path):
                continue
            if document.sha256 in seen_hashes:
                continue
            seen_hashes.add(document.sha256)
            reviewed = reviewed_by_document_id.get(document.document_id)
            selected.append(
                KnowledgePilotEntry(
                    source_id=document.source_id,
                    document_id=document.document_id,
                    repo_path=document.repo_path,
                    processing_status=(
                        KnowledgeProcessingStatus.TEXT_EXTRACTABLE
                        if is_artifact_backed_ocr
                        else document.processing_status
                    ),
                    selection_reason=(
                        reviewed.selection_reason
                        if reviewed is not None
                        else "대표 문서 품질 승인을 상속한 전체 코퍼스 전처리"
                    ),
                    manual_review_status=(
                        reviewed.manual_review_status if reviewed is not None else KnowledgeManualReviewStatus.APPROVED
                    ),
                    title=document.title or (reviewed.title if reviewed else None),
                    source_url=(document.source_url or (reviewed.source_url if reviewed else None)),
                    doi=document.doi or (reviewed.doi if reviewed else None),
                    authors=(document.authors or (reviewed.authors if reviewed else [])),
                    publication_year=(document.publication_year or (reviewed.publication_year if reviewed else None)),
                    drug_names=(document.drug_names or (reviewed.drug_names if reviewed else [])),
                    ingredient_names=(document.ingredient_names or (reviewed.ingredient_names if reviewed else [])),
                    evidence_level=(
                        document.evidence_level
                        if document.evidence_level != KnowledgeEvidenceLevel.UNKNOWN
                        else (reviewed.evidence_level if reviewed is not None else KnowledgeEvidenceLevel.UNKNOWN)
                    ),
                    study_population=(
                        document.study_population
                        if document.study_population != KnowledgeStudyPopulation.UNKNOWN
                        else (reviewed.study_population if reviewed is not None else KnowledgeStudyPopulation.UNKNOWN)
                    ),
                    verified_text_replacements=(reviewed.verified_text_replacements if reviewed is not None else {}),
                    verified_section_headings=(reviewed.verified_section_headings if reviewed is not None else []),
                    approved_chunk_content_hashes=(
                        reviewed.approved_chunk_content_hashes if reviewed is not None else []
                    ),
                    approved_review_reason_codes=(
                        reviewed.approved_review_reason_codes if reviewed is not None else []
                    ),
                )
            )

        return KnowledgePilotManifest(
            policy=("품질 승인 출처의 텍스트 추출 가능 PDF를 중복 제거 후 전체 전처리한다."),
            pilots=selected,
        )

    @staticmethod
    def _load_selected_ocr_document_ids(
        *,
        ocr_document_selection_path: Path | None,
    ) -> set[str]:
        if ocr_document_selection_path is None:
            return set()
        manifest = KnowledgeOcrDocumentSelectionManifest.model_validate(
            yaml.safe_load(Path(ocr_document_selection_path).read_text(encoding="utf-8")),
        )
        return {
            selection.document_id
            for selection in manifest.selections
            if selection.decision == KnowledgeOcrDocumentSelectionDecision.INCLUDE
        }

    def _has_eligible_ocr_artifact(
        self,
        *,
        artifact_root: Path | None,
        document_id: str,
    ) -> bool:
        if artifact_root is None:
            return False
        artifact_path = Path(artifact_root) / f"{document_id}.json"
        return self._ocr_artifact_quality_service.is_eligible_artifact(artifact_path)

    @staticmethod
    def _load_approved_source_ids(quality_report_path: Path) -> list[str]:
        """Read the stable source approval contract from legacy quality reports.

        Historical quality reports can lack fields newly added to per-document
        reports. The manifest builder only needs the top-level approved source
        list, so it must not deserialize unrelated document details.
        """
        try:
            payload = json.loads(Path(quality_report_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"대표 품질 보고서 JSON이 올바르지 않습니다: {quality_report_path}",
            ) from error
        source_ids = payload.get("ready_for_bulk_source_ids")
        if not isinstance(source_ids, list) or not all(
            isinstance(source_id, str) and source_id.strip() for source_id in source_ids
        ):
            raise ValueError(
                f"대표 품질 보고서의 ready_for_bulk_source_ids가 올바르지 않습니다: {quality_report_path}",
            )
        return source_ids

    @staticmethod
    def _load_reviewed_entries(
        *,
        pilot_manifest_path: Path | None,
        pilot_manifest_paths: list[Path] | None,
    ) -> dict[str, KnowledgePilotEntry]:
        paths = KnowledgeCorpusManifestBuilder._normalized_paths(
            singular=pilot_manifest_path,
            plural=pilot_manifest_paths,
            label="대표 매니페스트",
            required=False,
        )
        reviewed: dict[str, KnowledgePilotEntry] = {}
        for path in paths:
            manifest = KnowledgePilotManifest.model_validate_json(
                Path(path).read_text(encoding="utf-8"),
            )
            for entry in manifest.pilots:
                existing = reviewed.get(entry.document_id)
                if existing is not None and existing != entry:
                    raise ValueError(
                        f"대표 매니페스트에 충돌하는 문서 검수 정의가 있습니다: {entry.document_id}",
                    )
                reviewed[entry.document_id] = entry
        return reviewed

    @staticmethod
    def _normalized_paths(
        *,
        singular: Path | None,
        plural: list[Path] | None,
        label: str,
        required: bool = True,
    ) -> list[Path]:
        paths = list(plural or [])
        if singular is not None:
            paths.append(singular)
        unique_paths = list(dict.fromkeys(Path(path) for path in paths))
        if required and not unique_paths:
            raise ValueError(f"{label}가 하나 이상 필요합니다.")
        return unique_paths

    @staticmethod
    def _load_documents(
        path: Path,
    ) -> list[KnowledgeCorpusDocument]:
        documents: list[KnowledgeCorpusDocument] = []
        for line_number, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                documents.append(KnowledgeCorpusDocument.model_validate_json(line))
            except ValueError as error:
                raise ValueError(f"전체 문서 매니페스트 {line_number}행이 올바르지 않습니다.") from error
        return documents


class KnowledgeCorpusPreprocessingService:
    def __init__(
        self,
        *,
        pilot_service: KnowledgePilotPreprocessingService,
        manifest_builder: KnowledgeCorpusManifestBuilder | None = None,
    ) -> None:
        self._pilot_service = pilot_service
        self._manifest_builder = manifest_builder or KnowledgeCorpusManifestBuilder()

    def preprocess(
        self,
        *,
        documents_path: Path,
        sources_path: Path,
        pilot_quality_report_path: Path | None = None,
        pilot_quality_report_paths: list[Path] | None = None,
        pilot_manifest_path: Path | None = None,
        pilot_manifest_paths: list[Path] | None = None,
        ocr_artifact_root: Path | None = None,
        ocr_document_selection_path: Path | None = None,
        output_root: Path,
        dataset_version: str,
        baseline_quality_report_path: Path | None = None,
        recovery_reporting_service: KnowledgeRecoveryReportingService | None = None,
        blocked_document_recovery_service: KnowledgeBlockedDocumentRecoveryService | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        document_start: int = 0,
        document_end: int | None = None,
    ) -> KnowledgePilotPreprocessingResult:
        manifest = self._manifest_builder.build(
            documents_path=documents_path,
            sources_path=sources_path,
            pilot_quality_report_path=pilot_quality_report_path,
            pilot_quality_report_paths=pilot_quality_report_paths,
            pilot_manifest_path=pilot_manifest_path,
            pilot_manifest_paths=pilot_manifest_paths,
            ocr_artifact_root=ocr_artifact_root,
            ocr_document_selection_path=ocr_document_selection_path,
        )
        manifest = self._slice_manifest(
            manifest=manifest,
            document_start=document_start,
            document_end=document_end,
        )
        report_root = Path(output_root) / "reports"
        report_root.mkdir(parents=True, exist_ok=True)
        manifest_path = report_root / "corpus-manifest.json"
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        result = self._pilot_service.preprocess(
            manifest_path=manifest_path,
            sources_path=sources_path,
            output_root=output_root,
            dataset_version=dataset_version,
            progress_callback=progress_callback,
        )
        blocked_recovery = (blocked_document_recovery_service or KnowledgeBlockedDocumentRecoveryService()).write(
            result=result,
            output_root=output_root,
        )
        result = self._apply_automatic_exclusion_reasons(
            result=result,
            recovery=blocked_recovery,
        )
        release = self.finalize_release(
            result=result,
            output_root=output_root,
        )
        if baseline_quality_report_path is not None:
            (recovery_reporting_service or KnowledgeRecoveryReportingService()).write(
                documents_path=documents_path,
                baseline_quality_report_path=baseline_quality_report_path,
                result=release,
                output_root=output_root,
            )
        return release

    @staticmethod
    def _slice_manifest(
        *,
        manifest: KnowledgePilotManifest,
        document_start: int,
        document_end: int | None,
    ) -> KnowledgePilotManifest:
        if document_start < 0:
            raise ValueError("document_start는 0 이상이어야 합니다.")
        if document_end is not None and document_end <= document_start:
            raise ValueError("document_end는 document_start보다 커야 합니다.")
        selected = manifest.pilots[document_start:document_end]
        if not selected and (document_start != 0 or document_end is not None):
            raise ValueError("선택한 document 범위에 전처리할 승인 문서가 없습니다.")
        return manifest.model_copy(update={"pilots": selected})

    @staticmethod
    def _apply_automatic_exclusion_reasons(
        *,
        result: KnowledgePilotPreprocessingResult,
        recovery: KnowledgeBlockedDocumentRecoveryResult,
    ) -> KnowledgePilotPreprocessingResult:
        excluded_document_ids = recovery.automatically_excluded_document_ids
        if not excluded_document_ids:
            return result
        return result.model_copy(
            update={
                "skipped_documents": [
                    skipped.model_copy(
                        update={"reason": "AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT"},
                    )
                    if (skipped.document_id in excluded_document_ids and skipped.reason == "AUTOMATIC_QUALITY_BLOCKED")
                    else skipped
                    for skipped in result.skipped_documents
                ]
            }
        )

    @staticmethod
    def finalize_release(
        *,
        result: KnowledgePilotPreprocessingResult,
        output_root: Path,
    ) -> KnowledgePilotPreprocessingResult:
        root = Path(output_root)
        report_root = root / "reports"
        report_root.mkdir(parents=True, exist_ok=True)
        (report_root / "corpus-quality-audit.json").write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )

        chunks_root = root / "chunks"
        release_chunks_root = root / "release" / "chunks"
        chunks_root.mkdir(parents=True, exist_ok=True)
        released_reports: list[KnowledgeDocumentPreprocessingReport] = []
        released_ids: set[str] = set()
        chunk_count = 0

        for report in result.document_reports:
            target_path = chunks_root / f"{report.document_id}.jsonl"
            partial_path = release_chunks_root / f"{report.document_id}.jsonl"
            source_path = (
                partial_path
                if partial_path.is_file()
                else target_path
                if report.automatic_status == KnowledgeAutomaticQualityStatus.PASS and target_path.is_file()
                else None
            )
            if source_path is None:
                target_path.unlink(missing_ok=True)
                (root / "text" / f"{report.document_id}.jsonl").unlink(missing_ok=True)
                continue

            content = source_path.read_text(encoding="utf-8")
            released_chunk_count = sum(bool(line.strip()) for line in content.splitlines())
            if released_chunk_count == 0:
                target_path.unlink(missing_ok=True)
                (root / "text" / f"{report.document_id}.jsonl").unlink(missing_ok=True)
                continue
            if source_path != target_path:
                target_path.write_text(content, encoding="utf-8")

            released_ids.add(report.document_id)
            chunk_count += released_chunk_count
            released_reports.append(
                KnowledgeCorpusPreprocessingService._release_report(
                    report=report,
                    released_chunk_count=released_chunk_count,
                )
            )

        skipped = list(result.skipped_documents)
        skipped = [item for item in skipped if item.document_id not in released_ids]
        skipped_ids = {item.document_id for item in skipped}
        skipped.extend(
            SkippedKnowledgeDocument(
                document_id=report.document_id,
                reason=f"AUTOMATIC_QUALITY_{report.automatic_status.value}",
            )
            for report in result.document_reports
            if report.document_id not in released_ids
            if report.document_id not in skipped_ids
        )
        release = KnowledgePilotPreprocessingResult(
            dataset_version=result.dataset_version,
            processed_document_count=len(released_reports),
            chunk_count=chunk_count,
            skipped_documents=skipped,
            document_reports=released_reports,
            ready_for_bulk_source_ids=sorted(
                {report.source_id for report in released_reports},
            ),
        )
        (report_root / "preprocessing-quality.json").write_text(
            release.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return release

    @staticmethod
    def _release_report(
        *,
        report: KnowledgeDocumentPreprocessingReport,
        released_chunk_count: int,
    ) -> KnowledgeDocumentPreprocessingReport:
        approved_reviews = [
            review for review in report.chunk_reviews if review.status == KnowledgeChunkReviewStatus.APPROVED
        ]
        return report.model_copy(
            update={
                "chunk_count": released_chunk_count,
                "approved_chunk_count": released_chunk_count,
                "pending_chunk_count": 0,
                "repair_required_chunk_count": 0,
                "excluded_non_content_chunk_count": 0,
                "released_chunk_count": released_chunk_count,
                "partial_release": (report.partial_release or released_chunk_count < report.chunk_count),
                "release_ready": True,
                "chunk_reviews": approved_reviews,
            }
        )
