import json
import re
import unicodedata
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from ai_worker.schemas.knowledge import KnowledgeDocumentType
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityReasonCode,
    KnowledgeAutomaticQualityStatus,
    KnowledgeDocumentPreprocessingReport,
    KnowledgePilotPreprocessingResult,
)


class KnowledgeBlockedDocumentRecoveryStatus(StrEnum):
    AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT = "AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class KnowledgeBlockedDocumentRecoveryRecord(BaseModel):
    document_id: str
    source_id: str
    source_document_path: Path
    status: KnowledgeBlockedDocumentRecoveryStatus
    reason: str
    reason_codes: list[KnowledgeAutomaticQualityReasonCode] = Field(default_factory=list)
    review_pages: list[int] = Field(default_factory=list)


class KnowledgeBlockedDocumentRecoveryResult(BaseModel):
    records: list[KnowledgeBlockedDocumentRecoveryRecord] = Field(default_factory=list)
    automatically_excluded_count: int = Field(default=0, ge=0)
    manual_review_required_count: int = Field(default=0, ge=0)

    @property
    def automatically_excluded_document_ids(self) -> set[str]:
        return {
            record.document_id
            for record in self.records
            if record.status == KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT
        }


class KnowledgeBlockedDocumentRecoveryService:
    """Keep only unrecoverable medical-source layout issues in the human review queue."""

    _SUPPLEMENT_INGREDIENT_SOURCE_ID = "food_safety_korea_supplement_ingredients"
    _UNRECOVERABLE_SUPPLEMENT_REASONS = frozenset(
        {
            KnowledgeAutomaticQualityReasonCode.NO_SEMANTIC_SECTIONS,
            KnowledgeAutomaticQualityReasonCode.MISSING_SUPPLEMENT_CONTEXT,
        }
    )

    def write(
        self,
        *,
        result: KnowledgePilotPreprocessingResult,
        output_root: Path,
    ) -> KnowledgeBlockedDocumentRecoveryResult:
        root = Path(output_root)
        records = [
            self._classify(
                report=report,
                output_root=root,
            )
            for report in result.document_reports
            if self._requires_recovery_decision(report)
        ]
        recovery = KnowledgeBlockedDocumentRecoveryResult(
            records=records,
            automatically_excluded_count=sum(
                record.status == KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT
                for record in records
            ),
            manual_review_required_count=sum(
                record.status == KnowledgeBlockedDocumentRecoveryStatus.MANUAL_REVIEW_REQUIRED for record in records
            ),
        )
        reports_root = root / "reports"
        reports_root.mkdir(parents=True, exist_ok=True)
        (reports_root / "blocked-document-recovery.json").write_text(
            recovery.model_dump_json(indent=2),
            encoding="utf-8",
        )
        self._remove_automatic_exclusion_review_samples(
            root=root,
            records=records,
            reports=result.document_reports,
        )
        self._write_manual_review_document(
            root=root,
            records=records,
        )
        return recovery

    @staticmethod
    def _requires_recovery_decision(report: KnowledgeDocumentPreprocessingReport) -> bool:
        return (
            report.automatic_status
            in {
                KnowledgeAutomaticQualityStatus.BLOCKED,
                KnowledgeAutomaticQualityStatus.REVIEW,
            }
            and report.approved_chunk_count == 0
        )

    def _classify(
        self,
        *,
        report: KnowledgeDocumentPreprocessingReport,
        output_root: Path,
    ) -> KnowledgeBlockedDocumentRecoveryRecord:
        if self._is_unrecoverable_supplement_text(
            report=report,
            output_root=output_root,
        ):
            return KnowledgeBlockedDocumentRecoveryRecord(
                document_id=report.document_id,
                source_id=report.source_id,
                source_document_path=report.source_document_path,
                status=KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT,
                reason=(
                    "소비자용 핵심 항목이 없고 원본 텍스트가 문자 인코딩 손상 상태라 "
                    "의료·영양 근거를 안전하게 복원할 수 없습니다."
                ),
                reason_codes=report.reason_codes,
            )
        return KnowledgeBlockedDocumentRecoveryRecord(
            document_id=report.document_id,
            source_id=report.source_id,
            source_document_path=report.source_document_path,
            status=KnowledgeBlockedDocumentRecoveryStatus.MANUAL_REVIEW_REQUIRED,
            reason=self._manual_review_reason(report),
            reason_codes=report.reason_codes,
            review_pages=sorted(
                set(
                    [
                        *report.layout_warning_pages,
                        *report.rotated_text_warning_pages,
                    ]
                )
            ),
        )

    @staticmethod
    def _manual_review_reason(report: KnowledgeDocumentPreprocessingReport) -> str:
        if report.automatic_status == KnowledgeAutomaticQualityStatus.REVIEW:
            return "핵심 본문 섹션 또는 출처 메타데이터를 원본 PDF와 대조해 확정해야 합니다."
        return "본문 읽기 순서 또는 표 구조를 결정론적으로 보장할 수 없어 원본 PDF 대조가 필요합니다."

    def _is_unrecoverable_supplement_text(
        self,
        *,
        report: KnowledgeDocumentPreprocessingReport,
        output_root: Path,
    ) -> bool:
        if report.source_id != self._SUPPLEMENT_INGREDIENT_SOURCE_ID:
            return False
        if report.document_type != KnowledgeDocumentType.SUPPLEMENT_CODE:
            return False
        if not self._UNRECOVERABLE_SUPPLEMENT_REASONS.issubset(report.reason_codes):
            return False
        content = self._quarantined_text(
            output_root=output_root,
            document_id=report.document_id,
        )
        return self._has_high_garbled_character_ratio(content) or not self._has_consumer_summary_fields(content)

    @staticmethod
    def _has_consumer_summary_fields(content: str) -> bool:
        compact = re.sub(r"\s+", "", content)
        has_ingredient = "기능성원료명" in compact or "원료또는원재료" in compact
        return has_ingredient and all(
            heading in compact
            for heading in (
                "기능성내용",
                "일일섭취량",
                "섭취시주의사항",
            )
        )

    @staticmethod
    def _quarantined_text(*, output_root: Path, document_id: str) -> str:
        path = output_root / "quarantine" / "text" / f"{document_id}.jsonl"
        if not path.is_file():
            return ""
        contents: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                return ""
            content = payload.get("content")
            if isinstance(content, str):
                contents.append(content)
        return "\n".join(contents)

    @staticmethod
    def _has_high_garbled_character_ratio(content: str) -> bool:
        letters = [character for character in content if character.isalpha()]
        if len(letters) < 8:
            return False
        unreadable_letters = [
            character
            for character in letters
            if not KnowledgeBlockedDocumentRecoveryService._is_expected_korean_or_latin_letter(character)
        ]
        return len(unreadable_letters) / len(letters) >= 0.2

    @staticmethod
    def _is_expected_korean_or_latin_letter(character: str) -> bool:
        code_point = ord(character)
        return (
            "LATIN" in unicodedata.name(character, "")
            or "GREEK" in unicodedata.name(character, "")
            or 0xAC00 <= code_point <= 0xD7A3
        )

    @staticmethod
    def _remove_automatic_exclusion_review_samples(
        *,
        root: Path,
        records: list[KnowledgeBlockedDocumentRecoveryRecord],
        reports: list[KnowledgeDocumentPreprocessingReport],
    ) -> None:
        report_by_document_id = {report.document_id: report for report in reports}
        for record in records:
            if record.status != KnowledgeBlockedDocumentRecoveryStatus.AUTOMATIC_EXCLUDED_UNRECOVERABLE_TEXT:
                continue
            report = report_by_document_id[record.document_id]
            (root / report.review_sample_path).unlink(missing_ok=True)

    @staticmethod
    def _write_manual_review_document(
        *,
        root: Path,
        records: list[KnowledgeBlockedDocumentRecoveryRecord],
    ) -> None:
        path = root / "review" / "REQUIRES_MANUAL_REVIEW.md"
        manual_records = [
            record
            for record in records
            if record.status == KnowledgeBlockedDocumentRecoveryStatus.MANUAL_REVIEW_REQUIRED
        ]
        if not manual_records:
            path.unlink(missing_ok=True)
            return
        lines = [
            "# 수동 검수 필요 문서",
            "",
            "자동 복원 시 본문 순서나 표 행이 바뀔 수 있는 문서만 남겼습니다.",
            "자동 제외 문서는 이 목록에 포함하지 않습니다.",
        ]
        for record in manual_records:
            page_suffix = (
                " · 대조 페이지: 원본 " + ", ".join(f"p.{page}" for page in record.review_pages)
                if record.review_pages
                else ""
            )
            lines.extend(
                [
                    "",
                    f"## {record.document_id}",
                    "",
                    f"- 원본 PDF: `{record.source_document_path}`",
                    f"- 차단 사유: {', '.join(reason.value for reason in record.reason_codes)}",
                    f"- 수동 검수 이유: {record.reason}{page_suffix}",
                    "- [ ] 본문 읽기 순서와 표 행이 원문과 일치하는지 확인",
                    "- [ ] 안전하게 분리 가능한 본문·표 청크만 승인",
                ]
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
