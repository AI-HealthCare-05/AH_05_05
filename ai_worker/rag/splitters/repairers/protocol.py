from collections.abc import Callable
from typing import Protocol

from ai_worker.schemas.knowledge import KnowledgeChunk


class DocumentChunkRepairer(Protocol):
    """사람이 검수한 특정 문서의 청크 복원 규칙 계약입니다."""

    @property
    def document_id(self) -> str: ...

    def apply(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]: ...


DocumentChunkRepairFunction = Callable[[list[KnowledgeChunk]], list[KnowledgeChunk]]
