import re
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

import yaml
from pydantic import BaseModel, Field

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
    KnowledgeDocumentType,
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


class KnowledgeAutomaticQualityReasonCode(StrEnum):
    NO_SEMANTIC_SECTIONS = "NO_SEMANTIC_SECTIONS"
    OVERSIZED_CHUNK = "OVERSIZED_CHUNK"
    MISSING_SUPPLEMENT_CONTEXT = "MISSING_SUPPLEMENT_CONTEXT"
    SUSPICIOUS_SUPPLEMENT_UNIT = "SUSPICIOUS_SUPPLEMENT_UNIT"
    UNRESOLVED_HIERARCHY_REFERENCE = "UNRESOLVED_HIERARCHY_REFERENCE"
    SUPPLEMENT_SECTION_CONTAMINATION = "SUPPLEMENT_SECTION_CONTAMINATION"


_BLOCKING_QUALITY_REASONS = {
    KnowledgeAutomaticQualityReasonCode.OVERSIZED_CHUNK,
    KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
    KnowledgeAutomaticQualityReasonCode.SUSPICIOUS_SUPPLEMENT_UNIT,
    KnowledgeAutomaticQualityReasonCode.UNRESOLVED_HIERARCHY_REFERENCE,
    KnowledgeAutomaticQualityReasonCode.SUPPLEMENT_SECTION_CONTAMINATION,
}

_RESOLVED_SUPPLEMENT_REFERENCE = re.compile(
    r"-\s*(?P<top>\d+)\)\s*>\s*"
    r"\((?P<sub>\d+)\)\s*>\s*"
    r"\((?P<label>[가-하])\):"
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


class KnowledgeDocumentPreprocessingReport(BaseModel):
    document_id: str
    source_id: str
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
        text_output.mkdir(parents=True, exist_ok=True)
        chunk_output.mkdir(parents=True, exist_ok=True)
        report_output.mkdir(parents=True, exist_ok=True)
        review_output.mkdir(parents=True, exist_ok=True)
        quality_report_path = report_output / "preprocessing-quality.json"
        quality_report_path.unlink(missing_ok=True)

        active_document_ids = {pilot.document_id for pilot in pilot_manifest.pilots}
        self._remove_orphaned_outputs(
            active_document_ids=active_document_ids,
            text_output=text_output,
            chunk_output=chunk_output,
            review_output=review_output,
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
                document_id=pilot.document_id,
                repo_path=pilot.repo_path,
                dataset_version=normalized_version,
            )
            pages = self._loader.load(
                self._repo_root / pilot.repo_path,
                metadata,
            )
            normalized_pages = self._normalizer.normalize_pages(pages)
            quality = self._normalizer.assess_pages_quality(normalized_pages)
            if quality.status != TextQualityStatus.PASS:
                failed_representative_source_ids.add(pilot.source_id)
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason=f"TEXT_QUALITY_{quality.status.value}",
                    )
                )
                continue

            chunks = self._splitter.split(normalized_pages)
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

        reason_codes = list(dict.fromkeys(reason_codes))
        if _BLOCKING_QUALITY_REASONS.intersection(reason_codes):
            automatic_status = KnowledgeAutomaticQualityStatus.BLOCKED
        elif reason_codes:
            automatic_status = KnowledgeAutomaticQualityStatus.REVIEW
        else:
            automatic_status = KnowledgeAutomaticQualityStatus.PASS

        return KnowledgeDocumentPreprocessingReport(
            document_id=pilot.document_id,
            source_id=pilot.source_id,
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
            review_sample_path=review_sample_path,
        )

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
        sample_indices = KnowledgePilotPreprocessingService._sample_indices(chunks)
        lines = [
            f"# 전처리 표본 검수: {report.document_id}",
            "",
            f"- 출처 유형: `{report.document_type.value}`",
            f"- 대표 선정 이유: {report.selection_reason}",
            f"- 자동 품질 상태: `{report.automatic_status.value}`",
            f"- 수동 검수 상태: `{report.manual_review_status.value}`",
            f"- 페이지/청크: {report.page_count}/{report.chunk_count}",
            (
                "- 자동 검사 사유: "
                + (", ".join(reason.value for reason in report.reason_codes) if report.reason_codes else "없음")
            ),
            "",
            "## 사람이 확인할 항목",
            "",
            "- [ ] 원본 읽기 순서와 추출 텍스트 순서가 같다.",
            "- [ ] 제목과 설명이 같은 의미 단위에 남아 있다.",
            "- [ ] 약명·성분명·함량·단위가 원문과 같다.",
            "- [ ] 서로 다른 약·성분·사례가 한 청크에 섞이지 않았다.",
            "- [ ] 페이지 범위와 출처 표시가 원문 위치와 맞는다.",
            "",
            "## 결정론적 표본 청크",
        ]
        for chunk_index in sample_indices:
            chunk = chunks[chunk_index]
            metadata = chunk.metadata
            lines.extend(
                [
                    "",
                    (
                        f"### 청크 {metadata.chunk_index} · "
                        f"{metadata.section_type.value} · "
                        f"p.{metadata.page_start}-{metadata.page_end} · "
                        f"{chunk.token_count} tokens"
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
    def _supplement_quality_reason_codes(
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeAutomaticQualityReasonCode]:
        reasons: list[KnowledgeAutomaticQualityReasonCode] = []
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
    def _sample_indices(chunks: list[KnowledgeChunk]) -> list[int]:
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
        document_id: str,
        repo_path: Path,
        dataset_version: str,
    ) -> KnowledgeMetadata:
        document_type = cast(KnowledgeDocumentType, source.document_type)
        title = KnowledgePilotPreprocessingService._title_from_path(repo_path)
        ingredient_names: list[str] = []
        drug_names: list[str] = []

        if document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            ingredient_names = [title]
        elif document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            drug_names = [title]

        return KnowledgeMetadata(
            source_id=source.source_id,
            document_id=document_id,
            title=title,
            provider=source.provider,
            access_scope=source.access_scope,
            document_type=document_type,
            dataset_version=dataset_version,
            file_name=repo_path.name,
            drug_names=drug_names,
            ingredient_names=ingredient_names,
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
    ) -> None:
        outputs = (
            (text_output, ".jsonl"),
            (chunk_output, ".jsonl"),
            (review_output, ".md"),
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
    ) -> None:
        outputs = (
            (text_output, "*.jsonl"),
            (chunk_output, "*.jsonl"),
            (review_output, "*.md"),
        )
        for directory, pattern in outputs:
            for output_path in directory.glob(pattern):
                if output_path.stem not in active_document_ids:
                    output_path.unlink()
