from collections.abc import Iterable
from dataclasses import dataclass

from ai_worker.rag.splitters.repairers.protocol import (
    DocumentChunkRepairer,
    DocumentChunkRepairFunction,
)
from ai_worker.schemas.knowledge import KnowledgeChunk


@dataclass(frozen=True)
class CallableDocumentChunkRepairer:
    """기존 검수 복원 함수를 문서별 repairer 계약으로 감싸는 어댑터입니다."""

    document_id: str
    apply_chunks: DocumentChunkRepairFunction

    def apply(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        return self.apply_chunks(chunks)


class DocumentChunkRepairRegistry:
    """문서 ID와 검수 완료 청크 복원 규칙을 연결합니다."""

    def __init__(
        self,
        *,
        repairers: Iterable[DocumentChunkRepairer] = (),
    ) -> None:
        self._repairers: dict[str, DocumentChunkRepairer] = {}
        for repairer in repairers:
            document_id = repairer.document_id.strip()
            if not document_id:
                raise ValueError("문서 repairer의 document_id는 비어 있을 수 없습니다.")
            if document_id in self._repairers:
                raise ValueError(f"문서 repairer가 중복되었습니다: {document_id}")
            self._repairers[document_id] = repairer

    def repair(self, chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
        if not chunks:
            return chunks
        repairer = self._repairers.get(chunks[0].metadata.document_id)
        return chunks if repairer is None else repairer.apply(chunks)
