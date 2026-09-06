import re
from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

import yaml
from pydantic import BaseModel, Field

from ai_worker.rag.metadata.knowledge_entity_extractor import (
    KnowledgeEntityExtractor,
)
from ai_worker.rag.normalizers.knowledge_normalizer import (
    KnowledgeNormalizer,
    TextQualityStatus,
)
from ai_worker.rag.parsers.supplement_code_parser import (
    iter_supplement_reference_keys,
)
from ai_worker.rag.splitters.knowledge_splitter import KnowledgeSplitter
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgeSectionType,
)
from ai_worker.schemas.knowledge_manifest import (
    KnowledgeManualReviewStatus,
    KnowledgePilotEntry,
    KnowledgePilotManifest,
    KnowledgeProcessingStatus,
    KnowledgeSourceConfig,
    KnowledgeSourcesManifest,
)


class KnowledgeDocumentLoader(Protocol):
    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]: ...


class SkippedKnowledgeDocument(BaseModel):
    document_id: str
    reason: str


class KnowledgeAutomaticQualityStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


class KnowledgeChunkReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REPAIR_REQUIRED = "REPAIR_REQUIRED"
    EXCLUDED_NON_CONTENT = "EXCLUDED_NON_CONTENT"


class KnowledgeAutomaticQualityReasonCode(StrEnum):
    NO_SEMANTIC_SECTIONS = "NO_SEMANTIC_SECTIONS"
    OVERSIZED_CHUNK = "OVERSIZED_CHUNK"
    MISSING_SUPPLEMENT_CONTEXT = "MISSING_SUPPLEMENT_CONTEXT"
    SUSPICIOUS_SUPPLEMENT_UNIT = "SUSPICIOUS_SUPPLEMENT_UNIT"
    UNRESOLVED_HIERARCHY_REFERENCE = "UNRESOLVED_HIERARCHY_REFERENCE"
    SUPPLEMENT_SECTION_CONTAMINATION = "SUPPLEMENT_SECTION_CONTAMINATION"
    MALFORMED_SUPPLEMENT_TEXT = "MALFORMED_SUPPLEMENT_TEXT"
    MISSING_REQUIRED_SUPPLEMENT_SECTION = "MISSING_REQUIRED_SUPPLEMENT_SECTION"
    COMPLEX_TABLE_REQUIRES_REVIEW = "COMPLEX_TABLE_REQUIRES_REVIEW"
    MISSING_SEARCH_ENTITIES = "MISSING_SEARCH_ENTITIES"
    UNKNOWN_EVIDENCE_LEVEL = "UNKNOWN_EVIDENCE_LEVEL"
    BOILERPLATE_CONTAMINATION = "BOILERPLATE_CONTAMINATION"
    UNRESOLVED_LINE_WRAP = "UNRESOLVED_LINE_WRAP"
    SHORT_FRAGMENT_RATIO = "SHORT_FRAGMENT_RATIO"
    MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW = "MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW"
    ROTATED_TEXT_REQUIRES_REVIEW = "ROTATED_TEXT_REQUIRES_REVIEW"
    MISSING_SOURCE_METADATA = "MISSING_SOURCE_METADATA"
    TABLE_STRUCTURE_UNSAFE = "TABLE_STRUCTURE_UNSAFE"
    READING_ORDER_UNSAFE = "READING_ORDER_UNSAFE"


_BLOCKING_QUALITY_REASONS = {
    KnowledgeAutomaticQualityReasonCode.OVERSIZED_CHUNK,
    KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
    KnowledgeAutomaticQualityReasonCode.SUSPICIOUS_SUPPLEMENT_UNIT,
    KnowledgeAutomaticQualityReasonCode.UNRESOLVED_HIERARCHY_REFERENCE,
    KnowledgeAutomaticQualityReasonCode.SUPPLEMENT_SECTION_CONTAMINATION,
    KnowledgeAutomaticQualityReasonCode.MALFORMED_SUPPLEMENT_TEXT,
    KnowledgeAutomaticQualityReasonCode.MISSING_REQUIRED_SUPPLEMENT_SECTION,
    KnowledgeAutomaticQualityReasonCode.TABLE_STRUCTURE_UNSAFE,
    KnowledgeAutomaticQualityReasonCode.READING_ORDER_UNSAFE,
}

_REQUIRED_SUPPLEMENT_SECTIONS = frozenset(
    {
        KnowledgeSectionType.INGREDIENT,
        KnowledgeSectionType.FUNCTION,
        KnowledgeSectionType.DAILY_INTAKE,
    }
)
_MALFORMED_SUPPLEMENT_TEXT_PATTERNS = (
    re.compile(r"\)\("),
    re.compile(r"\(\s*\)"),
    re.compile(r"[ \t]+[,;:]"),
    re.compile(r"비타민\s+(?:를|을|와|과)\b[^\n]{0,80}\b[A-Z]\d*\b"),
    re.compile(r"\b(?P<symbol>[A-Z]\d*)\s+(?P=symbol)\b"),
    re.compile(r"비타민\s+(?:를|을|와|과)\b"),
    re.compile(r"다만[A-Z]\d*\b"),
    re.compile(r"\)\s+[A-Z]\d*\s+의\s+형태"),
)

_RESOLVED_SUPPLEMENT_REFERENCE = re.compile(
    r"-\s*(?P<top>\d+)\)\s*>\s*"
    r"\((?P<sub>\d+)\)\s*>\s*"
    r"\((?P<label>[가나다라마바사아자차카타파하])\):"
)
_SUPPLEMENT_SECTION_FORBIDDEN_HEADINGS = {
    KnowledgeSectionType.INGREDIENT: (
        r"규격",
        r"제품의\s*요건",
        r"기능성\s*내용",
        r"일일섭취량",
        r"섭취\s*시\s*주의사항",
        r"시험\s*법",
    ),
    KnowledgeSectionType.STANDARD: (
        r"제품의\s*요건",
        r"기능성\s*내용",
        r"일일섭취량",
        r"섭취\s*시\s*주의사항",
        r"시험\s*법",
    ),
    KnowledgeSectionType.FUNCTION: (
        r"일일섭취량",
        r"섭취\s*시\s*주의사항",
        r"시험\s*법",
    ),
    KnowledgeSectionType.DAILY_INTAKE: (
        r"섭취\s*시\s*주의사항",
        r"시험\s*법",
    ),
    KnowledgeSectionType.CAUTION: (r"시험\s*법",),
}

_COMPLEX_TABLE_PATTERN = re.compile(r"(?im)^\s*table\s+(?:\d+|[IVXLCDM]+)[.:\s]")
_BOILERPLATE_PATTERN = re.compile(
    r"(?i)(?:author contributions:|conflicts of interest:|"
    r"manufactured and distributed by:|©\s*20\d{2}|"
    r"https?://doi\.org/)"
)
_UNRESOLVED_LINE_WRAP_PATTERN = re.compile(r"\b[A-Za-z]{2,}-\n[A-Za-z]{2,}\b")
_METADATA_QUALITY_DOCUMENT_TYPES = {
    KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
    KnowledgeDocumentType.RESEARCH_ARTICLE,
}


class KnowledgeChunkReviewLocation(BaseModel):
    chunk_index: int = Field(ge=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)


class KnowledgeChunkReviewRecord(KnowledgeChunkReviewLocation):
    chunk_id: str = Field(min_length=64, max_length=64)
    status: KnowledgeChunkReviewStatus
    reason_codes: list[str] = Field(default_factory=list)


class QuarantinedKnowledgeChunk(BaseModel):
    review: KnowledgeChunkReviewRecord
    chunk: KnowledgeChunk


class KnowledgeDocumentPreprocessingReport(BaseModel):
    document_id: str
    source_id: str
    source_document_path: Path
    document_type: KnowledgeDocumentType
    selection_reason: str
    automatic_status: KnowledgeAutomaticQualityStatus
    manual_review_status: KnowledgeManualReviewStatus
    reason_codes: list[KnowledgeAutomaticQualityReasonCode] = Field(default_factory=list)
    page_count: int = Field(ge=1)
    character_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    min_chunk_tokens: int = Field(ge=1)
    average_chunk_tokens: float = Field(ge=0)
    max_chunk_tokens: int = Field(ge=1)
    semantic_section_ratio: float = Field(ge=0, le=1)
    search_entity_coverage: float = Field(default=0, ge=0, le=1)
    known_evidence_ratio: float = Field(default=0, ge=0, le=1)
    source_metadata_complete: bool = False
    complex_table_chunk_count: int = Field(default=0, ge=0)
    complex_table_locations: list[KnowledgeChunkReviewLocation] = Field(
        default_factory=list,
    )
    layout_warning_count: int = Field(default=0, ge=0)
    layout_warning_pages: list[int] = Field(default_factory=list)
    rotated_text_warning_count: int = Field(default=0, ge=0)
    rotated_text_warning_pages: list[int] = Field(default_factory=list)
    chunk_reviews: list[KnowledgeChunkReviewRecord] = Field(
        default_factory=list,
    )
    approved_chunk_count: int = Field(default=0, ge=0)
    pending_chunk_count: int = Field(default=0, ge=0)
    repair_required_chunk_count: int = Field(default=0, ge=0)
    excluded_non_content_chunk_count: int = Field(default=0, ge=0)
    release_ready: bool = False
    review_sample_path: Path


class KnowledgePilotPreprocessingResult(BaseModel):
    dataset_version: str
    processed_document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    skipped_documents: list[SkippedKnowledgeDocument] = Field(default_factory=list)
    document_reports: list[KnowledgeDocumentPreprocessingReport] = Field(default_factory=list)
    quality_report_path: Path = Path("reports/preprocessing-quality.json")
    ready_for_bulk_source_ids: list[str] = Field(default_factory=list)


class KnowledgePilotPreprocessingService:
    def __init__(
        self,
        *,
        repo_root: Path,
        loader: KnowledgeDocumentLoader,
        normalizer: KnowledgeNormalizer,
        splitter: KnowledgeSplitter,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._loader = loader
        self._normalizer = normalizer
        self._splitter = splitter

    def preprocess(
        self,
        *,
        manifest_path: Path,
        sources_path: Path,
        output_root: Path,
        dataset_version: str,
    ) -> KnowledgePilotPreprocessingResult:
        normalized_version = dataset_version.strip()
        if not normalized_version:
            raise ValueError("dataset_version은 비어 있을 수 없습니다.")

        pilot_manifest = KnowledgePilotManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
        source_manifest = KnowledgeSourcesManifest.model_validate(
            yaml.safe_load(Path(sources_path).read_text(encoding="utf-8"))
        )
        source_by_id = {source.source_id: source for source in source_manifest.sources}
        text_output = Path(output_root) / "text"
        chunk_output = Path(output_root) / "chunks"
        report_output = Path(output_root) / "reports"
        review_output = Path(output_root) / "review"
        quarantine_text_output = Path(output_root) / "quarantine" / "text"
        quarantine_chunk_output = Path(output_root) / "quarantine" / "chunks"
        release_text_output = Path(output_root) / "release" / "text"
        release_chunk_output = Path(output_root) / "release" / "chunks"
        text_output.mkdir(parents=True, exist_ok=True)
        chunk_output.mkdir(parents=True, exist_ok=True)
        report_output.mkdir(parents=True, exist_ok=True)
        review_output.mkdir(parents=True, exist_ok=True)
        quarantine_text_output.mkdir(parents=True, exist_ok=True)
        quarantine_chunk_output.mkdir(parents=True, exist_ok=True)
        release_text_output.mkdir(parents=True, exist_ok=True)
        release_chunk_output.mkdir(parents=True, exist_ok=True)
        quality_report_path = report_output / "preprocessing-quality.json"
        quality_report_path.unlink(missing_ok=True)

        active_document_ids = {pilot.document_id for pilot in pilot_manifest.pilots}
        self._remove_orphaned_outputs(
            active_document_ids=active_document_ids,
            text_output=text_output,
            chunk_output=chunk_output,
            review_output=review_output,
            quarantine_text_output=quarantine_text_output,
            quarantine_chunk_output=quarantine_chunk_output,
            release_text_output=release_text_output,
            release_chunk_output=release_chunk_output,
        )

        processed_count = 0
        chunk_count = 0
        skipped: list[SkippedKnowledgeDocument] = []
        document_reports: list[KnowledgeDocumentPreprocessingReport] = []
        failed_representative_source_ids: set[str] = set()

        for pilot in pilot_manifest.pilots:
            self._remove_previous_outputs(
                document_id=pilot.document_id,
                text_output=text_output,
                chunk_output=chunk_output,
                review_output=review_output,
                quarantine_text_output=quarantine_text_output,
                quarantine_chunk_output=quarantine_chunk_output,
                release_text_output=release_text_output,
                release_chunk_output=release_chunk_output,
            )

        for pilot in pilot_manifest.pilots:
            skip_reason = self._skip_reason(pilot.processing_status)
            if skip_reason:
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason=skip_reason,
                    )
                )
                continue

            source = source_by_id.get(pilot.source_id)
            if source is None:
                raise ValueError(f"출처 설정을 찾을 수 없습니다: {pilot.source_id}")
            if not source.index_eligible:
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason="SOURCE_NOT_INDEX_ELIGIBLE",
                    )
                )
                continue
            self._validate_source_path(
                pilot_path=pilot.repo_path,
                source_path=source.raw_path,
            )

            metadata = self._build_metadata(
                source=source,
                pilot=pilot,
                dataset_version=normalized_version,
            )
            pages = self._loader.load(
                self._repo_root / pilot.repo_path,
                metadata,
            )
            normalized_pages = self._normalizer.normalize_pages(
                pages,
                verified_text_replacements=pilot.verified_text_replacements,
            )
            quality = self._normalizer.assess_pages_quality(normalized_pages)
            has_blocking_layout_warning = any(
                warning
                in {
                    KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE,
                    KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
                }
                for page in normalized_pages
                for warning in page.extraction_warnings
            )
            if quality.status != TextQualityStatus.PASS and not has_blocking_layout_warning:
                failed_representative_source_ids.add(pilot.source_id)
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason=f"TEXT_QUALITY_{quality.status.value}",
                    )
                )
                continue

            chunks = self._splitter.split(
                normalized_pages,
                verified_section_headings=pilot.verified_section_headings,
            )
            if not chunks:
                failed_representative_source_ids.add(pilot.source_id)
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason="NO_CHUNKS",
                    )
                )
                continue

            review_path = review_output / f"{pilot.document_id}.md"
            document_report = self._build_document_report(
                pilot=pilot,
                document_type=metadata.document_type,
                normalized_pages=normalized_pages,
                chunks=chunks,
                review_sample_path=review_path.relative_to(output_root),
            )
            self._write_review_sample(
                path=review_path,
                report=document_report,
                chunks=chunks,
            )
            document_reports.append(document_report)
            self._write_candidate_and_release_outputs(
                document_id=pilot.document_id,
                normalized_pages=normalized_pages,
                chunks=chunks,
                report=document_report,
                quarantine_text_output=quarantine_text_output,
                quarantine_chunk_output=quarantine_chunk_output,
                release_text_output=release_text_output,
                release_chunk_output=release_chunk_output,
            )
            if document_report.automatic_status == KnowledgeAutomaticQualityStatus.BLOCKED:
                failed_representative_source_ids.add(pilot.source_id)
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason="AUTOMATIC_QUALITY_BLOCKED",
                    )
                )
                continue

            self._write_jsonl(
                text_output / f"{pilot.document_id}.jsonl",
                (page.model_dump_json() for page in normalized_pages),
            )
            self._write_jsonl(
                chunk_output / f"{pilot.document_id}.jsonl",
                (chunk.model_dump_json() for chunk in chunks),
            )
            processed_count += 1
            chunk_count += len(chunks)

        ready_for_bulk_source_ids = self._ready_for_bulk_source_ids(
            document_reports,
            failed_representative_source_ids=failed_representative_source_ids,
        )
        result = KnowledgePilotPreprocessingResult(
            dataset_version=normalized_version,
            processed_document_count=processed_count,
            chunk_count=chunk_count,
            skipped_documents=skipped,
            document_reports=document_reports,
            ready_for_bulk_source_ids=ready_for_bulk_source_ids,
        )
        self._write_text_atomic(
            quality_report_path,
            result.model_dump_json(indent=2),
        )
        return result

    @classmethod
    def _write_candidate_and_release_outputs(
        cls,
        *,
        document_id: str,
        normalized_pages: list[KnowledgePage],
        chunks: list[KnowledgeChunk],
        report: KnowledgeDocumentPreprocessingReport,
        quarantine_text_output: Path,
        quarantine_chunk_output: Path,
        release_text_output: Path,
        release_chunk_output: Path,
    ) -> None:
        cls._write_jsonl(
            quarantine_text_output / f"{document_id}.jsonl",
            (page.model_dump_json() for page in normalized_pages),
        )
        cls._write_jsonl(
            quarantine_chunk_output / f"{document_id}.jsonl",
            (
                QuarantinedKnowledgeChunk(
                    review=review,
                    chunk=chunk,
                ).model_dump_json()
                for review, chunk in zip(
                    report.chunk_reviews,
                    chunks,
                    strict=True,
                )
            ),
        )
        if not report.release_ready:
            return
        cls._write_jsonl(
            release_text_output / f"{document_id}.jsonl",
            (page.model_dump_json() for page in normalized_pages),
        )
        cls._write_jsonl(
            release_chunk_output / f"{document_id}.jsonl",
            (chunk.model_dump_json() for chunk in chunks),
        )

    def _build_document_report(
        self,
        *,
        pilot: KnowledgePilotEntry,
        document_type: KnowledgeDocumentType,
        normalized_pages: list[KnowledgePage],
        chunks: list[KnowledgeChunk],
        review_sample_path: Path,
    ) -> KnowledgeDocumentPreprocessingReport:
        policy = self._splitter.policy_for(document_type)
        token_counts = [chunk.token_count for chunk in chunks]
        semantic_chunk_count = sum(chunk.metadata.section_type != KnowledgeSectionType.OTHER for chunk in chunks)
        reason_codes: list[KnowledgeAutomaticQualityReasonCode] = []
        if semantic_chunk_count == 0:
            reason_codes.append(KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS)
        if max(token_counts) > policy.hard_max_tokens:
            reason_codes.append(KnowledgeAutomaticQualityReasonCode.OVERSIZED_CHUNK)
        if document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            reason_codes.extend(self._supplement_quality_reason_codes(chunks))
        if document_type in _METADATA_QUALITY_DOCUMENT_TYPES:
            reason_codes.extend(
                self._general_quality_reason_codes(
                    document_type=document_type,
                    pages=normalized_pages,
                    chunks=chunks,
                    target_min_tokens=policy.target_min_tokens,
                )
            )

        reason_codes = list(dict.fromkeys(reason_codes))
        search_entity_count = sum(
            bool(chunk.metadata.drug_names or chunk.metadata.ingredient_names) for chunk in chunks
        )
        known_evidence_count = sum(chunk.metadata.evidence_level.value != "UNKNOWN" for chunk in chunks)
        layout_warning_count = sum(
            KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT in page.extraction_warnings for page in normalized_pages
        )
        rotated_text_warning_count = sum(
            KnowledgeExtractionWarning.ROTATED_TEXT in page.extraction_warnings for page in normalized_pages
        )
        first_metadata = chunks[0].metadata
        complex_table_locations = [
            KnowledgeChunkReviewLocation(
                chunk_index=chunk.metadata.chunk_index,
                page_start=chunk.metadata.page_start,
                page_end=chunk.metadata.page_end,
            )
            for chunk in chunks
            if chunk.metadata.content_kind == KnowledgeContentKind.TABLE or _COMPLEX_TABLE_PATTERN.search(chunk.content)
        ]
        if _BLOCKING_QUALITY_REASONS.intersection(reason_codes):
            automatic_status = KnowledgeAutomaticQualityStatus.BLOCKED
        elif reason_codes:
            automatic_status = KnowledgeAutomaticQualityStatus.REVIEW
        else:
            automatic_status = KnowledgeAutomaticQualityStatus.PASS

        chunk_reviews = self._build_chunk_reviews(
            pilot=pilot,
            pages=normalized_pages,
            chunks=chunks,
            automatic_status=automatic_status,
        )
        status_counts = Counter(review.status for review in chunk_reviews)
        release_ready = (
            automatic_status == KnowledgeAutomaticQualityStatus.PASS
            and pilot.manual_review_status == KnowledgeManualReviewStatus.APPROVED
            and all(
                review.status
                in {
                    KnowledgeChunkReviewStatus.APPROVED,
                    KnowledgeChunkReviewStatus.EXCLUDED_NON_CONTENT,
                }
                for review in chunk_reviews
            )
        )

        return KnowledgeDocumentPreprocessingReport(
            document_id=pilot.document_id,
            source_id=pilot.source_id,
            source_document_path=pilot.repo_path,
            document_type=document_type,
            selection_reason=pilot.selection_reason,
            automatic_status=automatic_status,
            manual_review_status=pilot.manual_review_status,
            reason_codes=reason_codes,
            page_count=len(normalized_pages),
            character_count=sum(len(page.content) for page in normalized_pages),
            chunk_count=len(chunks),
            min_chunk_tokens=min(token_counts),
            average_chunk_tokens=round(
                sum(token_counts) / len(token_counts),
                1,
            ),
            max_chunk_tokens=max(token_counts),
            semantic_section_ratio=round(
                semantic_chunk_count / len(chunks),
                4,
            ),
            search_entity_coverage=round(
                search_entity_count / len(chunks),
                4,
            ),
            known_evidence_ratio=round(
                known_evidence_count / len(chunks),
                4,
            ),
            source_metadata_complete=bool(first_metadata.title and first_metadata.source_url),
            complex_table_chunk_count=len(complex_table_locations),
            complex_table_locations=complex_table_locations,
            layout_warning_count=layout_warning_count,
            layout_warning_pages=[
                page.page_number
                for page in normalized_pages
                if KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT in page.extraction_warnings
            ],
            rotated_text_warning_count=rotated_text_warning_count,
            rotated_text_warning_pages=[
                page.page_number
                for page in normalized_pages
                if KnowledgeExtractionWarning.ROTATED_TEXT in page.extraction_warnings
            ],
            chunk_reviews=chunk_reviews,
            approved_chunk_count=status_counts[KnowledgeChunkReviewStatus.APPROVED],
            pending_chunk_count=status_counts[KnowledgeChunkReviewStatus.PENDING],
            repair_required_chunk_count=status_counts[KnowledgeChunkReviewStatus.REPAIR_REQUIRED],
            excluded_non_content_chunk_count=status_counts[KnowledgeChunkReviewStatus.EXCLUDED_NON_CONTENT],
            release_ready=release_ready,
            review_sample_path=review_sample_path,
        )

    @staticmethod
    def _build_chunk_reviews(
        *,
        pilot: KnowledgePilotEntry,
        pages: list[KnowledgePage],
        chunks: list[KnowledgeChunk],
        automatic_status: KnowledgeAutomaticQualityStatus,
    ) -> list[KnowledgeChunkReviewRecord]:
        blocking_warnings_by_page = {
            page.page_number: [
                warning.value
                for warning in page.extraction_warnings
                if warning
                in {
                    KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE,
                    KnowledgeExtractionWarning.READING_ORDER_UNSAFE,
                }
            ]
            for page in pages
        }
        reviews: list[KnowledgeChunkReviewRecord] = []
        for chunk in chunks:
            reasons = list(
                dict.fromkeys(
                    reason
                    for page_number in range(
                        chunk.metadata.page_start,
                        chunk.metadata.page_end + 1,
                    )
                    for reason in blocking_warnings_by_page.get(
                        page_number,
                        [],
                    )
                )
            )
            if chunk.metadata.section_type == KnowledgeSectionType.REFERENCES:
                status = KnowledgeChunkReviewStatus.EXCLUDED_NON_CONTENT
                reasons = ["REFERENCE_SECTION"]
            elif chunk.metadata.content_hash in pilot.approved_chunk_content_hashes:
                status = KnowledgeChunkReviewStatus.APPROVED
            elif reasons:
                status = KnowledgeChunkReviewStatus.REPAIR_REQUIRED
            elif (
                automatic_status == KnowledgeAutomaticQualityStatus.PASS
                and pilot.manual_review_status == KnowledgeManualReviewStatus.APPROVED
            ):
                status = KnowledgeChunkReviewStatus.APPROVED
            else:
                status = KnowledgeChunkReviewStatus.PENDING
            reviews.append(
                KnowledgeChunkReviewRecord(
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.metadata.chunk_index,
                    page_start=chunk.metadata.page_start,
                    page_end=chunk.metadata.page_end,
                    status=status,
                    reason_codes=reasons,
                )
            )
        return reviews

    @staticmethod
    def _general_quality_reason_codes(
        *,
        document_type: KnowledgeDocumentType,
        pages: list[KnowledgePage],
        chunks: list[KnowledgeChunk],
        target_min_tokens: int,
    ) -> list[KnowledgeAutomaticQualityReasonCode]:
        reasons: list[KnowledgeAutomaticQualityReasonCode] = []
        joined_content = "\n".join(chunk.content for chunk in chunks)

        if _COMPLEX_TABLE_PATTERN.search(joined_content):
            reasons.append(KnowledgeAutomaticQualityReasonCode.COMPLEX_TABLE_REQUIRES_REVIEW)

        entity_count = sum(bool(chunk.metadata.drug_names or chunk.metadata.ingredient_names) for chunk in chunks)
        if entity_count / len(chunks) < 0.5:
            reasons.append(KnowledgeAutomaticQualityReasonCode.MISSING_SEARCH_ENTITIES)

        reasons.extend(KnowledgePilotPreprocessingService._extraction_warning_reason_codes(pages))

        if not chunks[0].metadata.source_url:
            reasons.append(KnowledgeAutomaticQualityReasonCode.MISSING_SOURCE_METADATA)

        if document_type == KnowledgeDocumentType.RESEARCH_ARTICLE:
            unknown_evidence_count = sum(chunk.metadata.evidence_level.value == "UNKNOWN" for chunk in chunks)
            if unknown_evidence_count / len(chunks) >= 0.5:
                reasons.append(KnowledgeAutomaticQualityReasonCode.UNKNOWN_EVIDENCE_LEVEL)

        if _BOILERPLATE_PATTERN.search(joined_content):
            reasons.append(KnowledgeAutomaticQualityReasonCode.BOILERPLATE_CONTAMINATION)
        if any(_UNRESOLVED_LINE_WRAP_PATTERN.search(chunk.content) for chunk in chunks):
            reasons.append(KnowledgeAutomaticQualityReasonCode.UNRESOLVED_LINE_WRAP)

        short_threshold = max(20, round(target_min_tokens * 0.25))
        short_count = sum(chunk.token_count < short_threshold for chunk in chunks)
        if len(chunks) >= 4 and short_count / len(chunks) >= 0.2:
            reasons.append(KnowledgeAutomaticQualityReasonCode.SHORT_FRAGMENT_RATIO)

        return reasons

    @staticmethod
    def _extraction_warning_reason_codes(
        pages: list[KnowledgePage],
    ) -> list[KnowledgeAutomaticQualityReasonCode]:
        warnings = {warning for page in pages for warning in page.extraction_warnings}
        reasons: list[KnowledgeAutomaticQualityReasonCode] = []
        if KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT in warnings:
            reasons.append(KnowledgeAutomaticQualityReasonCode.MULTI_COLUMN_LAYOUT_REQUIRES_REVIEW)
        if KnowledgeExtractionWarning.ROTATED_TEXT in warnings:
            reasons.append(KnowledgeAutomaticQualityReasonCode.ROTATED_TEXT_REQUIRES_REVIEW)
        if KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE in warnings:
            reasons.append(KnowledgeAutomaticQualityReasonCode.TABLE_STRUCTURE_UNSAFE)
        if KnowledgeExtractionWarning.READING_ORDER_UNSAFE in warnings:
            reasons.append(KnowledgeAutomaticQualityReasonCode.READING_ORDER_UNSAFE)
        return reasons

    @staticmethod
    def _ready_for_bulk_source_ids(
        reports: list[KnowledgeDocumentPreprocessingReport],
        *,
        failed_representative_source_ids: set[str],
    ) -> list[str]:
        reports_by_source: dict[
            str,
            list[KnowledgeDocumentPreprocessingReport],
        ] = {}
        for report in reports:
            reports_by_source.setdefault(report.source_id, []).append(report)

        return sorted(
            source_id
            for source_id, source_reports in reports_by_source.items()
            if source_id not in failed_representative_source_ids
            and all(
                report.automatic_status == KnowledgeAutomaticQualityStatus.PASS
                and report.manual_review_status == KnowledgeManualReviewStatus.APPROVED
                for report in source_reports
            )
        )

    @staticmethod
    def _write_review_sample(
        *,
        path: Path,
        report: KnowledgeDocumentPreprocessingReport,
        chunks: list[KnowledgeChunk],
    ) -> None:
        sample_indices = KnowledgePilotPreprocessingService._sample_indices(
            chunks,
            document_type=report.document_type,
        )
        sample_indices = sorted(
            set(sample_indices).union(
                review.chunk_index
                for review in report.chunk_reviews
                if review.status == KnowledgeChunkReviewStatus.REPAIR_REQUIRED
            )
        )
        lines = [
            f"# 전처리 표본 검수: {report.document_id}",
            "",
            f"- 원본 PDF: `{report.source_document_path}`",
            f"- 출처 유형: `{report.document_type.value}`",
            f"- 대표 선정 이유: {report.selection_reason}",
            f"- 자동 품질 상태: `{report.automatic_status.value}`",
            f"- 수동 검수 상태: `{report.manual_review_status.value}`",
            (f"- 추출된 텍스트 페이지/청크: {report.page_count}/{report.chunk_count}"),
            f"- 표 포함 청크: {report.complex_table_chunk_count}",
            f"- 다단 레이아웃 경고 페이지: {report.layout_warning_count}",
            f"- 회전 텍스트 경고 페이지: {report.rotated_text_warning_count}",
            f"- 릴리스 가능: `{report.release_ready}`",
            (
                "- 청크 상태: "
                f"APPROVED {report.approved_chunk_count}, "
                f"PENDING {report.pending_chunk_count}, "
                f"REPAIR_REQUIRED {report.repair_required_chunk_count}, "
                "EXCLUDED_NON_CONTENT "
                f"{report.excluded_non_content_chunk_count}"
            ),
            (
                "- 자동 검사 사유: "
                + (", ".join(reason.value for reason in report.reason_codes) if report.reason_codes else "없음")
            ),
            "",
            "## 우선 대조 위치",
            "",
            *KnowledgePilotPreprocessingService._review_location_lines(report),
            "",
            "## 사람이 확인할 항목",
            "",
            "- [ ] 원본 읽기 순서와 추출 텍스트 순서가 같다.",
            "- [ ] 제목과 설명이 같은 의미 단위에 남아 있다.",
            "- [ ] 약명·성분명·함량·단위가 원문과 같다.",
            "- [ ] 서로 다른 약·성분·사례가 한 청크에 섞이지 않았다.",
            "- [ ] 페이지 범위와 출처 표시가 원문 위치와 맞는다.",
            "",
            "## 수동 판정",
            "",
            "- [ ] `APPROVED` - 원문과 일치하며 인덱싱 가능",
            "- [ ] `KEEP_PENDING` - 추가 대조가 필요",
            "- [ ] `REPROCESS_REQUIRED` - 전처리 규칙 수정 후 재처리 필요",
            "- 검수자:",
            "- 검수일:",
            "- 메모:",
            "",
            "## 결정론적 표본 청크",
        ]
        for chunk_index in sample_indices:
            chunk = chunks[chunk_index]
            metadata = chunk.metadata
            chunk_review = report.chunk_reviews[chunk_index]
            lines.extend(
                [
                    "",
                    (
                        f"### 청크 {metadata.chunk_index} · "
                        f"{metadata.section_type.value} · "
                        f"p.{metadata.page_start}-{metadata.page_end} · "
                        f"{chunk.token_count} tokens"
                    ),
                    (
                        f"- 상태: `{chunk_review.status.value}`"
                        + (" · 사유: " + ", ".join(chunk_review.reason_codes) if chunk_review.reason_codes else "")
                    ),
                    "",
                    chunk.content,
                ]
            )
        KnowledgePilotPreprocessingService._write_text_atomic(
            path,
            "\n".join(lines).rstrip() + "\n",
        )

    @staticmethod
    def _review_location_lines(
        report: KnowledgeDocumentPreprocessingReport,
    ) -> list[str]:
        lines = [
            (
                "- 복잡한 표: "
                + ", ".join(
                    (
                        f"청크 {location.chunk_index}, "
                        f"원본 p.{location.page_start}"
                        + (f"-{location.page_end}" if location.page_end != location.page_start else "")
                    )
                    for location in report.complex_table_locations
                )
                if report.complex_table_locations
                else "- 복잡한 표: 없음"
            ),
            KnowledgePilotPreprocessingService._review_pages_line(
                label="다단 레이아웃",
                pages=report.layout_warning_pages,
            ),
            KnowledgePilotPreprocessingService._review_pages_line(
                label="회전 텍스트",
                pages=report.rotated_text_warning_pages,
            ),
        ]
        return lines

    @staticmethod
    def _review_pages_line(*, label: str, pages: list[int]) -> str:
        if not pages:
            return f"- {label}: 없음"
        return f"- {label}: " + ", ".join(f"원본 p.{page}" for page in pages)

    @staticmethod
    def _supplement_quality_reason_codes(
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeAutomaticQualityReasonCode]:
        reasons: list[KnowledgeAutomaticQualityReasonCode] = []
        section_types = {chunk.metadata.section_type for chunk in chunks}
        if section_types.intersection(_REQUIRED_SUPPLEMENT_SECTIONS) and not _REQUIRED_SUPPLEMENT_SECTIONS.issubset(
            section_types
        ):
            reasons.append(KnowledgeAutomaticQualityReasonCode.MISSING_REQUIRED_SUPPLEMENT_SECTION)

        for chunk in chunks:
            content = chunk.content
            if not content.startswith("성분: ") or "\n분류: " not in content:
                reasons.append(KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT)

            if chunk.metadata.section_type == KnowledgeSectionType.DAILY_INTAKE and re.search(
                r"(?<![μu])g\s+RAE\b", content
            ):
                reasons.append(KnowledgeAutomaticQualityReasonCode.SUSPICIOUS_SUPPLEMENT_UNIT)

            if KnowledgePilotPreprocessingService._has_unresolved_reference(content):
                reasons.append(KnowledgeAutomaticQualityReasonCode.UNRESOLVED_HIERARCHY_REFERENCE)

            if any(pattern.search(content) for pattern in _MALFORMED_SUPPLEMENT_TEXT_PATTERNS):
                reasons.append(KnowledgeAutomaticQualityReasonCode.MALFORMED_SUPPLEMENT_TEXT)

            body = KnowledgePilotPreprocessingService._supplement_chunk_body(content)
            forbidden = _SUPPLEMENT_SECTION_FORBIDDEN_HEADINGS.get(
                chunk.metadata.section_type,
                (),
            )
            if any(
                re.search(
                    rf"(?m)^\s*(?:\(?\d+\)?[.)]?\s*)?"
                    rf"{pattern}(?=\s|:|\d|\(|$)",
                    body,
                    flags=re.IGNORECASE,
                )
                for pattern in forbidden
            ):
                reasons.append(KnowledgeAutomaticQualityReasonCode.SUPPLEMENT_SECTION_CONTAMINATION)

            if chunk.metadata.section_type == KnowledgeSectionType.TEST_METHOD:
                reasons.append(KnowledgeAutomaticQualityReasonCode.SUPPLEMENT_SECTION_CONTAMINATION)
        return reasons

    @staticmethod
    def _has_unresolved_reference(content: str) -> bool:
        expected = set(iter_supplement_reference_keys(content))
        if not expected:
            return False

        resolved = {
            (match.group("top"), match.group("sub"), match.group("label"))
            for match in _RESOLVED_SUPPLEMENT_REFERENCE.finditer(content)
        }
        return not expected.issubset(resolved)

    @staticmethod
    def _supplement_chunk_body(content: str) -> str:
        lines = content.splitlines()
        if len(lines) < 3:
            return content
        _, separator, first_body = lines[2].partition(":")
        body_lines = [first_body] if separator else []
        body_lines.extend(lines[3:])
        return "\n".join(body_lines)

    @staticmethod
    def _sample_indices(
        chunks: list[KnowledgeChunk],
        *,
        document_type: KnowledgeDocumentType,
    ) -> list[int]:
        shortest = min(
            range(len(chunks)),
            key=lambda index: chunks[index].token_count,
        )
        longest = max(
            range(len(chunks)),
            key=lambda index: chunks[index].token_count,
        )
        candidates = {
            0,
            len(chunks) // 2,
            len(chunks) - 1,
            shortest,
            longest,
        }
        candidates.update(index for index, chunk in enumerate(chunks) if _COMPLEX_TABLE_PATTERN.search(chunk.content))
        if document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            first_index_by_section: dict[KnowledgeSectionType, int] = {}
            for index, chunk in enumerate(chunks):
                first_index_by_section.setdefault(
                    chunk.metadata.section_type,
                    index,
                )
            candidates.update(first_index_by_section.values())
        return sorted(candidates)

    @staticmethod
    def _write_text_atomic(path: Path, content: str) -> None:
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(content, encoding="utf-8")
        temporary_path.replace(path)

    @staticmethod
    def _skip_reason(
        status: KnowledgeProcessingStatus,
    ) -> str | None:
        if status == KnowledgeProcessingStatus.STRUCTURED_SOURCE:
            return "STRUCTURED_SOURCE"
        if status == KnowledgeProcessingStatus.OCR_REQUIRED:
            return "OCR_REQUIRED"
        return None

    @staticmethod
    def _build_metadata(
        *,
        source: KnowledgeSourceConfig,
        pilot: KnowledgePilotEntry,
        dataset_version: str,
    ) -> KnowledgeMetadata:
        document_type = cast(KnowledgeDocumentType, source.document_type)
        title = pilot.title or KnowledgePilotPreprocessingService._title_from_path(pilot.repo_path)
        entities = KnowledgeEntityExtractor().extract_from_title(
            document_type=document_type,
            title=title,
        )

        return KnowledgeMetadata(
            source_id=source.source_id,
            document_id=pilot.document_id,
            title=title,
            provider=source.provider,
            access_scope=source.access_scope,
            document_type=document_type,
            dataset_version=dataset_version,
            source_url=pilot.source_url,
            doi=pilot.doi,
            authors=pilot.authors,
            publication_year=pilot.publication_year,
            file_name=pilot.repo_path.name,
            drug_names=pilot.drug_names or entities.drug_names,
            ingredient_names=(pilot.ingredient_names or entities.ingredient_names),
            interaction_type=entities.interaction_type,
            interaction_pair_keys=entities.interaction_pair_keys,
            evidence_level=pilot.evidence_level,
            study_population=pilot.study_population,
            index_eligible=source.index_eligible,
        )

    @staticmethod
    def _title_from_path(path: Path) -> str:
        title = Path(path).stem
        title = re.sub(r"^\d+(?:-\d+)?[_\s-]*", "", title)
        title = re.sub(r"[_\s]*20\d{6}$", "", title)
        title = re.sub(r"[_\s]+", " ", title).strip()
        if not title:
            raise ValueError(f"문서 제목을 파일명에서 만들 수 없습니다: {path}")
        return title

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[str]) -> None:
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        with temporary_path.open("w", encoding="utf-8") as output:
            for row in rows:
                output.write(row)
                output.write("\n")
        temporary_path.replace(path)

    def _validate_source_path(
        self,
        *,
        pilot_path: Path,
        source_path: Path,
    ) -> None:
        resolved_root = self._repo_root.resolve()
        resolved_pilot = (self._repo_root / pilot_path).resolve()
        resolved_source = (self._repo_root / source_path).resolve()
        if not resolved_source.is_relative_to(resolved_root):
            raise ValueError(f"출처 경로가 저장소 경로 밖에 있습니다: {source_path}")
        if not resolved_pilot.is_relative_to(resolved_root):
            raise ValueError(f"파일럿 문서가 저장소 경로 밖에 있습니다: {pilot_path}")
        if not resolved_pilot.is_relative_to(resolved_source):
            raise ValueError(f"파일럿 문서가 설정된 출처 경로 밖에 있습니다: {pilot_path} (출처 경로: {source_path})")

    @staticmethod
    def _remove_previous_outputs(
        *,
        document_id: str,
        text_output: Path,
        chunk_output: Path,
        review_output: Path,
        quarantine_text_output: Path,
        quarantine_chunk_output: Path,
        release_text_output: Path,
        release_chunk_output: Path,
    ) -> None:
        outputs = (
            (text_output, ".jsonl"),
            (chunk_output, ".jsonl"),
            (review_output, ".md"),
            (quarantine_text_output, ".jsonl"),
            (quarantine_chunk_output, ".jsonl"),
            (release_text_output, ".jsonl"),
            (release_chunk_output, ".jsonl"),
        )
        for directory, suffix in outputs:
            output_path = directory / f"{document_id}{suffix}"
            output_path.unlink(missing_ok=True)

    @staticmethod
    def _remove_orphaned_outputs(
        *,
        active_document_ids: set[str],
        text_output: Path,
        chunk_output: Path,
        review_output: Path,
        quarantine_text_output: Path,
        quarantine_chunk_output: Path,
        release_text_output: Path,
        release_chunk_output: Path,
    ) -> None:
        outputs = (
            (text_output, "*.jsonl"),
            (chunk_output, "*.jsonl"),
            (review_output, "*.md"),
            (quarantine_text_output, "*.jsonl"),
            (quarantine_chunk_output, "*.jsonl"),
            (release_text_output, "*.jsonl"),
            (release_chunk_output, "*.jsonl"),
        )
        for directory, pattern in outputs:
            for output_path in directory.glob(pattern):
                if output_path.stem not in active_document_ids:
                    output_path.unlink()
