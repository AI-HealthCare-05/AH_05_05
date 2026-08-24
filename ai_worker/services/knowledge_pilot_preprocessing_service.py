import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

import yaml
from pydantic import BaseModel, Field

from ai_worker.rag.normalizers.knowledge_normalizer import (
    KnowledgeNormalizer,
    TextQualityStatus,
)
from ai_worker.rag.splitters.knowledge_splitter import KnowledgeSplitter
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeMetadata,
    KnowledgePage,
)
from ai_worker.schemas.knowledge_manifest import (
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


class KnowledgePilotPreprocessingResult(BaseModel):
    dataset_version: str
    processed_document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    skipped_documents: list[SkippedKnowledgeDocument] = Field(default_factory=list)


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
        text_output.mkdir(parents=True, exist_ok=True)
        chunk_output.mkdir(parents=True, exist_ok=True)

        active_document_ids = {pilot.document_id for pilot in pilot_manifest.pilots}
        self._remove_orphaned_outputs(
            active_document_ids=active_document_ids,
            text_output=text_output,
            chunk_output=chunk_output,
        )

        processed_count = 0
        chunk_count = 0
        skipped: list[SkippedKnowledgeDocument] = []

        for pilot in pilot_manifest.pilots:
            self._remove_previous_outputs(
                document_id=pilot.document_id,
                text_output=text_output,
                chunk_output=chunk_output,
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
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason=f"TEXT_QUALITY_{quality.status.value}",
                    )
                )
                continue

            chunks = self._splitter.split(normalized_pages)
            if not chunks:
                skipped.append(
                    SkippedKnowledgeDocument(
                        document_id=pilot.document_id,
                        reason="NO_CHUNKS",
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

        return KnowledgePilotPreprocessingResult(
            dataset_version=normalized_version,
            processed_document_count=processed_count,
            chunk_count=chunk_count,
            skipped_documents=skipped,
        )

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
    ) -> None:
        for directory in (text_output, chunk_output):
            output_path = directory / f"{document_id}.jsonl"
            output_path.unlink(missing_ok=True)

    @staticmethod
    def _remove_orphaned_outputs(
        *,
        active_document_ids: set[str],
        text_output: Path,
        chunk_output: Path,
    ) -> None:
        for directory in (text_output, chunk_output):
            for output_path in directory.glob("*.jsonl"):
                if output_path.stem not in active_document_ids:
                    output_path.unlink()
