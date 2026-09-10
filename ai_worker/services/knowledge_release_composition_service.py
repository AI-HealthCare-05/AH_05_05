import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ai_worker.rag.loaders.knowledge_chunk_loader import KnowledgeChunkLoader
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.metadata.knowledge_entity_extractor import KnowledgeEntityExtractor
from ai_worker.schemas.knowledge import KnowledgeChunk, KnowledgeEntityCatalogEntry
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgeAutomaticQualityStatus,
    KnowledgeChunkReviewStatus,
    KnowledgeDocumentPreprocessingReport,
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
        interaction_annotations: KnowledgeInteractionAnnotationRegistry | None = None,
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
        entity_extractor = KnowledgeEntityExtractor(
            interaction_annotations=interaction_annotations,
        )

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
            release_document_reports = self._validate_release_contract(
                report=report,
                chunks=chunks,
            )

            document_ids = {chunk.metadata.document_id for chunk in chunks}
            duplicate_documents = sorted(document_ids & seen_document_ids)
            if duplicate_documents:
                raise ValueError("조합 대상 release에 중복 document_id가 있습니다: " + ", ".join(duplicate_documents))
            duplicate_chunks = sorted(chunk.chunk_id for chunk in chunks if chunk.chunk_id in seen_chunk_ids)
            if duplicate_chunks:
                raise ValueError("조합 대상 release에 중복 chunk_id가 있습니다: " + ", ".join(duplicate_chunks))

            seen_document_ids.update(document_ids)
            seen_chunk_ids.update(chunk.chunk_id for chunk in chunks)
            document_reports.extend(release_document_reports)
            skipped_documents.extend(report.skipped_documents)
            ready_source_ids.update(document_report.source_id for document_report in release_document_reports)
            for chunk in chunks:
                release_chunk = self._apply_interaction_annotations(
                    chunk.model_copy(
                        update={"metadata": chunk.metadata.model_copy(update={"dataset_version": normalized_version})}
                    ),
                    entity_extractor=entity_extractor,
                )
                chunks_by_document[release_chunk.metadata.document_id].append(release_chunk)

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
    ) -> list[KnowledgeDocumentPreprocessingReport]:
        document_ids = {chunk.metadata.document_id for chunk in chunks}
        KnowledgeReleaseCompositionService._validate_report_totals(
            report=report,
            chunks=chunks,
            document_ids=document_ids,
        )
        reports_by_document = {
            document_report.document_id: document_report for document_report in report.document_reports
        }
        KnowledgeReleaseCompositionService._validate_non_release_reports(
            report=report,
            document_ids=document_ids,
            reports_by_document=reports_by_document,
        )
        for document_id in document_ids:
            document_report = reports_by_document[document_id]
            actual_count = sum(chunk.metadata.document_id == document_id for chunk in chunks)
            KnowledgeReleaseCompositionService._validate_released_document(
                document_report=document_report,
                document_id=document_id,
                actual_count=actual_count,
            )

        return [reports_by_document[document_id] for document_id in sorted(document_ids)]

    @staticmethod
    def _validate_report_totals(
        *,
        report: KnowledgePilotPreprocessingResult,
        chunks: list[KnowledgeChunk],
        document_ids: set[str],
    ) -> None:
        if report.chunk_count != len(chunks):
            raise ValueError("품질 보고서와 실제 release의 청크 수가 일치하지 않습니다.")
        if report.processed_document_count != len(document_ids):
            raise ValueError("품질 보고서와 실제 release의 문서 수가 일치하지 않습니다.")

    @staticmethod
    def _validate_non_release_reports(
        *,
        report: KnowledgePilotPreprocessingResult,
        document_ids: set[str],
        reports_by_document: dict[str, KnowledgeDocumentPreprocessingReport],
    ) -> None:
        missing_reports = document_ids - set(reports_by_document)
        if missing_reports:
            raise ValueError("품질 보고서와 실제 release의 document_id가 일치하지 않습니다.")

        skipped_document_ids = {item.document_id for item in report.skipped_documents}
        for document_id, document_report in reports_by_document.items():
            if document_id in document_ids:
                continue
            if document_id not in skipped_document_ids:
                raise ValueError("릴리스에 없는 문서가 skipped_documents에 없습니다.")
            if (
                document_report.release_ready
                or document_report.released_chunk_count
                or document_report.approved_chunk_count
            ):
                raise ValueError("릴리스에 없는 문서가 승인된 청크를 포함합니다.")

    @staticmethod
    def _validate_released_document(
        *,
        document_report: KnowledgeDocumentPreprocessingReport,
        document_id: str,
        actual_count: int,
    ) -> None:
        if document_report.chunk_count != actual_count:
            raise ValueError(f"문서별 품질 보고서와 청크 수가 일치하지 않습니다: {document_id}")
        if not document_report.release_ready:
            raise ValueError(f"품질 승인되지 않은 문서가 release에 포함되었습니다: {document_id}")
        if not KnowledgeReleaseCompositionService._is_released_document_approved(
            document_report=document_report,
            actual_count=actual_count,
        ):
            raise ValueError(f"품질 승인되지 않은 문서가 release에 포함되었습니다: {document_id}")
        if document_report.released_chunk_count not in {0, actual_count}:
            raise ValueError(f"릴리스 승인 청크 수가 일치하지 않습니다: {document_id}")
        if any(review.status != KnowledgeChunkReviewStatus.APPROVED for review in document_report.chunk_reviews):
            raise ValueError(f"승인되지 않은 청크가 release에 포함되었습니다: {document_id}")

    @staticmethod
    def _is_released_document_approved(
        *,
        document_report: KnowledgeDocumentPreprocessingReport,
        actual_count: int,
    ) -> bool:
        if document_report.automatic_status == KnowledgeAutomaticQualityStatus.PASS:
            return True
        if document_report.partial_release:
            return True
        return (
            document_report.manual_review_status.value == "APPROVED"
            and document_report.released_chunk_count == actual_count
            and all(review.status == "APPROVED" for review in document_report.chunk_reviews)
        )

    @staticmethod
    def _apply_interaction_annotations(
        chunk: KnowledgeChunk,
        *,
        entity_extractor: KnowledgeEntityExtractor,
    ) -> KnowledgeChunk:
        """기존 벡터 본문은 유지하고, 검수된 직접 관계 metadata만 보강한다."""
        metadata = chunk.metadata
        extracted = entity_extractor.extract_from_chunk(
            document_type=metadata.document_type,
            title=metadata.title,
            content=chunk.content,
            document_id=metadata.document_id,
            section_type=metadata.section_type,
        )
        if not extracted.interaction_pair_keys:
            return chunk

        interaction_types = {
            value
            for value in (
                metadata.interaction_type,
                extracted.interaction_type,
            )
            if value is not None
        }
        return chunk.model_copy(
            update={
                "metadata": metadata.model_copy(
                    update={
                        "drug_names": KnowledgeReleaseCompositionService._unique_strings(
                            [*metadata.drug_names, *extracted.drug_names]
                        ),
                        "ingredient_names": KnowledgeReleaseCompositionService._unique_strings(
                            [*metadata.ingredient_names, *extracted.ingredient_names]
                        ),
                        "food_names": KnowledgeReleaseCompositionService._unique_strings(
                            [*metadata.food_names, *extracted.food_names]
                        ),
                        "entity_catalog_entries": KnowledgeReleaseCompositionService._unique_catalog_entries(
                            [*metadata.entity_catalog_entries, *extracted.entity_catalog_entries]
                        ),
                        "interaction_type": next(iter(interaction_types)) if len(interaction_types) == 1 else None,
                        "interaction_pair_keys": KnowledgeReleaseCompositionService._unique_strings(
                            [*metadata.interaction_pair_keys, *extracted.interaction_pair_keys]
                        ),
                    }
                )
            }
        )

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _unique_catalog_entries(
        entries: list[KnowledgeEntityCatalogEntry],
    ) -> list[KnowledgeEntityCatalogEntry]:
        unique_entries: list[KnowledgeEntityCatalogEntry] = []
        for entry in entries:
            if entry not in unique_entries:
                unique_entries.append(entry)
        return unique_entries

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
