import json
from collections import Counter
from pathlib import Path
from typing import Any

from ai_worker.schemas.knowledge_manifest import KnowledgeProcessingStatus
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingResult,
)


class KnowledgeRecoveryReportingService:
    """전체 코퍼스 복원 결과와 OCR 대기 문서를 기록합니다."""

    def write(
        self,
        *,
        documents_path: Path,
        baseline_quality_report_path: Path,
        result: KnowledgePilotPreprocessingResult,
        output_root: Path,
    ) -> None:
        documents = self._load_documents(documents_path)
        baseline = self._load_json(baseline_quality_report_path)
        reports_root = Path(output_root) / "reports"
        reports_root.mkdir(parents=True, exist_ok=True)

        catalog_ocr_document_ids = {
            document["document_id"]
            for document in documents
            if document["processing_status"] == KnowledgeProcessingStatus.OCR_REQUIRED.value
        }
        dynamic_ocr_document_ids = {
            skipped.document_id for skipped in result.skipped_documents if skipped.reason == "TEXT_QUALITY_OCR_REQUIRED"
        }
        ocr_document_ids = catalog_ocr_document_ids | dynamic_ocr_document_ids
        ocr_documents = [document for document in documents if document["document_id"] in ocr_document_ids]
        self._write_jsonl(
            reports_root / "ocr-required.jsonl",
            (
                {
                    "document_id": document["document_id"],
                    "repo_path": document["repo_path"],
                    "sha256": document["sha256"],
                    "source_id": document["source_id"],
                    "ocr_reason": (
                        "CATALOG_OCR_REQUIRED"
                        if document["document_id"] in catalog_ocr_document_ids
                        else "TEXT_QUALITY_OCR_REQUIRED"
                    ),
                }
                for document in ocr_documents
            ),
        )

        baseline_skipped_ids = {
            item["document_id"]
            for item in baseline.get("skipped_documents", [])
            if isinstance(item, dict) and isinstance(item.get("document_id"), str)
        }
        released_ids = {report.document_id for report in result.document_reports}
        document_source_by_id = {document["document_id"]: document["source_id"] for document in documents}
        skipped_by_reason = Counter(item.reason for item in result.skipped_documents)
        skipped_by_source_reason = Counter(
            (
                document_source_by_id.get(item.document_id, "UNKNOWN"),
                item.reason,
            )
            for item in result.skipped_documents
        )
        released_by_source = Counter(report.source_id for report in result.document_reports)
        partial_by_source = Counter(report.source_id for report in result.document_reports if report.partial_release)
        summary: dict[str, Any] = {
            "dataset_version": result.dataset_version,
            "catalog_document_count": len(documents),
            "text_extractable_document_count": sum(
                document["processing_status"] == KnowledgeProcessingStatus.TEXT_EXTRACTABLE.value
                for document in documents
            ),
            "ocr_required_document_count": len(ocr_documents),
            "catalog_ocr_required_document_count": len(catalog_ocr_document_ids),
            "dynamic_ocr_required_document_count": len(dynamic_ocr_document_ids),
            "ocr_queue_document_count": len(ocr_documents),
            "release_document_count": result.processed_document_count,
            "released_chunk_count": result.chunk_count,
            "partial_release_document_count": sum(report.partial_release for report in result.document_reports),
            "recovered_document_count": len(released_ids & baseline_skipped_ids),
            "remaining_skipped_document_count": len(result.skipped_documents),
            "released_document_count_by_source": dict(sorted(released_by_source.items())),
            "partial_release_document_count_by_source": dict(
                sorted(partial_by_source.items()),
            ),
            "remaining_skipped_document_count_by_reason": dict(
                sorted(skipped_by_reason.items()),
            ),
            "remaining_skipped_document_count_by_source_reason": [
                {
                    "source_id": source_id,
                    "reason": reason,
                    "document_count": count,
                }
                for (source_id, reason), count in sorted(skipped_by_source_reason.items())
            ],
        }
        self._write_json(
            reports_root / "recovery-summary.json",
            summary,
        )
        self._write_markdown(
            reports_root / "recovery-summary.md",
            summary,
        )

    @staticmethod
    def _load_documents(path: Path) -> list[dict[str, str]]:
        documents: list[dict[str, str]] = []
        for line_number, line in enumerate(
            Path(path).read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            item = json.loads(line)
            required = ("document_id", "repo_path", "sha256", "source_id", "processing_status")
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in required):
                raise ValueError(f"문서 매니페스트 {line_number}행의 필수 값이 올바르지 않습니다.")
            documents.append({key: item[key] for key in required})
        return documents

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("기준선 품질 보고서는 JSON 객체여야 합니다.")
        return payload

    @staticmethod
    def _write_jsonl(path: Path, rows: Any) -> None:
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_markdown(path: Path, summary: dict[str, Any]) -> None:
        path.write_text(
            "\n".join(
                [
                    "# Knowledge Corpus 복원 결과",
                    "",
                    f"- 데이터셋: `{summary['dataset_version']}`",
                    f"- 카탈로그 문서: `{summary['catalog_document_count']}`",
                    f"- 텍스트 추출 가능: `{summary['text_extractable_document_count']}`",
                    (
                        "- OCR 대기: "
                        f"`{summary['ocr_queue_document_count']}` "
                        "(카탈로그 "
                        f"`{summary['catalog_ocr_required_document_count']}`, "
                        "전처리 중 감지 "
                        f"`{summary['dynamic_ocr_required_document_count']}`)"
                    ),
                    f"- 릴리스 문서: `{summary['release_document_count']}`",
                    f"- 릴리스 청크: `{summary['released_chunk_count']}`",
                    f"- 부분 승인 문서: `{summary['partial_release_document_count']}`",
                    f"- 기존 제외 문서 중 복원: `{summary['recovered_document_count']}`",
                    f"- 남은 제외 문서: `{summary['remaining_skipped_document_count']}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
