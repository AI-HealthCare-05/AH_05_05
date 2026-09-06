import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ai_worker.rag.loaders.knowledge_chunk_loader import KnowledgeChunkLoader
from ai_worker.schemas.knowledge import KnowledgeChunk
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgePilotPreprocessingResult,
    SkippedKnowledgeDocument,
)


class KnowledgeReleaseCompositionInput(BaseModel):
    chunks_dir: Path
    quality_report_path: Path


class KnowledgeReleaseCompositionService:
    """검증된 여러 청크 release를 새 불변 dataset으로 조합합니다."""

    def __init__(
        self,
        *,
        chunk_loader: KnowledgeChunkLoader | None = None,
    ) -> None:
        self._chunk_loader = chunk_loader or KnowledgeChunkLoader()

    def compose(
        self,
        *,
        inputs: list[KnowledgeReleaseCompositionInput],
        output_root: Path,
        dataset_version: str,
    ) -> KnowledgePilotPreprocessingResult:
        normalized_version = dataset_version.strip()
        if not normalized_version:
            raise ValueError("dataset_version은 비어 있을 수 없습니다.")
        if not inputs:
            raise ValueError("조합할 Knowledge release가 없습니다.")

        root = Path(output_root)
        if root.exists():
            raise ValueError(f"불변 release 출력 경로가 이미 존재합니다: {root}")

        chunks_by_document: dict[str, list[KnowledgeChunk]] = defaultdict(list)
        document_reports = []
        skipped_documents: list[SkippedKnowledgeDocument] = []
        ready_source_ids: set[str] = set()
        seen_document_ids: set[str] = set()
        seen_chunk_ids: set[str] = set()

        for release_input in inputs:
            raw_report = self._read_quality_report(release_input.quality_report_path)
            source_dataset_version = self._read_dataset_version(raw_report)
            chunks = self._chunk_loader.load(
                release_input.chunks_dir,
                expected_dataset_version=source_dataset_version,
            )
            report = self._load_quality_report(
                raw_report=raw_report,
                chunks=chunks,
            )
            self._validate_release_contract(report=report, chunks=chunks)

            document_ids = {chunk.metadata.document_id for chunk in chunks}
            duplicate_documents = sorted(document_ids & seen_document_ids)
            if duplicate_documents:
                raise ValueError("조합 대상 release에 중복 document_id가 있습니다: " + ", ".join(duplicate_documents))
            duplicate_chunks = sorted(chunk.chunk_id for chunk in chunks if chunk.chunk_id in seen_chunk_ids)
            if duplicate_chunks:
                raise ValueError("조합 대상 release에 중복 chunk_id가 있습니다: " + ", ".join(duplicate_chunks))

            seen_document_ids.update(document_ids)
            seen_chunk_ids.update(chunk.chunk_id for chunk in chunks)
            document_reports.extend(report.document_reports)
            skipped_documents.extend(report.skipped_documents)
            ready_source_ids.update(report.ready_for_bulk_source_ids)
            for chunk in chunks:
                chunks_by_document[chunk.metadata.document_id].append(
                    chunk.model_copy(
                        update={"metadata": chunk.metadata.model_copy(update={"dataset_version": normalized_version})}
                    )
                )

        result = KnowledgePilotPreprocessingResult(
            dataset_version=normalized_version,
            processed_document_count=len(chunks_by_document),
            chunk_count=sum(len(chunks) for chunks in chunks_by_document.values()),
            skipped_documents=self._unique_skipped_documents(skipped_documents),
            document_reports=document_reports,
            ready_for_bulk_source_ids=sorted(ready_source_ids),
        )
        self._write_release(
            root=root,
            chunks_by_document=chunks_by_document,
            report=result,
        )
        return result

    @staticmethod
    def _read_quality_report(path: Path) -> dict[str, Any]:
        report_path = Path(path)
        if not report_path.is_file():
            raise ValueError(f"전처리 품질 보고서가 없습니다: {report_path}")
        raw_report = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(raw_report, dict):
            raise ValueError("전처리 품질 보고서는 JSON 객체여야 합니다.")
        return raw_report

    @staticmethod
    def _read_dataset_version(raw_report: dict[str, Any]) -> str:
        dataset_version = raw_report.get("dataset_version")
        if not isinstance(dataset_version, str) or not dataset_version.strip():
            raise ValueError("전처리 품질 보고서에 dataset_version이 없습니다.")
        return dataset_version.strip()

    @staticmethod
    def _load_quality_report(
        *,
        raw_report: dict[str, Any],
        chunks: list[KnowledgeChunk],
    ) -> KnowledgePilotPreprocessingResult:
        migrated_report = dict(raw_report)
        document_paths = {
            chunk.metadata.document_id: (chunk.metadata.file_name or f"{chunk.metadata.document_id}.pdf")
            for chunk in chunks
        }
        raw_document_reports = migrated_report.get("document_reports", [])
        migrated_document_reports = []
        for item in raw_document_reports:
            if not isinstance(item, dict):
                migrated_document_reports.append(item)
                continue
            migrated_item = dict(item)
            document_id = migrated_item.get("document_id")
            if not migrated_item.get("source_document_path"):
                migrated_item["source_document_path"] = document_paths.get(
                    document_id,
                    f"{document_id}.pdf",
                )
            if "release_ready" not in migrated_item:
                migrated_item["release_ready"] = (
                    migrated_item.get("automatic_status") == KnowledgeAutomaticQualityStatus.PASS
                    and migrated_item.get("manual_review_status") == "APPROVED"
                )
            migrated_document_reports.append(migrated_item)
        migrated_report["document_reports"] = migrated_document_reports
        return KnowledgePilotPreprocessingResult.model_validate(migrated_report)

    @staticmethod
    def _validate_release_contract(
        *,
        report: KnowledgePilotPreprocessingResult,
        chunks: list[KnowledgeChunk],
    ) -> None:
        document_ids = {chunk.metadata.document_id for chunk in chunks}
        if report.chunk_count != len(chunks):
            raise ValueError("품질 보고서와 실제 release의 청크 수가 일치하지 않습니다.")
        if report.processed_document_count != len(document_ids):
            raise ValueError("품질 보고서와 실제 release의 문서 수가 일치하지 않습니다.")

        reports_by_document = {
            document_report.document_id: document_report for document_report in report.document_reports
        }
        if set(reports_by_document) != document_ids:
            raise ValueError("품질 보고서와 실제 release의 document_id가 일치하지 않습니다.")
        for document_id in document_ids:
            document_report = reports_by_document[document_id]
            actual_count = sum(chunk.metadata.document_id == document_id for chunk in chunks)
            if document_report.chunk_count != actual_count:
                raise ValueError(f"문서별 품질 보고서와 청크 수가 일치하지 않습니다: {document_id}")
            if (
                document_report.automatic_status != KnowledgeAutomaticQualityStatus.PASS
                or not document_report.release_ready
            ):
                raise ValueError(f"품질 승인되지 않은 문서가 release에 포함되었습니다: {document_id}")

    @staticmethod
    def _unique_skipped_documents(
        items: list[SkippedKnowledgeDocument],
    ) -> list[SkippedKnowledgeDocument]:
        unique: dict[tuple[str, str], SkippedKnowledgeDocument] = {}
        for item in items:
            unique[(item.document_id, item.reason)] = item
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _write_release(
        *,
        root: Path,
        chunks_by_document: dict[str, list[KnowledgeChunk]],
        report: KnowledgePilotPreprocessingResult,
    ) -> None:
        chunks_dir = root / "chunks"
        reports_dir = root / "reports"
        chunks_dir.mkdir(parents=True)
        reports_dir.mkdir(parents=True)
        for document_id, chunks in sorted(chunks_by_document.items()):
            content = "\n".join(
                chunk.model_dump_json()
                for chunk in sorted(
                    chunks,
                    key=lambda item: item.metadata.chunk_index,
                )
            )
            (chunks_dir / f"{document_id}.jsonl").write_text(
                content + "\n",
                encoding="utf-8",
            )
        (reports_dir / "preprocessing-quality.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
