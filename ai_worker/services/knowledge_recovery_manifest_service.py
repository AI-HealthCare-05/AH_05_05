import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from ai_worker.schemas.knowledge_manifest import KnowledgeSourcesManifest
from ai_worker.schemas.knowledge_recovery import (
    KnowledgeOcrManifestEntry,
    KnowledgeOcrManifestOrigin,
    KnowledgePendingChunkRecoveryTarget,
    KnowledgeRecoveryChunkStatus,
    KnowledgeRecoveryManifestResult,
    PartialChunkRecoveryEntry,
)


class KnowledgeRecoveryManifestService:
    """격리 청크와 OCR 대기 문서를 재현 가능한 실행 단위로 만듭니다."""

    def build(
        self,
        *,
        documents_path: Path,
        corpus_quality_audit_path: Path,
        release_chunks_dir: Path,
        ocr_queue_path: Path,
        sources_path: Path | None = None,
    ) -> KnowledgeRecoveryManifestResult:
        documents = self._load_documents(documents_path)
        access_scope_by_source = self._load_access_scopes(sources_path)
        partial_entries = self._build_partial_entries(
            documents=documents,
            corpus_quality_audit_path=corpus_quality_audit_path,
            release_chunks_dir=release_chunks_dir,
        )
        ocr_entries = self._build_ocr_entries(
            documents=documents,
            ocr_queue_path=ocr_queue_path,
            access_scope_by_source=access_scope_by_source,
        )
        return KnowledgeRecoveryManifestResult(
            partial_entries=partial_entries,
            ocr_entries=ocr_entries,
        )

    @staticmethod
    def validate_source_files(
        *,
        result: KnowledgeRecoveryManifestResult,
        repo_root: Path,
    ) -> None:
        """Stop recovery when a manifest no longer points to the reviewed PDF."""
        entries = [*result.partial_entries, *result.ocr_entries]
        seen_document_ids: set[str] = set()
        for entry in entries:
            if entry.document_id in seen_document_ids:
                raise ValueError(f"복원 매니페스트에 중복 document_id가 있습니다: {entry.document_id}")
            seen_document_ids.add(entry.document_id)
            source_path = Path(repo_root) / entry.repo_path
            if not source_path.is_file():
                raise ValueError(f"복원 대상 원본 PDF가 없습니다: {entry.document_id}")
            actual_hash = sha256(source_path.read_bytes()).hexdigest()
            if actual_hash != entry.source_sha256:
                raise ValueError(f"원본 SHA-256이 매니페스트와 다릅니다: {entry.document_id}")

    def write(
        self,
        *,
        result: KnowledgeRecoveryManifestResult,
        partial_manifest_path: Path,
        ocr_manifest_path: Path,
    ) -> None:
        self._write_jsonl(
            partial_manifest_path,
            (entry.model_dump(mode="json") for entry in result.partial_entries),
        )
        self._write_jsonl(
            ocr_manifest_path,
            (entry.model_dump(mode="json") for entry in result.ocr_entries),
        )

    @staticmethod
    def _load_documents(path: Path) -> dict[str, dict[str, str]]:
        documents: dict[str, dict[str, str]] = {}
        for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            required = ("document_id", "source_id", "repo_path", "sha256", "processing_status")
            if not isinstance(item, dict) or any(not isinstance(item.get(key), str) for key in required):
                raise ValueError(f"문서 매니페스트 {line_number}행의 필수 값이 올바르지 않습니다.")
            document_id = item["document_id"]
            if document_id in documents:
                raise ValueError(f"문서 매니페스트에 중복 document_id가 있습니다: {document_id}")
            documents[document_id] = {key: item[key] for key in required}
        return documents

    @staticmethod
    def _load_access_scopes(path: Path | None) -> dict[str, Any]:
        if path is None:
            return {}
        manifest = KnowledgeSourcesManifest.model_validate(
            yaml.safe_load(Path(path).read_text(encoding="utf-8")),
        )
        return {source.source_id: source.access_scope for source in manifest.sources}

    def _build_partial_entries(
        self,
        *,
        documents: dict[str, dict[str, str]],
        corpus_quality_audit_path: Path,
        release_chunks_dir: Path,
    ) -> list[PartialChunkRecoveryEntry]:
        raw_audit = self._read_json_object(corpus_quality_audit_path)
        raw_reports = raw_audit.get("document_reports")
        if not isinstance(raw_reports, list):
            raise ValueError("corpus quality audit에 document_reports가 없습니다.")

        entries: list[PartialChunkRecoveryEntry] = []
        seen_document_ids: set[str] = set()
        for raw_report in raw_reports:
            if not isinstance(raw_report, dict) or raw_report.get("partial_release") is not True:
                continue
            document_id = self._required_string(raw_report, "document_id", "corpus quality audit")
            source_id = self._required_string(raw_report, "source_id", "corpus quality audit")
            catalog_document = self._document_or_raise(documents, document_id)
            if source_id != catalog_document["source_id"]:
                raise ValueError(f"부분 복원 문서의 source_id가 카탈로그와 다릅니다: {document_id}")
            if document_id in seen_document_ids:
                raise ValueError(f"corpus quality audit에 중복 부분 복원 문서가 있습니다: {document_id}")
            seen_document_ids.add(document_id)

            raw_reviews = raw_report.get("chunk_reviews")
            if not isinstance(raw_reviews, list):
                raise ValueError(f"부분 복원 문서에 chunk_reviews가 없습니다: {document_id}")
            pending_chunks = [
                self._pending_chunk_target(review=review, document_id=document_id)
                for review in raw_reviews
                if isinstance(review, dict) and review.get("status") == KnowledgeRecoveryChunkStatus.PENDING.value
            ]
            expected_pending_count = raw_report.get("pending_chunk_count")
            if isinstance(expected_pending_count, int) and expected_pending_count != len(pending_chunks):
                raise ValueError(f"부분 복원 문서의 PENDING 청크 수가 일치하지 않습니다: {document_id}")
            if not pending_chunks:
                continue

            approved_chunk_ids = [
                self._required_string(review, "chunk_id", f"부분 복원 문서 {document_id}")
                for review in raw_reviews
                if isinstance(review, dict) and review.get("status") == "APPROVED"
            ]
            approved_content_hashes = self._approved_content_hashes(
                document_id=document_id,
                approved_chunk_ids=approved_chunk_ids,
                release_chunks_dir=release_chunks_dir,
            )
            entries.append(
                PartialChunkRecoveryEntry(
                    document_id=document_id,
                    source_id=source_id,
                    repo_path=Path(catalog_document["repo_path"]),
                    source_sha256=catalog_document["sha256"],
                    approved_content_hashes=approved_content_hashes,
                    pending_chunks=pending_chunks,
                ),
            )
        return sorted(entries, key=lambda entry: entry.document_id)

    def _build_ocr_entries(
        self,
        *,
        documents: dict[str, dict[str, str]],
        ocr_queue_path: Path,
        access_scope_by_source: dict[str, Any],
    ) -> list[KnowledgeOcrManifestEntry]:
        entries: list[KnowledgeOcrManifestEntry] = []
        seen_document_ids: set[str] = set()
        for line_number, line in enumerate(Path(ocr_queue_path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"OCR 대기열 {line_number}행은 JSON 객체여야 합니다.")
            document_id = self._required_string(row, "document_id", f"OCR 대기열 {line_number}행")
            if document_id in seen_document_ids:
                raise ValueError(f"OCR 대기열에 중복 document_id가 있습니다: {document_id}")
            seen_document_ids.add(document_id)
            catalog_document = self._document_or_raise(documents, document_id)
            for field in ("source_id", "repo_path", "sha256"):
                value = self._required_string(row, field, f"OCR 대기열 {line_number}행")
                if value != catalog_document[field]:
                    label = "SHA-256" if field == "sha256" else field
                    raise ValueError(f"OCR 대기열과 카탈로그의 {label}가 일치하지 않습니다: {document_id}")
            raw_reason = self._required_string(row, "ocr_reason", f"OCR 대기열 {line_number}행")
            origin = self._ocr_origin(raw_reason, document_id)
            entries.append(
                KnowledgeOcrManifestEntry(
                    document_id=document_id,
                    source_id=catalog_document["source_id"],
                    repo_path=Path(catalog_document["repo_path"]),
                    source_sha256=catalog_document["sha256"],
                    origin=origin,
                    access_scope=access_scope_by_source.get(catalog_document["source_id"]),
                ),
            )
        return sorted(entries, key=lambda entry: entry.document_id)

    @staticmethod
    def _approved_content_hashes(
        *,
        document_id: str,
        approved_chunk_ids: list[str],
        release_chunks_dir: Path,
    ) -> list[str]:
        if not approved_chunk_ids:
            return []
        chunk_path = Path(release_chunks_dir) / f"{document_id}.jsonl"
        if not chunk_path.is_file():
            raise ValueError(f"부분 복원 문서의 release 청크가 없습니다: {document_id}")
        content_hash_by_chunk_id: dict[str, str] = {}
        for line_number, line in enumerate(chunk_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"release 청크 {chunk_path}:{line_number}은 JSON 객체여야 합니다.")
            chunk_id = row.get("chunk_id")
            metadata = row.get("metadata")
            content_hash = metadata.get("content_hash") if isinstance(metadata, dict) else None
            if not isinstance(chunk_id, str) or not isinstance(content_hash, str):
                raise ValueError(f"release 청크 {chunk_path}:{line_number}의 chunk_id 또는 content_hash가 없습니다.")
            content_hash_by_chunk_id[chunk_id] = content_hash
        missing_chunk_ids = sorted(set(approved_chunk_ids) - set(content_hash_by_chunk_id))
        if missing_chunk_ids:
            raise ValueError(
                f"부분 복원 문서의 기존 승인 청크가 release에 없습니다: {document_id} ({', '.join(missing_chunk_ids)})",
            )
        return [content_hash_by_chunk_id[chunk_id] for chunk_id in approved_chunk_ids]

    @staticmethod
    def _pending_chunk_target(
        *,
        review: dict[str, Any],
        document_id: str,
    ) -> KnowledgePendingChunkRecoveryTarget:
        return KnowledgePendingChunkRecoveryTarget(
            chunk_id=KnowledgeRecoveryManifestService._required_string(
                review,
                "chunk_id",
                f"부분 복원 문서 {document_id}",
            ),
            page_start=KnowledgeRecoveryManifestService._required_positive_int(
                review,
                "page_start",
                document_id,
            ),
            page_end=KnowledgeRecoveryManifestService._required_positive_int(
                review,
                "page_end",
                document_id,
            ),
            status=KnowledgeRecoveryChunkStatus.PENDING,
        )

    @staticmethod
    def _ocr_origin(raw_reason: str, document_id: str) -> KnowledgeOcrManifestOrigin:
        if raw_reason == "CATALOG_OCR_REQUIRED":
            return KnowledgeOcrManifestOrigin.CATALOG
        if raw_reason == "TEXT_QUALITY_OCR_REQUIRED":
            return KnowledgeOcrManifestOrigin.DYNAMIC
        raise ValueError(f"알 수 없는 OCR 대기 사유입니다: {document_id} ({raw_reason})")

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str, context: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{context}의 {key}가 올바르지 않습니다.")
        return value.strip()

    @staticmethod
    def _required_positive_int(payload: dict[str, Any], key: str, document_id: str) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or value < 1:
            raise ValueError(f"부분 복원 문서의 {key}가 올바르지 않습니다: {document_id}")
        return value

    @staticmethod
    def _document_or_raise(
        documents: dict[str, dict[str, str]],
        document_id: str,
    ) -> dict[str, str]:
        document = documents.get(document_id)
        if document is None:
            raise ValueError(f"카탈로그에 없는 문서입니다: {document_id}")
        return document

    @staticmethod
    def _read_json_object(path: Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("corpus quality audit은 JSON 객체여야 합니다.")
        return payload

    @staticmethod
    def _write_jsonl(path: Path, rows: Any) -> None:
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )
