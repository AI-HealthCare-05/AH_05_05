from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_worker.schemas.knowledge import (
    KnowledgeEvidenceLevel,
    KnowledgeStudyPopulation,
)
from ai_worker.schemas.knowledge_manifest import (
    KnowledgeManualReviewStatus,
    KnowledgePilotEntry,
    KnowledgePilotManifest,
    KnowledgeProcessingStatus,
    KnowledgeSourcesManifest,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgePilotPreprocessingResult,
    KnowledgePilotPreprocessingService,
    SkippedKnowledgeDocument,
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


class KnowledgeCorpusManifestBuilder:
    def build(
        self,
        *,
        documents_path: Path,
        sources_path: Path,
        pilot_quality_report_path: Path,
        pilot_manifest_path: Path | None = None,
    ) -> KnowledgePilotManifest:
        sources = KnowledgeSourcesManifest.model_validate(
            yaml.safe_load(Path(sources_path).read_text(encoding="utf-8"))
        )
        source_by_id = {source.source_id: source for source in sources.sources}
        pilot_quality = KnowledgePilotPreprocessingResult.model_validate_json(
            Path(pilot_quality_report_path).read_text(encoding="utf-8")
        )
        approved_sources = set(pilot_quality.ready_for_bulk_source_ids)
        reviewed_by_document_id = self._load_reviewed_entries(
            pilot_manifest_path,
        )
        selected: list[KnowledgePilotEntry] = []
        seen_hashes: set[str] = set()

        for document in self._load_documents(documents_path):
            source = source_by_id.get(document.source_id)
            if source is None or not source.index_eligible:
                continue
            if document.source_id not in approved_sources:
                continue
            if document.processing_status != KnowledgeProcessingStatus.TEXT_EXTRACTABLE:
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
                    processing_status=document.processing_status,
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
    def _load_reviewed_entries(
        pilot_manifest_path: Path | None,
    ) -> dict[str, KnowledgePilotEntry]:
        if pilot_manifest_path is None:
            return {}
        manifest = KnowledgePilotManifest.model_validate_json(
            Path(pilot_manifest_path).read_text(encoding="utf-8"),
        )
        return {entry.document_id: entry for entry in manifest.pilots}

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
        pilot_quality_report_path: Path,
        pilot_manifest_path: Path | None = None,
        output_root: Path,
        dataset_version: str,
    ) -> KnowledgePilotPreprocessingResult:
        manifest = self._manifest_builder.build(
            documents_path=documents_path,
            sources_path=sources_path,
            pilot_quality_report_path=pilot_quality_report_path,
            pilot_manifest_path=pilot_manifest_path,
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
        )
        return self.finalize_release(
            result=result,
            output_root=output_root,
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

        pass_reports = [
            report
            for report in result.document_reports
            if report.automatic_status == KnowledgeAutomaticQualityStatus.PASS
        ]
        pass_ids = {report.document_id for report in pass_reports}
        non_pass_reports = [report for report in result.document_reports if report.document_id not in pass_ids]
        for report in non_pass_reports:
            for directory in ("chunks", "text"):
                (root / directory / f"{report.document_id}.jsonl").unlink(missing_ok=True)

        chunk_count = 0
        for report in pass_reports:
            path = root / "chunks" / f"{report.document_id}.jsonl"
            if not path.is_file():
                raise ValueError(f"자동 PASS 문서의 청크 파일이 없습니다: {report.document_id}")
            chunk_count += sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines())

        skipped = list(result.skipped_documents)
        skipped_ids = {item.document_id for item in skipped}
        skipped.extend(
            SkippedKnowledgeDocument(
                document_id=report.document_id,
                reason=f"AUTOMATIC_QUALITY_{report.automatic_status.value}",
            )
            for report in non_pass_reports
            if report.document_id not in skipped_ids
        )
        release = KnowledgePilotPreprocessingResult(
            dataset_version=result.dataset_version,
            processed_document_count=len(pass_reports),
            chunk_count=chunk_count,
            skipped_documents=skipped,
            document_reports=pass_reports,
            ready_for_bulk_source_ids=sorted({report.source_id for report in pass_reports}),
        )
        (report_root / "preprocessing-quality.json").write_text(
            release.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return release
