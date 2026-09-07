from hashlib import sha256
from pathlib import Path

from ai_worker.schemas.knowledge import (
    KnowledgeBoundingBox,
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgeMetadata,
    KnowledgePage,
    KnowledgePageBlock,
)
from ai_worker.schemas.knowledge_ocr import (
    KnowledgeOcrBlock,
    KnowledgeOcrDocumentArtifact,
    knowledge_ocr_artifact_path,
)


class KnowledgeOcrArtifactLoader:
    """CLOVA 등 OCR 공급자와 무관한 artifact를 기존 KnowledgePage로 변환합니다."""

    def __init__(
        self,
        *,
        artifact_root: Path,
    ) -> None:
        self._artifact_root = Path(artifact_root)

    def load(
        self,
        file_path: Path,
        metadata: KnowledgeMetadata,
    ) -> list[KnowledgePage]:
        source_path = Path(file_path)
        artifact_path = knowledge_ocr_artifact_path(
            artifact_root=self._artifact_root,
            document_id=metadata.document_id,
        )
        if not artifact_path.is_file():
            raise ValueError(f"OCR artifact가 없습니다: {metadata.document_id}")
        artifact = KnowledgeOcrDocumentArtifact.model_validate_json(
            artifact_path.read_text(encoding="utf-8"),
        )
        if artifact.document_id != metadata.document_id:
            raise ValueError(f"OCR artifact 문서 식별자가 다릅니다: {metadata.document_id}")
        if not source_path.is_file():
            raise ValueError(f"OCR artifact의 원본 PDF가 없습니다: {metadata.document_id}")
        actual_source_sha256 = sha256(source_path.read_bytes()).hexdigest()
        if artifact.source_sha256 != actual_source_sha256:
            raise ValueError(f"OCR artifact 원본 SHA-256이 다릅니다: {metadata.document_id}")
        return [
            self._to_knowledge_page(page=page, metadata=metadata)
            for page in artifact.pages
        ]

    @classmethod
    def _to_knowledge_page(
        cls,
        *,
        page,
        metadata: KnowledgeMetadata,
    ) -> KnowledgePage:
        ordered_columns = cls._ordered_columns(page.blocks)
        blocks = [
            KnowledgePageBlock(
                kind=KnowledgeContentKind.TEXT,
                order=index,
                bbox=cls._combined_bbox(column_blocks),
                content=cls._join_column_blocks(column_blocks),
            )
            for index, column_blocks in enumerate(ordered_columns)
        ]
        warnings = (
            [KnowledgeExtractionWarning.MULTI_COLUMN_LAYOUT]
            if len(blocks) > 1
            else []
        )
        return KnowledgePage(
            content="\n\n".join(block.content for block in blocks),
            metadata=metadata,
            page_number=page.page_number,
            blocks=blocks,
            extraction_warnings=warnings,
        )

    @classmethod
    def _ordered_columns(cls, blocks: list[KnowledgeOcrBlock]) -> list[list[KnowledgeOcrBlock]]:
        sorted_by_x = sorted(blocks, key=lambda block: (block.bbox.x0, block.bbox.top, block.block_id))
        median_width = cls._median([block.bbox.x1 - block.bbox.x0 for block in sorted_by_x])
        gap_threshold = max(median_width, 48.0)
        columns: list[list[KnowledgeOcrBlock]] = []
        current: list[KnowledgeOcrBlock] = []
        current_right: float | None = None
        for block in sorted_by_x:
            if current and current_right is not None and block.bbox.x0 - current_right > gap_threshold:
                columns.append(current)
                current = []
                current_right = None
            current.append(block)
            current_right = max(current_right or block.bbox.x1, block.bbox.x1)
        if current:
            columns.append(current)
        return [
            sorted(column, key=lambda block: (block.bbox.top, block.bbox.x0, block.block_id))
            for column in columns
        ]

    @staticmethod
    def _median(values: list[float]) -> float:
        ordered = sorted(values)
        midpoint = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[midpoint]
        return (ordered[midpoint - 1] + ordered[midpoint]) / 2

    @staticmethod
    def _join_column_blocks(blocks: list[KnowledgeOcrBlock]) -> str:
        return "\n".join(block.text for block in blocks)

    @staticmethod
    def _combined_bbox(blocks: list[KnowledgeOcrBlock]) -> KnowledgeBoundingBox:
        return KnowledgeBoundingBox(
            x0=min(block.bbox.x0 for block in blocks),
            top=min(block.bbox.top for block in blocks),
            x1=max(block.bbox.x1 for block in blocks),
            bottom=max(block.bbox.bottom for block in blocks),
        )
